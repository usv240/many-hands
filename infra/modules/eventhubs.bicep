// Azure Event Hubs carries the live match feed. A goal arriving on this stream wakes the agents.
param location string
param tags object
param namespaceName string
param appPrincipalId string
param userPrincipalId string

resource ns 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: namespaceName
  location: location
  tags: tags
  sku: { name: 'Basic', tier: 'Basic', capacity: 1 }
  properties: {
    disableLocalAuth: true // Entra ID only: no connection strings exist
    minimumTlsVersion: '1.2'
  }
}

resource hub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: ns
  name: 'match-events'
  properties: {
    partitionCount: 1 // one match feed in order; scale out per match in production
    messageRetentionInDays: 1
  }
}

// The way back out: approved, audited graphics for the broadcaster's own graphics system.
resource graphicsHub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: ns
  name: 'broadcast-graphics'
  properties: {
    partitionCount: 1
    messageRetentionInDays: 1
  }
}

var dataOwner = 'f526a384-b230-433a-b45c-95f59c4a2dec' // Azure Event Hubs Data Owner
resource appRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: ns
  name: guid(ns.id, appPrincipalId, dataOwner)
  properties: {
    principalId: appPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', dataOwner)
  }
}
resource userRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(userPrincipalId)) {
  scope: ns
  name: guid(ns.id, userPrincipalId, dataOwner)
  properties: {
    principalId: userPrincipalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', dataOwner)
  }
}

output namespace string = ns.name
output hubName string = hub.name
output graphicsHubName string = graphicsHub.name
