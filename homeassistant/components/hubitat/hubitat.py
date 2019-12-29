"""Hubitat API."""
from asyncio import gather
from enum import Enum
from logging import getLogger
from typing import Any, Callable, Dict, List, Optional, Union

from aiohttp import ClientTimeout, request
from bs4 import BeautifulSoup
import voluptuous as vol

_LOGGER = getLogger(__name__)


Listener = Callable[[], None]

DEVICE_TYPE = Enum("DeviceType", "DIMMER SWITCH SENSOR")

DEVICE_SCHEMA = vol.Schema({"id": str, "name": str, "label": str}, required=True)

ATTRIBUTE_SCHEMA = vol.Schema(
    {
        "name": str,
        "dataType": vol.Any(str, None),
        vol.Optional("currentValue"): vol.Any(str, int),
        vol.Optional("values"): vol.Any([str], [int]),
    },
    required=True,
)

CAPABILITY_SCHEMA = vol.Schema(
    vol.Any(str, vol.Schema({"attributes": [ATTRIBUTE_SCHEMA]}, required=True,),)
)

DEVICE_INFO_SCHEMA = vol.Schema(
    {
        "id": str,
        "name": str,
        "label": str,
        "attributes": [ATTRIBUTE_SCHEMA],
        "capabilities": [CAPABILITY_SCHEMA],
        "commands": [str],
    },
    required=True,
)

CAPABILITIES_SCHEMA = vol.Schema({"capabilities": [CAPABILITY_SCHEMA]}, required=True)

COMMAND_SCHEMA = vol.Schema({"command": str, "type": [str]}, required=True)

COMMANDS_SCHEMA = vol.Schema([COMMAND_SCHEMA])


class HubitatHub:
    """A representation of a Hubitat hub."""

    def __init__(self, host: str, app_id: str, access_token: str):
        """Initialize a Hubitat hub connector."""
        if not host:
            raise InvalidConfig('Missing "host"')
        if not app_id:
            raise InvalidConfig('Missing "app_id"')
        if not access_token:
            raise InvalidConfig('Missing "access_token"')

        self.host = host
        self.app_id = app_id
        self.token = access_token

        self.api = f"http://{host}/apps/api/{app_id}"
        self.devices: Dict[str, Any]
        self.info: Dict[str, str]

        self.listeners: Dict[str, List[Listener]] = {}

        _LOGGER.info(f"Created hub pointing to {self.api}")

    async def connect(self):
        """
        Connect to the hub and download initial state data.

        Hub and device data will not be available until this method has
        completed
        """
        await gather(self._load_info(), self._load_devices())

    def update_state(self, event: Dict[str, Any]):
        """Update the hub's state with an event received from the hub."""
        pass

    async def send_command(
        self, device_id: str, command: str, arg: Optional[Union[str, int]]
    ):
        """Send a device command to the hub."""
        url = f"http://{self.api}/devices/{device_id}/{command}"
        if arg:
            url += f"/{arg}"
        async with request("GET", url) as resp:
            return await resp.text()

    async def get_device_attribute(
        self, device_id: str, attr_name: str
    ) -> Dict[str, Any]:
        """Get an attribute value for a specific device."""
        state = self.devices[device_id]
        for attr in state["attributes"]:
            if attr["name"] == attr_name:
                return attr
        raise InvalidAttribute

    async def set_event_url(self, event_url: str):
        """Set the URL that Hubitat will POST events to."""
        params = {"access_token": self.token}
        _LOGGER.info(f"Posting update to {self.api}/postURL/{event_url}")
        async with request(
            "POST", f"{self.api}/postURL/{event_url}", params=params
        ) as resp:
            return await resp.json()

    async def _load_info(self):
        """Load general info about the hub."""
        url = f"http://{self.host}/hub/edit"
        _LOGGER.info(f"Getting hub info from {url}...")
        timeout = ClientTimeout(total=10)
        async with request("GET", url, timeout=timeout) as resp:
            text = await resp.text()
            soup = BeautifulSoup(text, "html.parser")
            section = soup.find("h2", string="Hub Details")
            self.info = _parse_details(section)
            _LOGGER.debug(f"Hub info: {self.devices}")

    async def _load_devices(self, force_refresh=False):
        """Load the current state of all devices."""
        if force_refresh or len(self.devices) == 0:
            params = {"access_token": self.token}
            async with request("GET", f"{self.api}/devices", params=params) as resp:
                devices = DEVICE_SCHEMA(await resp.json())

            # load devices sequentially to avoid overloading the hub
            for dev in devices:
                state = await self._load_device(dev["id"], force_refresh)
                self.devices[dev["id"]] = state

    async def _load_device(self, device_id: str, force_refresh=False):
        """
        Return full info for a specific device.

        {
            "id": "1922",
            "name": "Generic Z-Wave Smart Dimmer",
            "label": "Bedroom Light",
            "attributes": [
                {
                    "dataType": "NUMBER",
                    "currentValue": 10,
                    "name": "level"
                },
                {
                    "values": ["on", "off"],
                    "name": "switch",
                    "currentValue": "on",
                    "dataType": "ENUM"
                }
            ],
            "capabilities": [
                "Switch",
                {"attributes": [{"name": "switch", "currentValue": "off", "dataType": "ENUM", "values": ["on", "off"]}]},
                "Configuration",
                "SwitchLevel"
                {"attributes": [{"name": "level", "dataType": null}]}
            ],
            "commands": [
                "configure",
                "flash",
                "off",
                "on",
                "refresh",
                "setLevel"
            ]
        ]
        """
        if force_refresh or device_id not in self.devices:
            params = {"access_token": self.token}
            async with request(
                "GET", f"{self.api}/devices/{device_id}", params=params
            ) as resp:
                self.devices[device_id] = DEVICE_INFO_SCHEMA(await resp.json())
        return self.devices[device_id]


_DETAILS_MAPPING = {
    "Hubitat Elevation® Platform Version": "sw_version",
    "Hardware Version": "hw_version",
    "Hub UID": "id",
    "IP Address": "address",
    "MAC Address": "mac",
}


def _parse_details(tag):
    """Parse hub details from HTML."""
    details: Dict[str, str] = {}
    group = tag.find_next_sibling("div")
    while group is not None:
        heading = group.find("div", class_="menu-header").text.strip()
        content = group.find("div", class_="menu-text").text.strip()
        if heading in _DETAILS_MAPPING:
            details[_DETAILS_MAPPING[heading]] = content
        group = group.find_next_sibling("div")
    return details


class InvalidConfig(Exception):
    """An error indicating invalid hub config data."""

    pass


class InvalidAttribute(Exception):
    """An error indicating an invalid device attribute."""

    pass
