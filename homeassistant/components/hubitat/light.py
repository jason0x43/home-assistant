"""Support for Hubitat lights."""

from logging import getLogger

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    ATTR_TRANSITION,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR,
    SUPPORT_COLOR_TEMP,
    Light,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.util import color as color_util

from .const import DOMAIN
from .device import HubitatDevice
from .hubitat import (
    CAPABILITY_COLOR_CONTROL,
    CAPABILITY_COLOR_TEMP,
    CAPABILITY_SWITCH_LEVEL,
    COMMAND_ON,
    COMMAND_SET_COLOR,
    COMMAND_SET_COLOR_TEMP,
    COMMAND_SET_HUE,
    COMMAND_SET_LEVEL,
    COMMAND_SET_SAT,
    HubitatHub,
)

_LOGGER = getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistantType, entry: ConfigEntry, async_add_entities,
):
    """Initialize light devices."""
    hub: HubitatHub = hass.data[DOMAIN][entry.entry_id].hub
    _LOGGER.debug(f"Checking for lights in {hub.devices}")
    lights = [HubitatLight(hub, d) for d in hub.devices.values() if _is_light(d)]
    async_add_entities(lights)
    _LOGGER.debug(f"Added entities for lights: {lights}")


LIGHT_CAPABILITIES = ["SwitchLevel", "ColorControl"]


def _is_light(device):
    """Return true if device is a light."""
    return any(cap in device["capabilities"] for cap in LIGHT_CAPABILITIES)


class HubitatLight(HubitatDevice, Light):
    """Representation of a Hubitat light."""

    should_poll = False

    @property
    def brightness(self):
        """Return the level of this light."""
        return int(255 * int(self._get_attr("level")) / 100)

    @property
    def hs_color(self):
        """Return the hue and saturation color value [float, float]."""
        hue = int(self._get_attr("hue"))
        sat = int(self._get_attr("saturation"))
        hass_hue = 360 * hue / 100
        return [hass_hue, sat]

    @property
    def color_temp(self):
        """Return the CT color value in mireds."""
        temp = int(self._get_attr("colorTemperature"))
        mireds = color_util.color_temperature_kelvin_to_mired(temp)
        return mireds

    @property
    def is_on(self):
        """Return True if the light is on."""
        _LOGGER.debug(f"Checking if light {self.name} is on")
        return self._get_attr("switch") == "on"

    @property
    def supported_features(self):
        """Return supported feature flags."""
        features = 0
        caps = self._device["capabilities"]

        if CAPABILITY_COLOR_CONTROL in caps:
            features |= SUPPORT_COLOR
        if CAPABILITY_COLOR_TEMP in caps:
            features |= SUPPORT_COLOR_TEMP
        if CAPABILITY_SWITCH_LEVEL in caps:
            features |= SUPPORT_BRIGHTNESS

        return features

    @property
    def device_info(self):
        """Return the device info."""
        return {
            "identifiers": {(DOMAIN, self.device_id)},
            "name": self.name,
            "manufacturer": "Hubitat",
            "model": self.type,
            "via_device": (DOMAIN, self._hub.id),
        }

    def supports_feature(self, feature):
        """Return True if light supports a given feature."""
        return self.supported_features & feature != 0

    async def async_turn_on(self, **kwargs):
        """Turn on the light."""
        _LOGGER.debug(f"Turning on {self.name} with {kwargs}")

        props = {}

        if ATTR_BRIGHTNESS in kwargs and self.supports_feature(SUPPORT_BRIGHTNESS):
            props["level"] = int(100 * kwargs[ATTR_BRIGHTNESS] / 255)

        if ATTR_TRANSITION in kwargs:
            props["time"] = kwargs[ATTR_TRANSITION]

        if ATTR_HS_COLOR in kwargs and self.supports_feature(SUPPORT_COLOR):
            # Hubitat hue is from 0 - 100
            props["hue"] = int(100 * kwargs[ATTR_HS_COLOR][0] / 360)
            props["sat"] = kwargs[ATTR_HS_COLOR][1]

        if ATTR_COLOR_TEMP in kwargs and self.supports_feature(SUPPORT_COLOR_TEMP):
            mireds = kwargs[ATTR_COLOR_TEMP]
            props["temp"] = color_util.color_temperature_mired_to_kelvin(mireds)

        if "level" in props:
            if "time" in props:
                await self._send_command(
                    COMMAND_SET_LEVEL, props["level"], props["time"]
                )
                del props["time"]
            elif "hue" in props:
                await self._send_command(
                    COMMAND_SET_COLOR, props["hue"], props["sat"], props["level"]
                )
                del props["hue"]
                del props["sat"]
            else:
                await self._send_command(COMMAND_SET_LEVEL, props["level"])

            del props["level"]
        else:
            await self._send_command(COMMAND_ON)

        if "hue" in props:
            await self._send_command(COMMAND_SET_HUE, props["hue"])
            await self._send_command(COMMAND_SET_SAT, props["sat"])
            del props["hue"]
            del props["sat"]

        if "temp" in props:
            await self._send_command(COMMAND_SET_COLOR_TEMP, props["temp"])

    async def async_turn_off(self, **kwargs):
        """Turn off the light."""
        _LOGGER.debug(f"Turning off {self.name}")
        await self._send_command("off")
