"""Diagnostics download with personal details removed."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, "serialNum", "gatewaySN", "title", "unique_id"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry) -> dict[str, Any]:
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "heat_pumps": [
            {
                "temperature_unit": c.temperature_unit,
                "last_update_success": c.last_update_success,
                "data": async_redact_data(c.data or {}, TO_REDACT),
            }
            for c in entry.runtime_data.values()
        ],
    }
