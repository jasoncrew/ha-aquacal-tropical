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

from .api import TropicApiClient, TropicApiError, TropicAuthError, TropicInvalidCombination
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
        # Last power mode in use while the unit was on, to switch back on with.
        self._last_power: int | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.client.async_get_tropic(self.serial)
        except TropicAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TropicApiError as err:
            raise UpdateFailed(str(err)) from err
        self._remember_power(data)
        return data

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

    def _remember_power(self, data: dict[str, Any]) -> None:
        names = [str(n).lower() for n in data.get("availablePowerModes") or []]
        idx = data.get("powerMode")
        if isinstance(idx, int) and 0 <= idx < len(names) and names[idx] != "off":
            self._last_power = idx

    def power_to_resume(self) -> int | None:
        """Power mode to switch the unit on with.

        While the unit is off the cloud reports power mode "off" too, and it
        rejects any heat mode paired with that. Use the current power mode if
        it isn't off, else the last one used, else Smart.
        """
        names = self.mode_names("power")
        idx = (self.data or {}).get("powerMode")
        if isinstance(idx, int) and 0 <= idx < len(names) and names[idx] != "off":
            return idx
        if self._last_power is not None and self._last_power < len(names):
            return self._last_power
        if "smart" in names:
            return names.index("smart")
        return next((i for i, n in enumerate(names) if n != "off"), None)

    async def async_send(self, changes: dict[str, Any]) -> None:
        """Send a change to the heat pump and reflect it right away."""
        try:
            await self.client.async_set_tropic(self.serial, changes)
        except TropicInvalidCombination:
            # The cloud validates heatMode and powerMode as a pair; a change
            # to one alone can be checked against the wrong partner. Resend
            # with the other mode's current value spelled out.
            paired = self._with_partner_mode(changes)
            if paired == changes:
                raise
            _LOGGER.debug("Cloud rejected %s as a mode combination, resending as %s", changes, paired)
            await self.client.async_set_tropic(self.serial, paired)
            changes = paired
        # The cloud's GET lags the change, so show the new value now;
        # the next scheduled poll confirms it.
        merged = {**(self.data or {}), **changes}
        self._remember_power(merged)
        self.async_set_updated_data(merged)

    def _with_partner_mode(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Add the current heatMode to a powerMode change, or vice versa.

        A heat mode other than off is never paired with power "off" (what the
        cloud reports while the unit is off): it gets the power mode to switch
        back on with instead.
        """
        data = self.data or {}
        if "heatMode" in changes and "powerMode" not in changes:
            heat_names = self.mode_names("heat")
            heat = changes["heatMode"]
            turning_on = not (isinstance(heat, int) and 0 <= heat < len(heat_names) and heat_names[heat] == "off")
            if turning_on and self.mode_name("power") in (None, "off"):
                power = self.power_to_resume()
                if power is not None:
                    return {"powerMode": power, **changes}
        for key, partner in (("powerMode", "heatMode"), ("heatMode", "powerMode")):
            if key in changes and partner not in changes and isinstance(data.get(partner), int):
                return {partner: data[partner], **changes}
        return changes
