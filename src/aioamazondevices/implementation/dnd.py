"""Module to handle Alexa do not disturb setting."""

from http import HTTPMethod

from aioamazondevices.const.http import URI_DND_STATUS_ALL, URI_DND_STATUS_DEVICE
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import AmazonDevice, AmazonDeviceSensor


class AmazonDnDHandler:
    """Class to handle Alexa Do Not Disturb functionality."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
    ) -> None:
        """Initialize AmazonDnDHandler class."""
        self._session_state_data = session_state_data
        self._http_wrapper = http_wrapper

    async def get_do_not_disturb_status(self) -> dict[str, AmazonDeviceSensor]:
        """Get do_not_disturb status for all devices."""
        dnd_status: dict[str, AmazonDeviceSensor] = {}
        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.GET,
            url=f"https://alexa.amazon.{self._session_state_data.domain}{URI_DND_STATUS_ALL}",
        )

        dnd_data = await self._http_wrapper.response_to_json(raw_resp, "dnd")

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

    async def set_do_not_disturb(self, device: AmazonDevice, enable: bool) -> None:
        """Set do_not_disturb flag."""
        payload = {
            "deviceSerialNumber": device.serial_number,
            "deviceType": device.device_type,
            "enabled": enable,
        }
        url = f"https://alexa.amazon.{self._session_state_data.domain}{URI_DND_STATUS_DEVICE}"
        await self._http_wrapper.session_request(
            method=HTTPMethod.PUT,
            url=url,
            input_data=payload,
            json_data=True,
        )
