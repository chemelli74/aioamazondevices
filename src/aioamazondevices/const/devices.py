"""aioamazondevices devices."""

from .http import AMAZON_DEVICE_TYPE

SPEAKER_GROUP_DEVICE_TYPE = "A3C9PE6TNYLTCH"
SPEAKER_GROUP_FAMILY = "WHA"
SPEAKER_GROUP_MODEL = "Speaker Group"

DEVICE_TO_IGNORE: list[str] = [
    AMAZON_DEVICE_TYPE,  # Alexa App for iOS
    "A2TF17PFR55MTB",  # Alexa App for Android
    "A1RTAM01W29CUP",  # Alexa App for PC
    "A18BI6KPKDOEI4",  # ecobee4 Smart Thermostat with Built-in Alexa - issue #199
    "A21Z3CGI8UIP0F",  # Denon AVR-X1600H - issue #253
    "A15ERDAKK5HQQG",  # unsupported Sonos devices - issue #257
    "A3GZUE7F9MEB4U",  # Sony headset WH-1000XM3 - issue #269
    "A23ZD3FSVQM5EE",  # Sony headset WH-1000XM2 - issue #326
    "A7S41FQ5TWBC9",  # Sony headset WH-1000XM4 - issue #327
    "A1L4KDRIILU6N9",  # Sony headset WH-CH700N  - issue #345
    "A2IJJ9QXVOSYK0",  # JBL TUNE770NC - issue #391
    "AKOAGQTKAS9YB",  # Amazon Echo Connect - issue #406
    "A3PAHYZLPKL73D",  # EERO 6 Wifi AP - issue #426
    "A3KOTUS4DKHU1W",  # Samsung Fridge - issue #429
    "AN630UQPG2CA4",  # Insignia TV - issue #430
    "A3SSG6GR8UU7SN",  # Amazon Echo Sub - issue #437
    "A2Y04QPFCANLPQ",  # Bose QuietComfort 35 II - issue #476
    "AYHO3NTIQQ04G",  # Nextbase 622GW Dash Cam - issue #477
    "AHL4H6CKH3AUP",  # BMW Car System - issue #478
    "A3BW5ZVFHRCQPO",  # BMW Mini Car System - issue #479
    "A133UZ2CB0IB8",  # Sony Soundbar Sony HT-A5000 - issue #486
    "A2M9HB23M9MSSM",  # Smartwatch Amazfit Bip U Pro - issue #507
    "A1P7E7V3FCZKU6",  # Toshiba Corporation TV 32LF221U19 - issue #531
    "A1NPP2J03FTS0I",  # Eero Pro 6 - issue #602
    "A14AIWB3T3AS1Z",  # Samsung Soundbar HW-Q950A - issue #603
    "APHEAY6LX7T13",  # Samsung Refrigerator RS22T5561SR/AA - issue #577
]
