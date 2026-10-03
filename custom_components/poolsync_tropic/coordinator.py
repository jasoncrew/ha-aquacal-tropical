"""Polling coordinator for one TropiCal heat pump."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TropicApiClient, TropicApiError, TropicAuthError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class TropicCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches /tropic/<serial> on an interval."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: TropicApiClient,
        serial: str,
        device_name: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{serial}",
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self.serial = serial
        self.device_name = device_name

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.async_get_tropic(self.serial)
        except TropicAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TropicApiError as err:
            raise UpdateFailed(str(err)) from err

    # --- helpers shared by entities -------------------------------------

    @property
    def temperature_unit(self) -> str:
        """Unit the cloud reports this unit's temperatures in.

        The payload carries the setpoint in the account's units next to the
        setpoint limits in Celsius (setpointMin/Max, 8-40). A setpoint above
        the Celsius maximum can only be Fahrenheit (whose minimum is 46).
        """
        data = self.data or {}
        setpoint, sp_max = data.get("setpoint"), data.get("setpointMax")
        if isinstance(setpoint, (int, float)) and isinstance(sp_max, (int, float)):
            if setpoint <= sp_max:
                return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @property
    def temperature_range(self) -> tuple[float, float]:
        data = self.data or {}
        if self.temperature_unit == UnitOfTemperature.CELSIUS:
            return data.get("setpointMin") or 8, data.get("setpointMax") or 40
        return data.get("minTemp") or 46, data.get("maxTemp") or 104

    def mode_names(self, kind: str) -> list[str]:
        """Lower-case names from availableHeatModes / availablePowerModes."""
        names = (self.data or {}).get(f"available{kind.capitalize()}Modes") or []
        return [str(n).lower() for n in names]

    def mode_name(self, kind: str) -> str | None:
        """Map heatMode/powerMode index to its name, e.g. heatMode 2 -> 'heat'."""
        idx = (self.data or {}).get(f"{kind}Mode")
        names = self.mode_names(kind)
        if isinstance(idx, int) and 0 <= idx < len(names):
            return names[idx]
        return None

    def mode_index(self, kind: str, name: str) -> int | None:
        """Map a mode name back to its index, e.g. ('heat', 'cool') -> 3."""
        names = self.mode_names(kind)
        return names.index(name) if name in names else None

    async def async_send(self, changes: dict[str, Any]) -> None:
        """Send a change to the heat pump and reflect it right away."""
        await self.client.async_set_tropic(self.serial, changes)
        # The cloud's GET lags the change, so show the new value now;
        # the next scheduled poll confirms it.
        self.async_set_updated_data({**(self.data or {}), **changes})
