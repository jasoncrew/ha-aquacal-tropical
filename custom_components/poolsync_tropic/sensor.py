"""Sensors for the TropiCal heat pump."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TropicCoordinator
from .entity import TropicEntity


def _timestamp(value: Any) -> datetime | None:
    # The cloud reports dateTime without an offset; it matches UTC.
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass(frozen=True, kw_only=True)
class TropicSensorDescription(SensorEntityDescription):
    value_fn: Callable[[TropicCoordinator], Any]


SENSORS: tuple[TropicSensorDescription, ...] = (
    TropicSensorDescription(
        key="water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.data.get("waterTemp"),
    ),
    TropicSensorDescription(
        key="air_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.data.get("airTemp"),
    ),
    TropicSensorDescription(
        key="last_report",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: _timestamp(c.data.get("dateTime")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        TropicSensor(coordinator, d)
        for coordinator in entry.runtime_data.values()
        for d in SENSORS
    )


class TropicSensor(TropicEntity, SensorEntity):
    entity_description: TropicSensorDescription

    def __init__(self, coordinator: TropicCoordinator, description: TropicSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.device_class == SensorDeviceClass.TEMPERATURE:
            return self.coordinator.temperature_unit
        return None

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)
