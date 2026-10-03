"""AquaCal TropiCal heat pumps via the PoolSync cloud."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TropicApiClient, TropicApiError, TropicAuthError
from .coordinator import TropicCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.SENSOR]

type TropicConfigEntry = ConfigEntry[dict[str, TropicCoordinator]]


async def async_setup_entry(hass: HomeAssistant, entry: TropicConfigEntry) -> bool:
    client = TropicApiClient(
        async_get_clientsession(hass), entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
    )
    try:
        serials = await client.async_get_tropic_serials()
    except TropicAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except TropicApiError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinators: dict[str, TropicCoordinator] = {}
    for serial in serials:
        name = "TropiCal heat pump" if len(serials) == 1 else f"TropiCal heat pump {serial[-4:]}"
        coordinator = TropicCoordinator(hass, entry, client, serial, name)
        await coordinator.async_config_entry_first_refresh()
        coordinators[serial] = coordinator

    entry.runtime_data = coordinators
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: TropicConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TropicConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
