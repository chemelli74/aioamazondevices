"""aioamazondevices devices."""

from .http import AMAZON_DEVICE_TYPE

SPEAKER_GROUP_FAMILY = "WHA"

DEVICE_TYPE_AQM = "AEZME1X38KDRA"
DEVICE_TYPE_CUBE_GEN3 = "A2JKHJ0PX4J3L3"
DEVICE_TYPE_SPEAKER_GROUP = "A3C9PE6TNYLTCH"

DEVICE_TYPES_HARDCODED_METADATA: dict[str, dict[str, str]] = {
    DEVICE_TYPE_AQM: {
        "model": "Air Quality Monitor",
        "manufacturer": "Amazon",
    },
    DEVICE_TYPE_CUBE_GEN3: {
        "model": "Fire TV Cube (3rd Generation)",
        "manufacturer": "Amazon",
    },
    DEVICE_TYPE_SPEAKER_GROUP: {
        "model": "Speaker Group",
        "manufacturer": "Amazon",
    },
}

DEVICE_TYPES_TO_IGNORE: list[str] = [
    AMAZON_DEVICE_TYPE,  # Alexa App for iOS
    "A133UZ2CB0IB8",  # Sony Soundbar Sony HT-A5000 - issue #486
    "A14AIWB3T3AS1Z",  # Samsung Soundbar HW-Q950A - issue #603
    "A15ERDAKK5HQQG",  # unsupported Sonos devices - issue #257
    "A18BI6KPKDOEI4",  # ecobee4 Smart Thermostat with Built-in Alexa - issue #199
    "A1L4KDRIILU6N9",  # Sony headset WH-CH700N - issue #345
    "A1NPP2J03FTS0I",  # Eero Pro 6 - issue #602
    "A1NQ0LXWBGVQS9",  # Samsung 2012 QLED TV - issue #660
    "A1P7E7V3FCZKU6",  # Toshiba Corporation TV 32LF221U19 - issue #531
    "A1RTAM01W29CUP",  # Alexa App for PC
    "A1X5IB2CRN3E8G",  # Fitbit Versa 3 - issue #651
    "A21Z3CGI8UIP0F",  # Denon AVR-X1600H - issue #253
    "A23ZD3FSVQM5EE",  # Sony headset WH-1000XM2 - issue #326
    "A2IJJ9QXVOSYK0",  # JBL TUNE770NC - issue #391
    "A2M9HB23M9MSSM",  # Smartwatch Amazfit Bip U Pro - issue #507
    "A2QDHDQIWC2LTG",  # Echo Buds (Left) - issue #515
    "A2TF17PFR55MTB",  # Alexa App for Android
    "A2Y04QPFCANLPQ",  # Bose QuietComfort 35 II - issue #476
    "A31PMVIWCRNTX2",  # Echo Buds (Right) - issue #515
    "A3BW5ZVFHRCQPO",  # BMW Mini Car System - issue #479
    "A3GZUE7F9MEB4U",  # Sony headset WH-1000XM3 - issue #269
    "A3HVREY4JWAZ6K",  # Echo Buds (Charger) - issue #515
    "A3KOTUS4DKHU1W",  # Samsung Fridge - issue #429
    "A3PAHYZLPKL73D",  # EERO 6 Wifi AP - issue #426
    "A3SSG6GR8UU7SN",  # Amazon Echo Sub - issue #437
    "A7S41FQ5TWBC9",  # Sony headset WH-1000XM4 - issue #327
    "AHL4H6CKH3AUP",  # BMW Car System - issue #478
    "AKOAGQTKAS9YB",  # Amazon Echo Connect - issue #406
    "AN630UQPG2CA4",  # Insignia TV - issue #430
    "APHEAY6LX7T13",  # Samsung Refrigerator RS22T5561SR/AA - issue #577
    "AYHO3NTIQQ04G",  # Nextbase 622GW Dash Cam - issue #477
]
