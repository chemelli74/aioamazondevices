# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""GraphQL queries for Amazon devices."""

QUERY_DEVICE_DATA = """
query getDevicesBaseData {
  listEndpoints(
    listEndpointsInput: {
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

QUERY_DEVICE_FEATURES = """
fragment EndpointFeatures on Endpoint {
  endpointId: id
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
      ... on DetectionSensitivity {
        detectionSensitivityValue
        timeOfSample
        timeOfLastChange
      }
      ... on EnablementState {
        enablementStateValue
        timeOfSample
        timeOfLastChange
      }
      ... on DetectionRange {
        detectionRangeValue
        timeOfSample
        timeOfLastChange
      }
      ... on DetectionTechnology {
        detectionTechnologyValue
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


query getEndpointFeatures($endpointIds: [String]!) {
  listEndpoints(
    listEndpointsInput: {
      latencyTolerance: LOW,
      endpointIds: $endpointIds,
      includeHouseholdDevices: true
    }
  ) {
    endpoints {
      ...EndpointFeatures
    }
  }
}
"""

QUERY_POLLED_SENSOR_STATE = """
fragment EndpointState on Endpoint {
  endpointId: id
  features {
    name
    instance
    properties {
      ... on Illuminance {
        name
        error { type message }
        illuminanceValue { value }
        timeOfSample
      }
      ... on Reachability {
        name
        error { type message }
        reachabilityStatusValue
        timeOfSample
      }
      ... on DetectionState {
        name
        error { type message }
        detectionStateValue
        timeOfSample
      }
    }
  }
}


query getPolledSensorState($endpointIds: [String]!) {
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

MUTATION_SET_ENDPOINT_FEATURES = """
mutation setEndpointFeatures(
  $setEndpointFeaturesInput: SetEndpointFeaturesInput!
) {
  setEndpointFeatures(setEndpointFeaturesInput: $setEndpointFeaturesInput) {
    featureControlResponses {
      endpointId
      featureName
      instance
      featureOperationName
      code
    }
    errors {
      endpointId
      featureName
      instance
      featureOperationName
      code
      message
    }
  }
}
"""

QUERY_ALL_ENDPOINT_STATES = """
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

      ... on Brightness {
        timeOfSample
        timeOfLastChange
        brightnessStateValue
      }
      ... on Color {
        timeOfSample
        timeOfLastChange
        colorStateValue {
          hue
          saturation
          brightness
        }
      }
      ... on ColorTemperature {
        timeOfSample
        timeOfLastChange
        colorTemperatureInKelvinStateValue
      }
      ... on DetectionRange {
        timeOfSample
        timeOfLastChange
        detectionRangeValue
      }
      ... on DetectionSensitivity {
        timeOfSample
        timeOfLastChange
        detectionSensitivityValue
      }
      ... on DetectionState {
        timeOfSample
        timeOfLastChange
        detectionStateValue
      }
      ... on DetectionTechnology {
        timeOfSample
        timeOfLastChange
        detectionTechnologyValue
      }
      ... on DynamicLightingEffectEffect {
        timeOfSample
        timeOfLastChange
        dynamicLightingEffectEffectValue {
          status
          typeId
          colorPalette {
            brightness
            hue
            saturation
            colorTemperatureinKelvin
          }
          speedMultiplier
        }
      }
      ... on EnablementState {
        timeOfSample
        timeOfLastChange
        enablementStateValue
      }
      ... on Illuminance {
        illuminanceValue {
          value
        }
        timeOfSample
        timeOfLastChange
      }
      ... on Mode {
        timeOfSample
        timeOfLastChange
        modeValue {
          value
        }
      }
      ... on Percentage {
        timeOfSample
        timeOfLastChange
        percentageValue
      }
      ... on Power {
        timeOfSample
        timeOfLastChange
        powerStateValue
      }
      ... on PowerLevel {
        timeOfSample
        timeOfLastChange
        powerLevelValue
      }
      ... on RangeValue {
        timeOfSample
        timeOfLastChange
        rangeValue {
          value
        }
      }
      ... on Reachability {
        timeOfSample
        timeOfLastChange
        reachabilityStatusValue
      }
      ... on RelativeHumidity {
        timeOfSample
        timeOfLastChange
        relativeHumidityValue {
          value
        }
      }
      ... on Setpoint {
        timeOfSample
        timeOfLastChange
        deviceNativeScaleValue
        setpointValue: value {
          value
          scale
        }
      }
      ... on StatusCode {
        timeOfSample
        timeOfLastChange
        statusCodeValue {
          value {
            code
            timeOfDetection
          }
        }
      }
      ... on TemperatureSensor {
        timeOfSample
        timeOfLastChange
        temperatureValue: value {
          value
          scale
        }
      }
      ... on ThermostatAutomationLastActivityType {
        timeOfSample
        timeOfLastChange
        thermostatAutomationLastActivityTypeValue {
          value
        }
      }
      ... on ThermostatConfigurationAllowedTemperatureRange {
        timeOfSample
        timeOfLastChange
        thermostatAllowedTemperatureRangeValue {
          heating {
            minimum {
              value
              scale
            }
            maximum {
              value
              scale
            }
          }
          cooling {
            minimum {
              value
              scale
            }
            maximum {
              value
              scale
            }
          }
        }
      }
      ... on ThermostatConfigurationSetupState {
        timeOfSample
        timeOfLastChange
        thermostatSetupStateValue {
          value
        }
      }
      ... on ThermostatConfigurationTemperatureScale {
        timeOfSample
        timeOfLastChange
        thermostatTemperatureScaleValue {
          value
        }
      }
      ... on ThermostatMode {
        timeOfSample
        timeOfLastChange
        thermostatModeValue
      }
      ... on ThermostatScheduleAdaptiveRecoveryEnabled {
        timeOfSample
        timeOfLastChange
        thermostatScheduleAdaptiveRecoveryEnabledValue {
          value
        }
      }
      ... on ThermostatScheduleLastActivityType {
        timeOfSample
        timeOfLastChange
        thermostatScheduleLastActivityTypeValue {
          value
        }
      }
      ... on ThermostatScheduleScheduleEnabled {
        timeOfSample
        timeOfLastChange
        thermostatScheduleScheduleEnabledValue {
          value
        }
      }
      ... on ToggleState {
        timeOfSample
        timeOfLastChange
        toggleStateValue
      }
      ... on UnknownFeatureProperty {
        data
      }
      ... on Volume {
        timeOfSample
        timeOfLastChange
        volumeValue: value {
          value
        }
      }
    }
    operations {
      name
      verificationsRequired {
        type
      }
    }
    configuration {
      __typename
      ... on ActionConfiguration {
        action {
          supportedStates
          categoryLabel {
            friendlyNames {
              type
              value {
                text
                locale
              }
            }
          }
          supportedActions {
            id
            friendlyNames {
              type
              value {
                text
                locale
              }
            }
          }
        }
        target {
          categoryLabel {
            friendlyNames {
              type
              value {
                text
                locale
              }
            }
          }
          supportedTargets {
            friendlyNames {
              type
              value {
                text
                locale
              }
            }
            id
          }
        }
      }
      ... on DetectionEventsConfiguration {
        supportedEvents {
          category {
            __typename
            ... on CameraCapabilitySupportedEventCategory {
              name
              capabilitySubType: subType
            }
            ... on CameraEventSupportedEventCategory {
              name
              eventSubType: subType
            }
          }
          displayText
          filterIconImageUri
          fallbackImageUri
          altTextForFallbackImage
        }
      }
      ... on GenericConfiguration {
        genericValue
      }
      ... on HvacConfiguration {
        numberOfPrimaryHeaterStage
        numberOfFanStage
        numberOfCoolerStage
      }
      ... on ModeConfiguration {
        friendlyName {
          type
          value {
            text
            locale
          }
        }
        order
        modeOptions {
          value
          modeResources {
            friendlyName {
              type
              value {
                text
                locale
              }
            }
          }
        }
      }
      ... on ObjectDetectionConfiguration {
        objectDetectionConfiguration {
          imageNetClass
          isAvailable
          unavailabilityReason
          zone {
            id
            friendlyName
          }
          states {
            id
            friendlyName
          }
        }
      }
      ... on ProactiveNotificationSourceConfiguration {
        notificationConditions {
          conditionType
          property {
            interfaceName
            instance
            name
          }
          valueChangeCondition {
            comparator
            value
          }
        }
        supportedNotificationEvents {
          eventName
          notificationResources {
            label {
              type
              value {
                assetId
              }
            }
          }
        }
      }
      ... on RangeConfiguration {
        friendlyName {
          type
          value {
            text
            locale
          }
        }
        supportedRange {
          minimumValue
          maximumValue
          precision
        }
        unitOfMeasure {
          type
          value {
            text
            locale
          }
        }
        presets {
          rangeValue
          presetResources {
            friendlyName {
              type
              value {
                text
                locale
              }
            }
          }
        }
      }
      ... on StatusCodeConfiguration {
        supportedCodes {
          code
          descriptions {
            primary {
              type
              value {
                text
                locale
              }
            }
          }
        }
      }
      ... on ThermostatConfiguration {
        supportedModes
      }
      ... on ThermostatConfigurationConfiguration {
        supportedResetStates {
          value
        }
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
              minimum {
                value
                scale
              }
              maximum {
                value
                scale
              }
            }
            cooling {
              minimum {
                value
                scale
              }
              maximum {
                value
                scale
              }
            }
            increment {
              value
              scale
            }
          }
        }
        requiredSetupInformation
        supportedTemperatureScales
        safetyTemperatures {
          heating {
            minimum {
              value
              scale
            }
            maximum {
              value
              scale
            }
          }
          cooling {
            minimum {
              value
              scale
            }
            maximum {
              value
              scale
            }
          }
        }
        minimumSetpointDifferential {
          value
          scale
        }
      }
      ... on ThermostatScheduleConfiguration {
        supportedFanModes
        supportsAdaptiveRecovery
        maxEntryPerDay
      }
      ... on ToggleConfiguration {
        friendlyName {
          type
          value {
            text
            locale
          }
        }
      }
    }
  }
}

query getEndpointState {
  listEndpoints(
    listEndpointsInput: {
      latencyTolerance: LOW,
      includeHouseholdDevices: true
    }
  ) {
    endpoints {
      ...EndpointState
    }
  }
}
"""

QUERY_INTROSPECTION = """
query getSchema {
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types {
      ...FullType
    }
    directives {
      name
      description
      locations
      args {
        ...InputValue
      }
    }
  }
}

fragment FullType on __Type {
  kind
  name
  description
  fields(includeDeprecated: true) {
    name
    description
    args {
      ...InputValue
    }
    type {
      ...TypeRef
    }
    isDeprecated
    deprecationReason
  }
  inputFields {
    ...InputValue
  }
  interfaces {
    ...TypeRef
  }
  enumValues(includeDeprecated: true) {
    name
    description
    isDeprecated
    deprecationReason
  }
  possibleTypes {
    ...TypeRef
  }
}

fragment InputValue on __InputValue {
  name
  description
  type {
    ...TypeRef
  }
  defaultValue
}

fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType {
        kind
        name
        ofType {
          kind
          name
          ofType {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
              }
            }
          }
        }
      }
    }
  }
}
"""
