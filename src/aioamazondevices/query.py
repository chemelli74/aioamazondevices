"""GraphQL Queries."""

QUERY_DEVICE_STATE = """
query getDevicesState ($latencyTolerance: LatencyToleranceValue) {
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
      settings {
        doNotDisturb {
          id
          endpointId
          name
          toggleValue
          error {
            type
            message
          }
        }
      }
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
      associatedUnits { id }
      connections {
          type
          macAddress
          bleMeshDeviceUuid
      }
      features(latencyToleranceValue: $latencyTolerance) {
        name
        instance
        properties {
          name
          type
          accuracy
          error { message }
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
          ... on Volume {
              value { volValue: value }
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
  }
}
"""

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
query getEndpointState($endpointId: String!, $latencyTolerance: LatencyToleranceValue) {
  endpoint(id: $endpointId) {
    endpointId: id
    settings {
      doNotDisturb {
        id
        endpointId
        name
        toggleValue
        error {
          type
          message
        }
      }
    }
    features(latencyToleranceValue: $latencyTolerance) {
      name
      instance
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
}
"""
