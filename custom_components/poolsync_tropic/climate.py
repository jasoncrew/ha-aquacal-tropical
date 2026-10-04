"""Thermostat entity for the TropiCal heat pump."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import TropicApiError
from .coordinator import TropicCoordinator
from .entity import TropicEntity

# Cloud heat-mode names -> Home Assistant HVAC modes
HEAT_TO_HVAC = {
    "off": HVACMode.OFF,
    "auto": HVACMode.HEAT_COOL,
    "heat": HVACMode.HEAT,
    "cool": HVACMode.COOL,
}
HVAC_TO_HEAT = {v: k for k, v in HEAT_TO_HVAC.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(TropicClimate(c) for c in entry.runtime_data.values())


class TropicClimate(TropicEntity, ClimateEntity):
    _attr_target_temperature_step = 1
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: TropicCoordinator) -> None:
        super().__init__(coordinator, "thermostat")
        self._last_active_mode = "heat"

    @property
    def _data(self) -> dict[str, Any]:
        return self.coordinator.data or {}

    @property
    def temperature_unit(self) -> str:
        return self.coordinator.temperature_unit

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return [HEAT_TO_HVAC[n] for n in self.coordinator.mode_names("heat") if n in HEAT_TO_HVAC]

    @property
    def hvac_mode(self) -> HVACMode | None:
        name = self.coordinator.mode_name("heat")
        if name and name != "off":
            self._last_active_mode = name
        return HEAT_TO_HVAC.get(name) if name else None

    @property
    def preset_modes(self) -> list[str]:
        return [n for n in self.coordinator.mode_names("power") if n != "off"]

    @property
    def preset_mode(self) -> str | None:
        name = self.coordinator.mode_name("power")
        return name if name and name != "off" else None

    @property
    def current_temperature(self) -> float | None:
        return self._data.get("waterTemp")

    @property
    def target_temperature(self) -> float | None:
        return self._data.get("setpoint")

    @property
    def min_temp(self) -> float:
        return self.coordinator.temperature_range[0]

    @property
    def max_temp(self) -> float:
        return self.coordinator.temperature_range[1]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"air_temperature": self._data.get("airTemp")}

    async def _send(self, changes: dict[str, Any]) -> None:
        try:
            await self.coordinator.async_send(changes)
        except TropicApiError as err:
            raise HomeAssistantError(f"TropiCal did not accept {changes}: {err}") from err

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            await self.async_set_hvac_mode(mode)
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            temp = round(float(temp))
            if not self.min_temp <= temp <= self.max_temp:
                raise HomeAssistantError(
                    f"{temp} is outside the heat pump's range ({self.min_temp}-{self.max_temp} {self.temperature_unit})"
                )
            await self._send({"setpoint": temp})

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        name = HVAC_TO_HEAT.get(hvac_mode)
        idx = self.coordinator.mode_index("heat", name) if name else None
        if idx is None:
            raise HomeAssistantError(f"Mode {hvac_mode} is not supported by this heat pump")
        changes: dict[str, Any] = {"heatMode": idx}
        # Switching on from off: the unit's power mode reads "off" too, and the
        # cloud rejects a heat mode paired with it, so send a real one along.
        if name != "off" and self.coordinator.mode_name("power") in (None, "off"):
            if (power := self.coordinator.power_to_resume()) is not None:
                changes["powerMode"] = power
        await self._send(changes)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        idx = self.coordinator.mode_index("power", preset_mode)
        if idx is None:
            raise HomeAssistantError(f"Power mode {preset_mode} is not supported")
        await self._send({"powerMode": idx})

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HEAT_TO_HVAC.get(self._last_active_mode, HVACMode.HEAT))

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
