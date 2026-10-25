// Many Hands on Azure. Subscription-scoped so `azd up` creates the resource group too.
targetScope = 'subscription'

@minLength(1)
@maxLength(32)
@description('azd environment name, used to name every resource.')
param environmentName string

@description('Region for every resource. eastus2 has gpt-5-mini Global Standard capacity.')
param location string

@description('Object id of the person running azd, granted access to the model with no keys.')
param principalId string = ''

@description('Model deployment capacity in thousands of tokens per minute.')
param modelCapacity int = 100

var tags = { 'azd-env-name': environmentName, project: 'many-hands' }
var token = toLower(uniqueString(subscription().id, environmentName, location))

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module monitoring 'modules/monitoring.bicep' = {
  scope: rg
  name: 'monitoring'
  params: {
    location: location
    tags: tags
    logAnalyticsName: 'log-${token}'
    appInsightsName: 'appi-${token}'
  }
}

module foundry 'modules/foundry.bicep' = {
  scope: rg
  name: 'foundry'
  params: {
    location: location
    tags: tags
    accountName: 'ai-manyhands-${token}'
    principalId: principalId
    modelCapacity: modelCapacity
    appInsightsId: monitoring.outputs.appInsightsId
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
  }
}

module app 'modules/app.bicep' = {
  scope: rg
  name: 'app'
  params: {
    location: location
    tags: tags
    token: token
    logAnalyticsId: monitoring.outputs.logAnalyticsId
    foundryAccountName: foundry.outputs.accountName
    projectEndpoint: foundry.outputs.projectEndpoint
    deploymentName: foundry.outputs.deploymentName
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    eventHubsNamespace: 'evh-manyhands-${token}'
    eventHubName: 'match-events'
  }
}

module eventhubs 'modules/eventhubs.bicep' = {
  scope: rg
  name: 'eventhubs'
  params: {
    location: location
    tags: tags
    namespaceName: 'evh-manyhands-${token}'
    appPrincipalId: app.outputs.identityPrincipalId
    userPrincipalId: principalId
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_OPENAI_ENDPOINT string = foundry.outputs.openAiEndpoint
output AZURE_AI_PROJECT_ENDPOINT string = foundry.outputs.projectEndpoint
output AZURE_OPENAI_DEPLOYMENT string = foundry.outputs.deploymentName
output APPLICATIONINSIGHTS_CONNECTION_STRING string = monitoring.outputs.appInsightsConnectionString
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = app.outputs.registryEndpoint
output SERVICE_APP_URL string = app.outputs.appUrl
output EVENTHUB_NAMESPACE string = eventhubs.outputs.namespace
output EVENTHUB_NAME string = eventhubs.outputs.hubName
