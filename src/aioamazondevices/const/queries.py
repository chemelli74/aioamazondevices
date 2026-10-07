# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""GraphQL queries for Amazon devices."""

QUERY_DEVICE_DATA = """
query getDevicesBaseData {
  listEndpoints(
    listEndpointsInput: {
      latencyTolerance: LOW,
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
        ... on ToggleState {
          toggleStateValue
          timeOfSample
          timeOfLastChange
        }
        ... on Power {
          powerStateValue
          timeOfSample
          timeOfLastChange
        }
        ... on Brightness {
          brightnessStateValue
          timeOfSample
          timeOfLastChange
        }
        ... on Color {
          colorStateValue { hue saturation brightness }
          timeOfSample
          timeOfLastChange
        }
        ... on Mode {
          modeValue { value }
          timeOfSample
          timeOfLastChange
        }
        ... on ThermostatMode {
          thermostatModeValue
          timeOfSample
          timeOfLastChange
        }
        ... on Setpoint {
          value { value scale }
          deviceNativeScaleValue
          timeOfSample
          timeOfLastChange
        }
        ... on ThermostatScheduleScheduleEnabled {
          thermostatScheduleScheduleEnabledValue { value }
          timeOfSample
          timeOfLastChange
        }
        ... on ThermostatScheduleAdaptiveRecoveryEnabled {
          thermostatScheduleAdaptiveRecoveryEnabledValue { value }
          timeOfSample
          timeOfLastChange
        }
        ... on ThermostatScheduleLastActivityType {
          thermostatScheduleLastActivityTypeValue { value }
          timeOfSample
          timeOfLastChange
        }
        ... on AdaptiveRecoveryStatus {
          adaptiveRecoveryStatusValue { value }
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
        ... on ThermostatConfigurationAllowedTemperatureRange {
          thermostatAllowedTemperatureRangeValue {
            heating {
              minimum { value scale }
              maximum { value scale }
            }
            cooling {
              minimum { value scale }
              maximum { value scale }
            }
          }
          timeOfSample
          timeOfLastChange
        }
      }
      operations { name }
      configuration {
        __typename
        ... on ModeConfiguration {
          friendlyName { value { text } }
          order
          modeOptions {
            value
            modeResources {
              friendlyName { value { text } }
            }
          }
        }
        ... on RangeConfiguration {
          friendlyName { value { text } }
          supportedRange {
            minimumValue
            maximumValue
            precision
          }
          unitOfMeasure { value { text } }
          presets {
            rangeValue
            presetResources {
              friendlyName { value { text } }
            }
          }
        }
        ... on ThermostatConfiguration {
          supportedModes
        }
        ... on ThermostatConfigurationConfiguration {
          supportedResetStates { value }
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
              heating {
                minimum { value scale }
                maximum { value scale }
              }
              cooling {
                minimum { value scale }
                maximum { value scale }
              }
              increment { value scale }
            }
          }
          requiredSetupInformation
          supportedTemperatureScales
          safetyTemperatures {
            heating {
              minimum { value scale }
              maximum { value scale }
            }
            cooling {
              minimum { value scale }
              maximum { value scale }
            }
          }
          minimumSetpointDifferential { value scale }
        }
        ... on ThermostatScheduleConfiguration {
          supportedFanModes
          supportsAdaptiveRecovery
          maxEntryPerDay
        }
        ... on ToggleConfiguration {
          friendlyName { value { text } }
        }
        ... on GenericConfiguration {
          genericValue
        }
      }
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
