"""Tests built from real PoolSync app traffic (identifiers replaced)."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.components.climate import HVACMode
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

from custom_components.poolsync_tropic.const import BASE_URL, CONF_SCAN_INTERVAL, DOMAIN
from custom_components.poolsync_tropic.diagnostics import async_get_config_entry_diagnostics

SERIAL = "IVA00X000000A001"
SERIAL2 = "IVA00X000000A002"
LOGIN = f"{BASE_URL}/auth/login"
USER = f"{BASE_URL}/user"
EMAIL = "owner@example.com"
CLIMATE = "climate.tropical_heat_pump_thermostat"


def tropic_url(serial: str = SERIAL) -> str:
    return f"{BASE_URL}/tropic/{serial}"


def state(serial: str = SERIAL, **overrides) -> dict:
    data = {
        "airTemp": 73,
        "availableHeatModes": ["OFF", "AUTO", "HEAT", "COOL"],
        "availablePowerModes": ["OFF", "ECO", "SMART", "BOOST"],
        "dateTime": "2026-10-03T17:34:38",
        "hasFlow": True,
        "heatMode": 2,
        "isOn": True,
        "isOnline": True,
        "powerMode": 3,
        "serialNum": serial,
        "setpoint": 100,
        "waterTemp": 82,
        "gatewaySN": "PC-B-00-00-00000000",
        "gatewayType": "B",
        "maxTemp": 104,
        "minTemp": 46,
        "modelNum": "IVA_Q0",
        "networkType": "wifi",
        "setpointMax": 40,
        "setpointMin": 8,
    }
    return data | overrides


def user_body(*serials: str) -> dict:
    return {"user": {"email": EMAIL, "myDevices": [], "myDevicesTropic": [{"serialNum": s} for s in serials]}}


def mock_cloud(aioclient_mock, serials=(SERIAL,), states=None):
    aioclient_mock.post(LOGIN, json={"tokens": {"access": "tok"}})
    aioclient_mock.get(USER, json=user_body(*serials))
    for s in serials:
        aioclient_mock.get(tropic_url(s), json=(states or {}).get(s, state(s)))


async def setup(hass, aioclient_mock, *, units=US_CUSTOMARY_SYSTEM, **kw):
    hass.config.units = units
    mock_cloud(aioclient_mock, **kw)
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=EMAIL, title=EMAIL, data={CONF_EMAIL: EMAIL, CONF_PASSWORD: "pw"}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def patch_bodies(aioclient_mock):
    return [c[2] for c in aioclient_mock.mock_calls if c[0] == "PATCH"]


# --- config flow -------------------------------------------------------------


async def test_flow_creates_account_entry(hass: HomeAssistant, aioclient_mock) -> None:
    mock_cloud(aioclient_mock)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch("custom_components.poolsync_tropic.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: " Owner@Example.com ", CONF_PASSWORD: "pw"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_EMAIL: "Owner@Example.com", CONF_PASSWORD: "pw"}
    assert result["result"].unique_id == EMAIL


@pytest.mark.parametrize(
    ("login_status", "serials", "error"),
    [(401, (SERIAL,), "invalid_auth"), (200, (), "no_devices"), (502, (SERIAL,), "cannot_connect")],
)
async def test_flow_errors(hass: HomeAssistant, aioclient_mock, login_status, serials, error) -> None:
    aioclient_mock.post(LOGIN, status=login_status, json={"tokens": {"access": "tok"}})
    aioclient_mock.get(USER, json=user_body(*serials))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: "x"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_options_change_interval(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await setup(hass, aioclient_mock)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_SCAN_INTERVAL: 120})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    coordinator = next(iter(entry.runtime_data.values()))
    assert coordinator.update_interval.total_seconds() == 120


# --- entities ----------------------------------------------------------------


async def test_entities_fahrenheit(hass: HomeAssistant, aioclient_mock) -> None:
    await setup(hass, aioclient_mock)
    climate = hass.states.get(CLIMATE)
    assert climate.state == HVACMode.HEAT
    assert climate.attributes["current_temperature"] == 82
    assert climate.attributes["temperature"] == 100
    assert (climate.attributes["min_temp"], climate.attributes["max_temp"]) == (46, 104)
    assert climate.attributes["preset_mode"] == "boost"
    assert climate.attributes["preset_modes"] == ["eco", "smart", "boost"]
    assert set(climate.attributes["hvac_modes"]) == {"off", "heat_cool", "heat", "cool"}
    assert hass.states.get("sensor.tropical_heat_pump_water_temperature").state == "82"
    assert hass.states.get("sensor.tropical_heat_pump_air_temperature").state == "73"
    assert hass.states.get("sensor.tropical_heat_pump_last_report").state == "2026-10-03T17:34:38+00:00"
    assert hass.states.get("binary_sensor.tropical_heat_pump_water_flow").state == "on"
    assert hass.states.get("binary_sensor.tropical_heat_pump_power").state == "on"
    assert hass.states.get("binary_sensor.tropical_heat_pump_online").state == "on"


async def test_entities_celsius_account(hass: HomeAssistant, aioclient_mock) -> None:
    celsius = state(setpoint=38, waterTemp=28, airTemp=23, minTemp=8, maxTemp=40)
    await setup(hass, aioclient_mock, units=METRIC_SYSTEM, states={SERIAL: celsius})
    climate = hass.states.get(CLIMATE)
    assert climate.attributes["temperature"] == 38
    assert climate.attributes["current_temperature"] == 28
    assert (climate.attributes["min_temp"], climate.attributes["max_temp"]) == (8, 40)
    water = hass.states.get("sensor.tropical_heat_pump_water_temperature")
    assert water.state == "28" and water.attributes["unit_of_measurement"] == "°C"


async def test_heat_only_unit(hass: HomeAssistant, aioclient_mock) -> None:
    await setup(hass, aioclient_mock, states={SERIAL: state(availableHeatModes=["OFF", "HEAT"], heatMode=1)})
    climate = hass.states.get(CLIMATE)
    assert climate.state == HVACMode.HEAT
    assert set(climate.attributes["hvac_modes"]) == {"off", "heat"}


async def test_two_heat_pumps_one_account(hass: HomeAssistant, aioclient_mock) -> None:
    await setup(hass, aioclient_mock, serials=(SERIAL, SERIAL2))
    assert hass.states.get("climate.tropical_heat_pump_a001_thermostat") is not None
    assert hass.states.get("climate.tropical_heat_pump_a002_thermostat") is not None


# --- commands ----------------------------------------------------------------


async def test_commands_match_app(hass: HomeAssistant, aioclient_mock) -> None:
    await setup(hass, aioclient_mock)
    aioclient_mock.patch(tropic_url(), status=200, text="")
    call = hass.services.async_call
    await call("climate", "set_temperature", {"entity_id": CLIMATE, "temperature": 99}, blocking=True)
    await call("climate", "set_hvac_mode", {"entity_id": CLIMATE, "hvac_mode": "cool"}, blocking=True)
    await call("climate", "set_preset_mode", {"entity_id": CLIMATE, "preset_mode": "smart"}, blocking=True)
    await call("climate", "set_hvac_mode", {"entity_id": CLIMATE, "hvac_mode": "heat_cool"}, blocking=True)
    await call("climate", "turn_off", {"entity_id": CLIMATE}, blocking=True)
    await call("climate", "turn_on", {"entity_id": CLIMATE}, blocking=True)
    assert patch_bodies(aioclient_mock) == [
        {"setpoint": 99}, {"heatMode": 3}, {"powerMode": 2}, {"heatMode": 1}, {"heatMode": 0}, {"heatMode": 1},
    ]
    climate = hass.states.get(CLIMATE)
    assert climate.attributes["temperature"] == 99
    assert climate.attributes["preset_mode"] == "smart"
    assert climate.state == HVACMode.HEAT_COOL


async def test_out_of_range_rejected(hass: HomeAssistant, aioclient_mock) -> None:
    await setup(hass, aioclient_mock)
    with pytest.raises(Exception):
        await hass.services.async_call(
            "climate", "set_temperature", {"entity_id": CLIMATE, "temperature": 110}, blocking=True
        )
    assert patch_bodies(aioclient_mock) == []


async def test_busy_unit_retried(hass: HomeAssistant, aioclient_mock) -> None:
    await setup(hass, aioclient_mock)
    calls = {"n": 0}

    async def flaky(method, url, data):
        calls["n"] += 1
        if calls["n"] < 3:
            return AiohttpClientMockResponse(method, url, status=500, text='{"error":"timeout"}')
        return AiohttpClientMockResponse(method, url, status=200, text="")

    aioclient_mock.patch(tropic_url(), side_effect=flaky)
    with patch("custom_components.poolsync_tropic.api.COMMAND_RETRY_DELAY", 0):
        await hass.services.async_call(
            "climate", "set_temperature", {"entity_id": CLIMATE, "temperature": 98}, blocking=True
        )
    assert calls["n"] == 3
    assert hass.states.get(CLIMATE).attributes["temperature"] == 98


async def test_busy_unit_gives_up(hass: HomeAssistant, aioclient_mock) -> None:
    await setup(hass, aioclient_mock)
    aioclient_mock.patch(tropic_url(), status=500, text='{"error":"{\\"ReplyStatus\\":3,\\"Response\\":{\\"r\\":25}}"}')
    with patch("custom_components.poolsync_tropic.api.COMMAND_RETRY_DELAY", 0), pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "climate", "set_temperature", {"entity_id": CLIMATE, "temperature": 98}, blocking=True
        )
    assert len(patch_bodies(aioclient_mock)) == 4
    assert hass.states.get(CLIMATE).attributes["temperature"] == 100


# --- auth & diagnostics ------------------------------------------------------


async def test_expired_token_relogin(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await setup(hass, aioclient_mock)
    coordinator = entry.runtime_data[SERIAL]
    aioclient_mock.clear_requests()
    aioclient_mock.post(LOGIN, json={"tokens": {"access": "tok2"}})
    seen = {"n": 0}

    async def first_401(method, url, data):
        seen["n"] += 1
        if seen["n"] == 1:
            return AiohttpClientMockResponse(method, url, status=401, json={"message": "Unauthorized"})
        return AiohttpClientMockResponse(method, url, json=state(waterTemp=84))

    aioclient_mock.get(tropic_url(), side_effect=first_401)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.last_update_success
    assert hass.states.get("sensor.tropical_heat_pump_water_temperature").state == "84"


async def test_password_changed_starts_reauth(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.post(LOGIN, status=401, json={"error": "bad"})
    entry = MockConfigEntry(domain=DOMAIN, unique_id=EMAIL, data={CONF_EMAIL: EMAIL, CONF_PASSWORD: "old"})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_diagnostics_redacted(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await setup(hass, aioclient_mock)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = str(diag)
    for secret in (EMAIL, "pw", SERIAL, "PC-B-00-00-00000000"):
        assert secret not in text
    assert diag["heat_pumps"][0]["data"]["waterTemp"] == 82
