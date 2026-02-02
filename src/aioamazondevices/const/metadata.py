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
    "connectivity": {
        "name": "reachability",
        "key": "reachabilityStatusValue",
        "subkey": None,
        "scale": None,
    },
    "range": {
        "name": "rangeValue",
        "key": "rangeValue",
        "subkey": "value",
        "scale": None,
    },
}

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


ALEXA_INFO_SKILLS = {
    "alexa_calendar_today": "Alexa.Calendar.PlayToday",
    "alexa_calendar_tomorrow": "Alexa.Calendar.PlayTomorrow",
    "alexa_calendar_next": "Alexa.Calendar.PlayNext",
    "alexa_date": "Alexa.Date.Play",
    "alexa_time": "Alexa.Time.Play",
    "alexa_nationalnews": "Alexa.News.NationalNews",
    "alexa_flashbriefing": "Alexa.FlashBriefing.Play",
    "alexa_traffic": "Alexa.Traffic.Play",
    "alexa_weather": "Alexa.Weather.Play",
    "alexa_cleanup": "Alexa.CleanUp.Play",
    "alexa_goodmorning": "Alexa.GoodMorning.Play",
    "alexa_singasong": "Alexa.SingASong.Play",
    "alexa_funfact": "Alexa.FunFact.Play",
    "alexa_joke": "Alexa.Joke.Play",
    "alexa_tellstory": "Alexa.TellStory.Play",
    "alexa_imhome": "Alexa.ImHome.Play",
    "alexa_goodnight": "Alexa.GoodNight.Play",
}

MAX_CUSTOMER_ACCOUNT_RETRIES = 3
