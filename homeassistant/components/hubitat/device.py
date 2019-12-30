"""Base module for Hubitat devices."""

from typing import Any, Dict, List, Union

from homeassistant.helpers.entity import Entity

from .hubitat import HubitatHub


class HubitatDevice(Entity):
    """A generic Hubitat device."""

    def __init__(self, hub: HubitatHub, device_json: Dict[str, Any]):
        """Initialize a device."""
        self._hub = hub
        self._device: Dict[str, Any] = device_json
        self._id = f"{self._hub.id}:{self._device['id']}"

        self._hub.add_device_listener(
            self._device["id"], self.async_schedule_update_ha_state
        )

    @property
    def unique_id(self):
        """Return a unique for this device."""
        return self._id

    @property
    def name(self):
        """Return the display name of this device."""
        return self._device["label"]

    async def async_update(self):
        """Fetch new data for this device."""
        await self._hub.refresh_device(self._device["id"])

    def async_will_remove_from_hass(self):
        """Run when entity will be removed from hass."""
        self._hub.remove_device_listeners(self._device["id"])

    async def _send_command(self, command: str, *args: List[Union[int, str]]):
        """Send a command to this device."""
        arg = ",".join([str(a) for a in args])
        await self._hub.send_command(self._device["id"], command, arg)

    def _get_attr(self, attr: str):
        """Get the current value of an attribute."""
        dev_attr = self._hub.get_device_attribute(self._device["id"], attr)
        return dev_attr["currentValue"]
