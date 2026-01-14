"""aioamazondevices devices."""

from .http import AMAZON_DEVICE_TYPE

SPEAKER_GROUP_FAMILY = "WHA"
SPEAKER_GROUP_MODEL = "Speaker Group"
AQM_DEVICE_TYPE = "AEZME1X38KDRA"

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
    "A2QDHDQIWC2LTG",  # Echo Buds (Left) - issue #515
    "A31PMVIWCRNTX2",  # Echo Buds (Right) - issue #515
    "A3HVREY4JWAZ6K",  # Echo Buds (Charger) - issue #515
    "A1P7E7V3FCZKU6",  # Toshiba Corporation TV 32LF221U19 - issue #531
    "APHEAY6LX7T13",  # Samsung Refrigerator RS22T5561SR/AA - issue #577
    "A1NPP2J03FTS0I",  # Eero Pro 6 - issue #602
    "A14AIWB3T3AS1Z",  # Samsung Soundbar HW-Q950A - issue #603
    "A1NQ0LXWBGVQS9",  # Samsung 2012 QLED TV - Issue #660
]

DEVICE_TYPE_TO_MODEL: dict[str, dict[str, str | None]] = {
    "A10A33FOX2NUBK": {
        "model": "Echo Spot",
        "hw_version": "Gen1",
    },
    "A11QM4H9HGV71H": {
        "model": "Echo Show 5",
        "hw_version": "Gen3",
    },
    "A13W6HQIHKEN3Z": {
        "model": "Echo Auto",
        "hw_version": "Gen2",
    },
    "A15996VY63BQ2D": {
        "model": "Echo Show 8",
        "hw_version": "Gen2",
    },
    "A18O6U1UQFJ0XK": {
        "model": "Echo Plus",
        "hw_version": "Gen2",
    },
    "A1C66CX2XD756O": {
        "model": "Fire Tablet HD 8",
        "hw_version": "Gen8",
    },
    "A1EIANJ7PNB0Q7": {
        "model": "Echo Show 15",
        "hw_version": "Gen1",
    },
    "A1M0A9L9HDBID3": {
        "manufacturer": "First Alert",
        "model": "Onelink Smoke + Carbon Monoxide Alarm",
        "hw_version": None,
    },
    "A1NL4BVLQ4L3N3": {
        "model": "Echo Show",
        "hw_version": "Gen1",
    },
    "A1Q6UGEXJZWJQ0": {
        "model": "Fire TV Stick 4K",
        "hw_version": "Gen2",
    },
    "A1Q7QCGNMXAKYW": {
        "model": "Fire Tablet 7",
        "hw_version": "Gen9",
    },
    "A1RABVCI4QCIKC": {
        "model": "Echo Dot",
        "hw_version": "Gen3",
    },
    "A1TD5Z1R8IWBHA": {
        "model": "Fire Tablet HD 8",
        "hw_version": "Gen12",
    },
    "A1VGB7MHSIEYFK": {
        "model": "Fire TV Cube",
        "hw_version": "Gen3",
    },
    "A1WAR447VT003J": {
        "manufacturer": "Yamaha",
        "model": "RX A4 Aventage",
        "hw_version": None,
    },
    "A1WZKXFLI43K86": {
        "model": "FireTV 4k MAX",
        "hw_version": "Gen2",
    },
    "A1X92YQU8MWAPD": {
        "manufacturer": "Devialet",
        "model": "Freebox Delta",
        "hw_version": None,
    },
    "A1XWJRHALS1REP": {
        "model": "Echo Show 5",
        "hw_version": "Gen2",
    },
    "A1Z88NGR2BK6A2": {
        "model": "Echo Show 8",
        "hw_version": "Gen1",
    },
    "A1ZOM3H3U20BL8": {
        "manufacturer": "Medion",
        "model": "Life P66970",
        "hw_version": "A16",
    },
    "A20E9PVI3HANVQ": {
        "manufacturer": "Marshall",
        "model": "Marshall Uxbridge",
    },
    "A25521KS9QCAMD": {
        "model": "Fire Tablet HD 7",
        "hw_version": "Gen4",
    },
    "A265XOI9586NML": {
        "model": "Fire TV Stick with Alexa Voice Remote",
        "hw_version": None,
    },
    "A271DR1789MXDS": {
        "model": "Fire Tablet 7",
        "hw_version": "Gen12",
    },
    "A2DS1Q2TPDJ48U": {
        "model": "Echo Dot Clock",
        "hw_version": "Gen5",
    },
    "A2E0SNTXJVT7WK": {
        "model": "Fire TV Stick",
        "hw_version": "Gen2",
    },
    "A2F7IJUT32OLN4": {
        "manufacturer": "Samsung Electronics Co., Ltd.",
        "model": "Soundbar Q990D",
        "hw_version": None,
    },
    "A2GFL5ZMWNE0PX": {
        "model": "Fire TV Stick",
        "hw_version": "Gen3",
    },
    "A2H4LV5GIZ1JFT": {
        "model": "Echo Dot Clock",
        "hw_version": "Gen4",
    },
    "A2JKHJ0PX4J3L3": {
        "model": "Fire TV Cube",
        "hw_version": "Gen2",
    },
    "A2LWARUGJLBYEW": {
        "model": "Fire TV Stick",
        "hw_version": "Gen2",
    },
    "A2M35JJZWCQOMZ": {
        "model": "Echo Plus",
        "hw_version": "Gen1",
    },
    "A2M4YX06LWP8WI": {
        "model": "Fire Tablet 7",
        "hw_version": "Gen5",
    },
    "A2N49KXGVA18AR": {
        "model": "Fire Tablet HD 10 Plus",
        "hw_version": "Gen11",
    },
    "A2OSP3UA4VC85F": {
        "manufacturer": "Sonos Inc.",
        "model": "Sonos One",
        "hw_version": "Gen1",
    },
    "A2RG3FY1YV97SS": {
        "manufacturer": "Sonos Inc.",
        "model": "Sonos Move",
        "hw_version": "Gen1",
    },
    "A2RU4B77X9R9NZ": {
        "model": "Echo Link Amp",
        "hw_version": None,
    },
    "A2U21SRK4QGSE1": {
        "model": "Echo Dot",
        "hw_version": "Gen4",
    },
    "A2UONLFQW0PADH": {
        "model": "Echo Show 8",
        "hw_version": "Gen3",
    },
    "A2Z8O30CD35N8F": {
        "manufacturer": "Sonos Inc.",
        "model": "Sonos Arc",
        "hw_version": "Gen1",
    },
    "A303PJF6ISQ7IC": {
        "model": "Echo Auto",
        "hw_version": "Gen1",
    },
    "A30YDR2MK8HMRV": {
        "model": "Echo Dot",
        "hw_version": "Gen3",
    },
    "A31DTMEEVDDOIV": {
        "model": "Fire TV Stick Lite",
        "hw_version": "Gen1",
    },
    "A32DDESGESSHZA": {
        "model": "Echo Dot",
        "hw_version": "Gen3",
    },
    "A32DOYMUN6DTXA": {
        "model": "Echo Dot",
        "hw_version": "Gen3",
    },
    "A33S43L213VSHQ": {
        "model": "Smart TV 4K",
        "hw_version": "4 Series",
    },
    "A38949IHXHRQ5P": {
        "model": "Echo Tap",
        "hw_version": "Gen1",
    },
    "A39OV95SPFQ9YG": {
        "manufacturer": "Sonos Inc.",
        "model": "Sonos Era 100",
        "hw_version": None,
    },
    "A3C9PE6TNYLTCH": {
        "model": "Speaker Group",
        "hw_version": None,
    },
    "A3EH2E0YZ30OD6": {
        "model": "Echo Spot",
        "hw_version": "Gen2",
    },
    "A3EVMLQTU6WL1W": {
        "model": "FireTV 4k MAX",
        "hw_version": "Gen1",
    },
    "A3FX4UWTP28V1P": {
        "model": "Echo",
        "hw_version": "Gen3",
    },
    "A3HF4YRA2L7XGC": {
        "model": "Fire TV Cube",
        "hw_version": "Gen1",
    },
    "A3HND3J60V1OXX": {
        "model": "Echo Loop",
        "hw_version": None,
    },
    "A3NPD82ABCPIDP": {
        "manufacturer": "Sonos Inc.",
        "model": "Sonos Beam",
        "hw_version": None,
    },
    "A3RBAYBE7VM004": {
        "model": "Echo Studio",
        "hw_version": None,
    },
    "A3RMGO6LYLH7YN": {
        "model": "Echo",
        "hw_version": "Gen4",
    },
    "A3S5BH2HU6VAYF": {
        "model": "Echo Dot",
        "hw_version": "Gen2",
    },
    "A3VRME03NAXFUB": {
        "model": "Echo Flex",
        "hw_version": None,
    },
    "A4ZP7ZC4PI6TO": {
        "model": "Echo Show 5",
        "hw_version": "Gen1",
    },
    "A4ZXE0RM7LQ7A": {
        "model": "Echo Dot",
        "hw_version": "Gen5",
    },
    "A50R5P5LEX87M ": {
        "manufacturer": "JBL",
        "model": "JBL BAR 500",
        "hw_version": None,
    },
    "A7WXQPH584YP": {
        "model": "Echo",
        "hw_version": "Gen2",
    },
    "AB72C64C86AW2": {
        "model": "Echo",
        "hw_version": "Gen2",
    },
    "AD2YUJTRVBNOF": {
        "manufacturer": "Sony Group Corporation",
        "model": "HT-Z9F",
        "hw_version": None,
    },
    "ADMKNMEVNL158": {
        "model": "Echo Hub",
        "hw_version": "Gen1",
    },
    "ADOUDFQX2QVX0": {
        "model": "Fire TV Omni QLED",
        "hw_version": None,
    },
    "ADVBD696BHNV5": {
        "model": "Fire TV Stick",
        "hw_version": "Gen1",
    },
    "AECNEXTDY5AD9": {
        "manufacturer": "Cozyla",
        "model": "Frame with Alexa",
        "hw_version": None,
    },
    "AIPK7MM90V7TB": {
        "model": "Echo Show 10",
        "hw_version": "Gen3",
    },
    "AKNO1N0KSFN8L": {
        "model": "Echo Dot",
        "hw_version": "Gen1",
    },
    "AKPGW064GI9HE": {
        "model": "Fire TV Stick 4K",
        "hw_version": "Gen1",
    },
    "AP1F6KUH00XPV": {
        "model": "Echo Stereo Pair",
        "hw_version": "Virtual",
    },
    "AQ24620N8QD5Q": {
        "model": "Echo Show 15",
        "hw_version": "Gen2",
    },
    "ASQZWP4GPYUT7": {
        "model": "Echo pop",
        "hw_version": "Gen1",
    },
    "ATNLRCEBX3W4P": {
        "model": "Fire Tablet HD 10",
        "hw_version": "Gen11",
    },
    "AU3ZY84EWI70R": {
        "manufacturer": "Medion",
        "model": "Life P61142",
        "hw_version": "A16",
    },
    "AUPUQSVCVHXP0": {
        "manufacturer": "ecobee Inc.",
        "model": "ecobee Switch+",
        "hw_version": None,
    },
    "AVD3HM0HOJAAL": {
        "manufacturer": "Sonos Inc.",
        "model": "Sonos One",
        "hw_version": "Gen2",
    },
    "AVU7CPPF2ZRAS": {
        "model": "Fire Tablet HD 8 Plus",
        "hw_version": "Gen10",
    },
    "AWZZ5CVHX2CD": {
        "model": "Echo Show",
        "hw_version": "Gen2",
    },
    "G2A0V704840708AP": {
        "model": "Echo Plus",
        "hw_version": "Gen2",
    },
    "A1JJ0KFC4ZPNJ3": {
        "model": "Echo Input",
        "hw_version": "Gen1",
    },
    "A2V9UEGZ82H4KZ": {
        "model": "Fire Tablet HD 10",
        "hw_version": "Gen13",
    },
    "ALCIV0P5M8TZ0": {
        "manufacturer": "Sonos Inc.",
        "model": "Sonos Beam",
        "hw_version": None,
    },
    "A1MKGHX5VQBDWX": {
        "manufacturer": "Denon",
        "model": "Denon Home 150",
        "hw_version": None,
    },
    "A2X8WT9JELC577": {
        "manufacturer": "ecobee Inc.",
        "model": "ecobee 4 Smart Thermostat with Voice Control",
        "hw_version": None,
    },
    "AA1IN44SS3X6O": {
        "manufacturer": "ecobee Inc.",
        "model": "ecobee SmartThermostat Premium",
        "hw_version": None,
    },
    "A2ZJ8HST6J24XH": {
        "manufacturer": "Sonos Inc.",
        "model": "Sonos Roam 2",
        "hw_version": None,
    },
    "A3M91KUSTM6A3P": {
        "manufacturer": "Ford",
        "model": "Ford SYNC 4",
        "hw_version": None,
    },
    "A1J16TEDOYCZTN": {
        "model": "Fire Tablet 7",
        "hw_version": "Gen7",
    },
    "A18TCD9FP10WJ9": {
        "manufacturer": "Netgear",
        "model": "Orbi Voice (RBS40V)",
        "hw_version": None,
    },
    AQM_DEVICE_TYPE: {
        "model": "Air Quality Monitor",
        "hw_version": "Gen1",
    },
    "A1MR3F8QRZNAXI": {
        "model": "Echo Dot Max",
        "hw_version": "Gen1",
    },
    "A1XULUOD31VLF4": {
        "manufacturer": "Broan-NuTone LLC",
        "model": "Bathroom Fan with Alexa (VC110CCT)",
        "hw_version": None,
    },
    "A15QWUTQ6FSMYX": {
        # This appears to be a group for both speakers
        # but four devices show this device type (see issue #515)
        "model": "Echo Buds",
        "hw_version": "Gen2",
    },
}
