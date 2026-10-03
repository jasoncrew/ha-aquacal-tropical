"""Binary sensors for the TropiCal heat pump."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TropicCoordinator
from .entity import TropicEntity

# (description, key in the cloud payload)
BINARY_SENSORS: tuple[tuple[BinarySensorEntityDescription, str], ...] = (
    (BinarySensorEntityDescription(key="power", device_class=BinarySensorDeviceClass.POWER), "isOn"),
    (BinarySensorEntityDescription(key="water_flow", device_class=BinarySensorDeviceClass.RUNNING), "hasFlow"),
    (
        BinarySensorEntityDescription(
            key="online",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        "isOnline",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        TropicBinarySensor(coordinator, d, k)
        for coordinator in entry.runtime_data.values()
        for d, k in BINARY_SENSORS
    )


class TropicBinarySensor(TropicEntity, BinarySensorEntity):
    def __init__(self, coordinator: TropicCoordinator, description: BinarySensorEntityDescription, field: str) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._field = field

    @property
    def is_on(self) -> bool | None:
        value = self.coordinator.data.get(self._field)
        return None if value is None else bool(value)
