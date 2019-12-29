"""The Hubitat integration."""
import asyncio
from copy import deepcopy
from logging import getLogger
from typing import List

from aiohttp.web import Request
import voluptuous as vol

from homeassistant.components.webhook import async_generate_url
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_HOST, CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant

from .const import CONF_APP_ID, DOMAIN, EVENT_DEVICE
from .hubitat import HubitatHub

_LOGGER = getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

PLATFORMS = ["light"]


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Hubitat component."""

    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data=deepcopy(conf)
        )
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Hubitat from a config entry."""
    # TODO Store an API object for your platforms to access
    # hass.data[DOMAIN][entry.entry_id] = MyApi(...)

    host = entry.data.get(CONF_HOST)
    app_id = entry.data.get(CONF_APP_ID)
    token = entry.data.get(CONF_ACCESS_TOKEN)

    hub = HubitatHub(host, app_id, token)
    hass.data[DOMAIN][entry.entry_id] = Hubitat(hub)

    await hub.set_event_url(async_generate_url(hass, entry.data[CONF_WEBHOOK_ID]))

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    hass.components.webhook.async_register(
        DOMAIN, "Hubitat", entry.data[CONF_WEBHOOK_ID], handle_event
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class Hubitat:
    """Hubitat management class."""

    def __init__(self, hub: HubitatHub):
        """Initialize a Hubitat manager."""
        self.hub = hub
        self.entity_ids: List[int] = []


async def handle_event(hass: HomeAssistant, webhook_id: str, request: Request):
    """Handle an event from the hub."""
    try:
        event = await request.json()
    except ValueError:
        _LOGGER.warning("Invalid message from Hubitat")
        return None

    if isinstance(event, dict):
        event["webhook_id"] = webhook_id

    # Tell everyone else about the event
    hass.bus.async_fire(EVENT_DEVICE, event)
