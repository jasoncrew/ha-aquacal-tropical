"""Shared entity base."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TropicCoordinator


class TropicEntity(CoordinatorEntity[TropicCoordinator]):
    """Base class: one device per heat pump serial."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TropicCoordinator, key: str) -> None:
        super().__init__(coordinator)
        serial = coordinator.serial
        data = coordinator.data or {}
        self._attr_unique_id = f"{serial}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer="AquaCal",
            name=coordinator.device_name,
            model=data.get("modelNum"),
            serial_number=serial,
        )
