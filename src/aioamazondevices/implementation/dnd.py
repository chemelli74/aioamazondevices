"""Module to handle Alexa do not disturb setting."""

from http import HTTPMethod

from aioamazondevices.const.http import (
    URI_DND,
)
from aioamazondevices.http_wrapper import AmazonHttpWrapper
from aioamazondevices.structures import AmazonDevice, AmazonDeviceSensor


async def get_do_not_disturb_status(
    http_wrapper: AmazonHttpWrapper,
    domain: str,
) -> dict[str, AmazonDeviceSensor]:
    """Get do_not_disturb status for all devices."""
    dnd_status: dict[str, AmazonDeviceSensor] = {}
    _, raw_resp = await http_wrapper.session_request(
        method=HTTPMethod.GET,
        url=f"https://alexa.amazon.{domain}{URI_DND}",
    )

    dnd_data = await http_wrapper.response_to_json(raw_resp, "dnd")

    for dnd in dnd_data.get("doNotDisturbDeviceStatusList", {}):
        dnd_status[dnd.get("deviceSerialNumber")] = AmazonDeviceSensor(
            name="dnd",
            value=dnd.get("enabled"),
            error=False,
            error_type=None,
            error_msg=None,
            scale=None,
        )
    return dnd_status


async def set_do_not_disturb(
    http_wrapper: AmazonHttpWrapper, domain: str, device: AmazonDevice, state: bool
) -> None:
    """Set do_not_disturb flag."""
    payload = {
        "deviceSerialNumber": device.serial_number,
        "deviceType": device.device_type,
        "enabled": state,
    }
    url = f"https://alexa.amazon.{domain}/api/dnd/status"
    await http_wrapper.session_request(
        method=HTTPMethod.PUT,
        url=url,
        input_data=payload,
        json_data=True,
    )
