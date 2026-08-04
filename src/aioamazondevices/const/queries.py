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
      includeHouseholdDevices: false
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
        value { value scale }
        timeOfSample
        timeOfLastChange
      }
      ... on RangeValue {
        rangeValue { value }
        timeOfSample
        timeOfLastChange
      }

      # --- thermostat ---
      ... on Setpoint {
        value { value scale }
        deviceNativeScaleValue
        timeOfSample
        timeOfLastChange
      }
      ... on ThermostatMode {
        thermostatModeValue
        timeOfSample
        timeOfLastChange
      }

      # --- thermostatConfiguration (properties) ---
      ... on ThermostatConfigurationAllowedTemperatureRange {
        thermostatAllowedTemperatureRangeValue {
          heating { minimum { value scale } maximum { value scale } }
          cooling { minimum { value scale } maximum { value scale } }
        }
        timeOfSample
        timeOfLastChange
      }
      ... on ThermostatConfigurationSetupState {
        thermostatSetupStateValue { value }
        timeOfSample
        timeOfLastChange
      }
      ... on ThermostatConfigurationTemperatureScale {
        thermostatTemperatureScaleValue { value }
        timeOfSample
        timeOfLastChange
      }

      # --- thermostatSchedule ---
      ... on ThermostatScheduleAdaptiveRecoveryEnabled {
        thermostatScheduleAdaptiveRecoveryEnabledValue { value }
        timeOfSample
        timeOfLastChange
      }
      ... on ThermostatScheduleScheduleEnabled {
        thermostatScheduleScheduleEnabledValue { value }
        timeOfSample
        timeOfLastChange
      }
      ... on ThermostatScheduleLastActivityType {
        thermostatScheduleLastActivityTypeValue { value }
        timeOfSample
        timeOfLastChange
      }

      # --- thermostatAutomation ---
      ... on ThermostatAutomationLastActivityType {
        thermostatAutomationLastActivityTypeValue { value }
        timeOfSample
        timeOfLastChange
      }
    }

    # --- static device capabilities ---
    configuration {
      __typename

      ... on ThermostatConfiguration {
        supportedModes
      }
      ... on HvacConfiguration {
        numberOfPrimaryHeaterStage
        numberOfFanStage
        numberOfCoolerStage
      }
      ... on ThermostatScheduleConfiguration {
        supportedFanModes
        supportsAdaptiveRecovery
        maxEntryPerDay
      }
      ... on ThermostatConfigurationConfiguration {
        supportedResetStates { value }
        requiredSetupInformation
        supportedTemperatureScales
        safetyTemperatures {
          heating { minimum { value scale } maximum { value scale } }
          cooling { minimum { value scale } maximum { value scale } }
        }
        minimumSetpointDifferential { value scale }
        componentConfigurationConstraints {
          supportedTerminals {
            name
            purpose
          }
          maximumStages {
            heating
            cooling
            combined
          }
          supportedSwitchOverTypes
          lockoutTemperature {
            heating  { minimum { value scale } maximum { value scale } }
            cooling  { minimum { value scale } maximum { value scale } }
            increment { value scale }
          }
        }
      }

      # likely on the `doorbell` feature
      ... on SimpleEventSourceConfiguration {
        supportedEvents {
          id
          friendlyNames {
            type
            value { text locale }
          }
        }
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
