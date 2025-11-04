"""aioamazondevices GraphQL queries."""

QUERY_DEVICE_DATA = """
query getDevicesBaseData {
  listEndpoints(
    listEndpointsInput: {
        displayCategory: "ALEXA_VOICE_ENABLED"
        includeHouseholdDevices: true
    }
  )
  {
    endpoints {
      endpointId: id
      friendlyNameObject { value { text } }
      manufacturer { value { text } }
      model { value { text} }
      serialNumber { value { text } }
      softwareVersion { value { text } }
      creationTime
      enablement
      displayCategories {
        all { value }
        primary { value }
      }
      alexaEnabledMetadata {
        iconId
        isVisible
        category
        capabilities
      }
      legacyIdentifiers {
        dmsIdentifier {
          deviceType { value { text } }
        }
        chrsIdentifier { entityId }
      }
      legacyAppliance { applianceId }
    }
  }
}
"""

QUERY_SENSOR_STATE = """
fragment EndpointState on Endpoint {
  endpointId: id
  friendlyNameObject { value { text } }
  features {
    name
    properties {
      name
      type
      accuracy
      error { type message }
      __typename
      ... on Illuminance {
        illuminanceValue { value }
        timeOfSample
        timeOfLastChange
      }
      ... on Reachability {
        reachabilityStatusValue
        timeOfSample
        timeOfLastChange
      }
      ... on DetectionState {
        detectionStateValue
        timeOfSample
        timeOfLastChange
      }
      ... on TemperatureSensor {
        name
        value {
          value
          scale
        }
        timeOfSample
        timeOfLastChange
      }
    }
  }
}


query getEndpointState($endpointIds: [String]!) {
  listEndpoints(
    listEndpointsInput: {
      latencyTolerance: LOW,
      endpointIds: $endpointIds,
      includeHouseholdDevices: true
    }
  ) {
    endpoints {
      ...EndpointState
    }
  }
}
"""
