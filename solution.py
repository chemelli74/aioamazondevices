# Custom patch to register Alexa group device types (place in your custom_components/aioamazondevices/__init__.py)
from aioamazondevices.device import Device
from aioamazondevices.type import DeviceType

# Define a generic “Group” device type
GroupDeviceType = DeviceType(
    identificator="group",
    display_name="Alexa Group",
    supports_speak=False,
    supports_announce=False,
)

# Register the device IDs that belong to your groups
GROUP_DEVICE_IDS = [
    "A3C9PE6TNYLTCH",   # Überall
    "AP1F6KUH00XPV",     # Soundsystem
]

for dev_id in GROUP_DEVICE_IDS:
    Device.register_device_type(
        device_id=dev_id,
        device_type=GroupDeviceType
    )