"""aioamazondevices Additional entities const."""

SENSOR_STATE_OFF = "NOT_DETECTED"

SENSORS: dict[str, dict[str, str | None]] = {
    "temperatureSensor": {
        "name": "temperature",
        "key": "value",
        "subkey": "value",
        "scale": "scale",
    },
    "motionSensor": {
        "name": "detectionState",
        "key": "detectionStateValue",
        "subkey": None,
        "scale": None,
    },
    "lightSensor": {
        "name": "illuminance",
        "key": "illuminanceValue",
        "subkey": "value",
        "scale": None,
    },
    "range": {
        "name": "rangeValue",
        "key": "rangeValue",
        "subkey": "value",
        "scale": None,
    },
}

AQM_DEVICE_TYPE = "AEZME1X38KDRA"
AQM_RANGE_SENSORS: dict[str, dict[str, str | None]] = {
    "4": {
        "name": "Humidity",
        "scale": "%",
    },
    "5": {
        "name": "VOC",
        "scale": None,
    },
    "6": {
        "name": "PM25",
        "scale": "MicroGramsPerCubicMeter",
    },
    "7": {
        "name": "PM10",
        "scale": "MicroGramsPerCubicMeter",
    },
    "8": {
        "name": "CO",
        "scale": "ppm",
    },
    "9": {
        "name": "Air Quality",
        "scale": None,
    },
}


ALEXA_INFO_SKILLS = [
    "Alexa.Calendar.PlayToday",
    "Alexa.Calendar.PlayTomorrow",
    "Alexa.Calendar.PlayNext",
    "Alexa.Date.Play",
    "Alexa.Time.Play",
    "Alexa.News.NationalNews",
    "Alexa.FlashBriefing.Play",
    "Alexa.Traffic.Play",
    "Alexa.Weather.Play",
    "Alexa.CleanUp.Play",
    "Alexa.GoodMorning.Play",
    "Alexa.SingASong.Play",
    "Alexa.FunFact.Play",
    "Alexa.Joke.Play",
    "Alexa.TellStory.Play",
    "Alexa.ImHome.Play",
    "Alexa.GoodNight.Play",
]

MAX_CUSTOMER_ACCOUNT_RETRIES = 3
