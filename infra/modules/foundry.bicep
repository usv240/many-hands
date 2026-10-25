// Microsoft Foundry: an AI Services account with a project and a gpt-5-mini deployment.
// Local key auth is disabled; everything signs in with Microsoft Entra ID (managed identity or azd login).
param location string
param tags object
param accountName string
param principalId string
param modelCapacity int
param appInsightsId string
@secure()
param appInsightsConnectionString string

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
    allowProjectManagement: true
    disableLocalAuth: true
  }
}

// Created after the model deployment: two child operations on one account cannot run in parallel.
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: 'many-hands'
  location: location
  tags: tags
  dependsOn: [deployment]
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'Many Hands'
    description: 'Fair match intelligence: traces every goal to everyone who caused it and checks each line for scapegoating before it airs.'
  }
}

// Tracing for agent runs lands in Application Insights.
resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: 'appinsights'
  properties: {
    category: 'AppInsights'
    target: appInsightsId
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: { key: appInsightsConnectionString }
    metadata: { ApiType: 'Azure', ResourceId: appInsightsId }
  }
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: 'gpt-5-mini'
  sku: { name: 'GlobalStandard', capacity: modelCapacity }
  properties: {
    model: { format: 'OpenAI', name: 'gpt-5-mini', version: '2025-08-07' }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

// Let the person running azd call models and use the project, with no keys.
var roles = [
  '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // Cognitive Services OpenAI User
  '53ca6127-db72-4b80-b1b0-d745d6d5456d' // Azure AI User
]
resource userRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for role in roles: if (!empty(principalId)) {
  scope: account
  name: guid(account.id, principalId, role)
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role)
  }
}]

output accountId string = account.id
output accountName string = account.name
output openAiEndpoint string = 'https://${accountName}.openai.azure.com/'
output projectEndpoint string = 'https://${accountName}.services.ai.azure.com/api/projects/${project.name}'
output deploymentName string = deployment.name
