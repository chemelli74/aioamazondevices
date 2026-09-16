# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""GraphQL queries for Amazon devices."""

QUERY_DEVICE_DATA = """
query getDevicesBaseData {
  alexaVoiceDevices: listEndpoints(
    listEndpointsInput: {
      allDisplayCategories: "ALEXA_VOICE_ENABLED"
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

QUERY_DEVICE_DATA_ALL = """
query getDevicesBaseData {
  alexaVoiceDevices: listEndpoints(
    listEndpointsInput: {
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

      ... on ActionState {
        timeOfSample
        timeOfLastChange
        actionStateValue {
          status
          timeInterval {
            start
            end
            duration
          }
          actionId
          targetIds
        }
      }
      ... on AdaptiveRecoveryStatus {
        timeOfSample
        timeOfLastChange
        adaptiveRecoveryStatusValue {
          value
        }
      }
      ... on ArmState {
        timeOfSample
        timeOfLastChange
        armStateValue
      }
      ... on AutomationManagementAutomationStatuses {
        timeOfSample
        timeOfLastChange
        automationManagementAutomationStatusesValue {
          automationStatuses {
            status
            interfaceName
            instance
            source
          }
        }
      }
      ... on Battery {
        timeOfSample
        timeOfLastChange
        batteryValue {
          levelPercentage
          health {
            state
            reasons
          }
          chargingHealth {
            state
            reason
          }
        }
      }
      ... on Brightness {
        timeOfSample
        timeOfLastChange
        brightnessStateValue
      }
      ... on BurglaryAlarm {
        timeOfSample
        timeOfLastChange
        burglaryAlarmValue
      }
      ... on CarbonMonoxideAlarm {
        timeOfSample
        timeOfLastChange
        carbonMonoxideAlarmValue
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
      ... on CurrentProgram {
        timeOfSample
        timeOfLastChange
        currentProgramValue {
          value
        }
      }
      ... on CustomYaleDoorState {
        timeOfSample
        timeOfLastChange
        customYaleDoorStateValue {
          value
        }
      }
      ... on CustomYaleLockState {
        timeOfSample
        timeOfLastChange
        customYaleLockStateValue {
          value
        }
      }
      ... on CustomYaleOneTouchLocking {
        timeOfSample
        timeOfLastChange
        customYaleOneTouchLockingValue {
          value
        }
      }
      ... on CustomYaleOperatingMode {
        timeOfSample
        timeOfLastChange
        customYaleOperatingModeValue {
          value
        }
      }
      ... on CustomYaleSoundVolume {
        timeOfSample
        timeOfLastChange
        customYaleSoundVolumeValue {
          value
        }
      }
      ... on DelayState {
        timeOfSample
        timeOfLastChange
        delayStateValue {
          state
          delayInSeconds
          playlistId
          playOrder {
            assetId
            loopCount
            loopPauseInMilliseconds
          }
        }
      }
      ... on DemandResponseEventStatus {
        timeOfSample
        timeOfLastChange
        eventStatusValue {
          eventId
          status
          activeSignals {
            name
            currentInterval
          }
        }
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
      ... on DeviceUsageMeterElectricityReading {
        timeOfSample
        timeOfLastChange
        value
      }
      ... on DeviceUsageMeterNaturalGasReading {
        timeOfSample
        timeOfLastChange
        value
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
      ... on FireAlarm {
        timeOfSample
        timeOfLastChange
        fireAlarmValue
      }
      ... on GenericFeatureProperty {
        timeOfSample
        timeOfLastChange
        genericValue
      }
      ... on HvacAuxiliaryHeaterStage {
        timeOfSample
        timeOfLastChange
        auxiliaryHeaterStageValue {
          value
        }
      }
      ... on HvacCoolerStage {
        timeOfSample
        timeOfLastChange
        coolerStageValue {
          value
        }
      }
      ... on HvacFanStage {
        timeOfSample
        timeOfLastChange
        fanStageValue {
          value
        }
      }
      ... on HvacPrimaryHeaterStage {
        timeOfSample
        timeOfLastChange
        primaryHeaterStageValue {
          value
        }
      }
      ... on Illuminance {
        illuminanceValue {
          value
        }
        timeOfSample
        timeOfLastChange
      }
      ... on Lock {
        timeOfSample
        timeOfLastChange
        lockState
      }
      ... on Mode {
        timeOfSample
        timeOfLastChange
        modeValue {
          value
        }
      }
      ... on NetworkThroughput {
        timeOfSample
        timeOfLastChange
        networkThroughputValue {
          quality
          bitsPerSecond
        }
      }
      ... on OperationalState {
        timeOfSample
        timeOfLastChange
        operationalStateValue {
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
      ... on RadioDiagnostics {
        timeOfSample
        timeOfLastChange
        radioDiagnosticsValue {
          values {
            radioType
            signalStrength {
              quality
              rssiInDBM
            }
            signalToNoiseRatio {
              quality
              snrInDB
            }
          }
        }
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
      ... on SirenState {
        timeOfSample
        timeOfLastChange
        sirenStateValue {
          state
          playlistId
          playOrder {
            assetId
            loopCount
            loopPauseInMilliseconds
          }
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
      ... on WaterAlarm {
        timeOfSample
        timeOfLastChange
        waterAlarmValue
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
      ... on ConsentRequirementsConfiguration {
        consents {
          name
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
      ... on RecordingProviderConfiguration {
        isAvailable
        recordingUnavailabilityReason: unavailabilityReason
        recordingFeatures {
          __typename
          name
        }
        supportedProtocols
        retentionPeriodInHours
      }
      ... on SceneDescriptionProviderConfiguration {
        isAvailable
        sceneDescriptionUnavailabilityReason: unavailabilityReason
        supportedLocales
        supportedCapabilitiesConfig {
          capabilityName
        }
        supportedRetrievalQueryTypes
      }
      ... on SecurityPanelAlertConfiguration {
        alerts {
          defaultPlaylistId
          type
        }
        assets {
          id
          url
        }
        playlists {
          id
          playOrder {
            assetId
            loopCount
            loopPauseInMilliseconds
          }
        }
      }
      ... on SecurityPanelConfiguration {
        supportedAuthorizationTypes {
          type
        }
        supportedArmStates {
          value
        }
      }
      ... on SimpleEventSourceConfiguration {
        simpleEventSourceSupportedEvents: supportedEvents {
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
      ... on VideoSearchConfiguration {
        isAvailable
        unavailabilityReason
      }
    }
    semantics {
      __typename
      ... on GenericSemantics {
        genericValue
      }
      ... on StatusCodeSemantics {
        codeToStatusesMappings {
          code
          statuses
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
