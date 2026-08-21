# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""GraphQL queries for Amazon devices."""

QUERY_DEVICE_DATA = """
query getDevicesBaseData {
  alexaVoiceDevices: listEndpoints(
    listEndpointsInput: {
      displayCategory: "ALEXA_VOICE_ENABLED"
      includeHouseholdDevices: true
    }
  ) {
    ...DeviceEndpoints
  }

  airQualityMonitors: listEndpoints(
    listEndpointsInput: {
      displayCategory: "AIR_QUALITY_MONITOR"
      includeHouseholdDevices: true
    }
  ) {
    ...DeviceEndpoints
  }

  thermostats: listEndpoints(
    listEndpointsInput: {
      displayCategory: "THERMOSTAT"
      includeHouseholdDevices: true
    }
  ) {
    ...DeviceEndpoints
  }
}

fragment DeviceEndpoints on ListEndpointsResponse {
  endpoints {
    endpointId: id
    friendlyNameObject { value { text } }
    manufacturer { value { text } }
    model { value { text } }
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
      dmsIdentifier { deviceType { value { text } } }
      chrsIdentifier { entityId }
    }
    legacyAppliance { applianceId }
  }
}
"""

QUERY_SENSOR_STATE = """
fragment EndpointState on Endpoint {
  endpointId: id
  friendlyNameObject { value { text } }
  features {
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
      ... on RangeValue {
        rangeValue { value }
        timeOfSample
        timeOfLastChange
      }
      ... on Setpoint {
        value { value scale }
        timeOfSample
        timeOfLastChange
      }
      ... on ThermostatMode {
        thermostatModeValue
        timeOfSample
        timeOfLastChange
      }
      ... on ThermostatConfigurationAllowedTemperatureRange {
        thermostatAllowedTemperatureRangeValue {
          heating { minimum { value scale } maximum { value scale } }
          cooling { minimum { value scale } maximum { value scale } }
        }
        timeOfSample
        timeOfLastChange
      }
    }
    configuration {
      __typename
      ... on ThermostatConfiguration {
        supportedModes
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
