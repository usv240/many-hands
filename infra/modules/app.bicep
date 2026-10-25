// The app: a private container registry, a managed identity, and one Container App that serves
// the website and the API. The identity can pull images and call Foundry models; there are no keys.
param location string
param tags object
param token string
param logAnalyticsId string
param foundryAccountName string
param projectEndpoint string
param deploymentName string
@secure()
param appInsightsConnectionString string
param eventHubsNamespace string = ''
param eventHubName string = ''

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: last(split(logAnalyticsId, '/'))
}
resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-app-${token}'
  location: location
  tags: tags
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'cr${token}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

var acrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
resource pullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, identity.id, acrPull)
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPull)
  }
}

var aiRoles = [
  '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // Cognitive Services OpenAI User
  '53ca6127-db72-4b80-b1b0-d745d6d5456d' // Azure AI User
]
resource foundryRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for role in aiRoles: {
  scope: foundry
  name: guid(foundry.id, identity.id, role)
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role)
  }
}]

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${token}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-manyhands-${token}'
  location: location
  tags: union(tags, { 'azd-service-name': 'app' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  dependsOn: [pullRole]
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [{ server: registry.properties.loginServer, identity: identity.id }]
      secrets: [{ name: 'appinsights', value: appInsightsConnectionString }]
    }
    template: {
      containers: [{
        name: 'app'
        image: 'mcr.microsoft.com/k8se/quickstart:latest'
        resources: { cpu: json('1.0'), memory: '2Gi' }
        env: [
          { name: 'AZURE_AI_PROJECT_ENDPOINT', value: projectEndpoint }
          { name: 'AZURE_OPENAI_DEPLOYMENT', value: deploymentName }
          { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
          { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights' }
          { name: 'EVENTHUB_NAMESPACE', value: eventHubsNamespace }
          { name: 'EVENTHUB_NAME', value: eventHubName }
        ]
      }]
      // One warm replica so a judge never waits for a cold start; scales out under load.
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

output registryEndpoint string = registry.properties.loginServer
output appUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
output identityPrincipalId string = identity.properties.principalId
output identityClientId string = identity.properties.clientId
