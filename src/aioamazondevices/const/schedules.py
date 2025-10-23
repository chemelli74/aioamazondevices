"""aioamazondevices: schedules."""

NOTIFICATION_ALARM = "Alarm"
NOTIFICATION_MUSIC_ALARM = "MusicAlarm"
NOTIFICATION_REMINDER = "Reminder"
NOTIFICATION_TIMER = "Timer"

RECURRING_PATTERNS: dict[str, str] = {
    "XXXX-WD": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    "XXXX-WE": "FREQ=WEEKLY;BYDAY=SA,SU",
    "XXXX-WXX-1": "FREQ=WEEKLY;BYDAY=MO",
    "XXXX-WXX-2": "FREQ=WEEKLY;BYDAY=TU",
    "XXXX-WXX-3": "FREQ=WEEKLY;BYDAY=WE",
    "XXXX-WXX-4": "FREQ=WEEKLY;BYDAY=TH",
    "XXXX-WXX-5": "FREQ=WEEKLY;BYDAY=FR",
    "XXXX-WXX-6": "FREQ=WEEKLY;BYDAY=SA",
    "XXXX-WXX-7": "FREQ=WEEKLY;BYDAY=SU",
}

WEEKEND_EXCEPTIONS = {
    "TH-FR": {
        "XXXX-WD": "FREQ=WEEKLY;BYDAY=MO,TU,WE,SA,SU",
        "XXXX-WE": "FREQ=WEEKLY;BYDAY=TH,FR",
    },
    "FR-SA": {
        "XXXX-WD": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,SU",
        "XXXX-WE": "FREQ=WEEKLY;BYDAY=FR,SA",
    },
}

# Countries grouped by their weekend type
COUNTRY_GROUPS = {
    "TH-FR": ["IR"],
    "FR-SA": [
        "AF",
        "BD",
        "BH",
        "DZ",
        "EG",
        "IL",
        "IQ",
        "JO",
        "KW",
        "LY",
        "MV",
        "MY",
        "OM",
        "PS",
        "QA",
        "SA",
        "SD",
        "SY",
        "YE",
    ],
}
