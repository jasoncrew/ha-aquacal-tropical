# AquaCal TropiCal (PoolSync Cloud) for Home Assistant

Monitor and control **AquaCal TropiCal inverter heat pumps** (e.g. T130) that have
built-in PoolSync Wi-Fi, from Home Assistant.

These units do not expose a local API, so the existing local PoolSync integrations
can't reach them. This integration uses the same cloud API as the official PoolSync
app, signing in with your PoolSync app account.

> Not affiliated with or endorsed by AquaCal AutoPilot, Inc. The cloud API is
> undocumented and could change without notice.

## Related integrations
- **[AP_PoolSync](https://github.com/ccpk1/AP_PoolSync)** (PoolSync Custom) by
  @ccpk1: **local control** of AquaCal/AutoPilot PoolSync hardware, including
  heat pumps on a PoolSync module that answers on your network, ChlorSync and
  ChemSync. If your device can be reached locally, use that: it's faster, needs
  no cloud account and covers far more hardware. This integration is for the
  TropiCal units with built-in Wi-Fi that have no local API.
- **[poolsync_chlorsync](https://github.com/CLARENNE-Q/poolsync_chlorsync)** by
  @CLARENNE-Q: ChlorSync chlorinators over the PoolSync cloud.

Both can be installed alongside this one (different domains).

## Requirements
- A TropiCal heat pump already set up in the **PoolSync app** on your account
- Home Assistant 2024.11 or newer (developed and tested on 2026.9–2026.10)

## Tested hardware
| Model | Reported model code | Status |
|---|---|---|
| TropiCal T130 | `IVA_Q0` | Working (heat, cool, auto, off; Eco / Smart / Boost) |

Other TropiCal models with PoolSync Wi-Fi should work, since the integration reads
whatever modes the unit advertises. If you try one, please open an issue with your
model and a **Download diagnostics** file, whether it works or not, so this table
can grow.

## Installation (HACS)
1. HACS → ⋮ → **Custom repositories** → add this repository's URL, type **Integration**.
2. Install **AquaCal TropiCal (PoolSync Cloud)** and restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → AquaCal TropiCal**.
4. Sign in with your PoolSync app email and password. Every TropiCal on the
   account is added as its own device.

Manual install: copy `custom_components/poolsync_tropic` into your
`config/custom_components/` folder and restart.

## What you get (per heat pump)
| Entity | Details |
|---|---|
| Thermostat (climate) | Water temperature, setpoint, modes Off / Heat / Cool / Auto (whichever the unit supports), presets Eco / Smart / Boost |
| Water temperature, Air temperature | Sensors |
| Power, Water flow | Binary sensors |
| Online, Last report | Diagnostic |

Temperatures use whatever units your PoolSync account reports (°F or °C);
Home Assistant converts them for display as usual.

## Options
**Configure** on the integration lets you change the polling interval
(default 60 s, 30–3600 s).

## How the heat pump behaves (worth knowing before you automate it)
- **One command every few seconds.** The unit only takes about one command
  every few seconds; the cloud answers "timeout" while it is busy. Commands are
  queued and retried up to four times, 4 s apart. In automations, only send
  what actually changes.
- **Auto drops Boost.** In Auto (`heat_cool`) the unit switches Boost back to
  Smart within about a minute. Boost holds in Heat and in Cool, so if you want
  Boost, pick Heat or Cool rather than Auto.
- **Switching on from Off.** While the unit is off the cloud reports its power
  preset as "off" too, and it rejects a heat mode paired with that. Turning it
  on from Home Assistant sends a real preset with the mode: the current one,
  else the last one you used, else Smart.
- **Reporting delay.** After a change the new value shows immediately; the
  cloud itself can take a minute to report it back.
- **Its air sensor reads cold while running.** The unit's air temperature
  sensor sits in its own airflow and reads several degrees low while the
  compressor runs. Use a separate weather sensor for air temperature in
  automations.

## Example automation
Heat the spa to 102 °F on Boost every Friday at 5 pm (Heat, not Auto, so Boost
holds):

```yaml
alias: Spa for Friday evening
triggers:
  - trigger: time
    at: "17:00:00"
conditions:
  - condition: time
    weekday: fri
actions:
  - action: climate.set_preset_mode
    target:
      entity_id: climate.tropical_heat_pump_thermostat
    data:
      preset_mode: boost
  - delay: "00:00:05"
  - action: climate.set_temperature
    target:
      entity_id: climate.tropical_heat_pump_thermostat
    data:
      hvac_mode: heat
      temperature: 102
```

Your entity id may differ; check it under the device.

## Sign-in and privacy
- Your PoolSync email and password are stored in Home Assistant's config entry
  and are only ever sent to the PoolSync cloud.
- If the password changes or the cloud rejects the saved login, Home Assistant
  shows a repair asking you to sign in again (**Re-enter PoolSync password**);
  nothing needs to be removed.
- The **Download diagnostics** file removes your email, password and the unit
  serial numbers.

## Troubleshooting
Enable debug logging and include the log plus the **Download diagnostics**
file when opening an issue:

```yaml
logger:
  logs:
    custom_components.poolsync_tropic: debug
```

## Removing the integration
1. **Settings → Devices & Services → AquaCal TropiCal → ⋮ → Delete.**
2. In HACS, open the integration and choose **Remove**, then restart Home
   Assistant (or delete `config/custom_components/poolsync_tropic` if you
   installed it manually).

The heat pump keeps its last settings and keeps working from the PoolSync app.

## How it works
| Action | Request |
|---|---|
| Sign in | `POST /api/app/auth/login` `{"email","password"}` |
| Find units | `GET /api/app/user` → `user.myDevicesTropic[].serialNum` |
| Read state | `GET /api/app/tropic/<serial>` |
| Change | `PATCH /api/app/tropic/<serial>` with `{"setpoint": n}`, `{"heatMode": i}` or `{"powerMode": i}` (indexes into `availableHeatModes` / `availablePowerModes`) |

## Development
```bash
pip install pytest-homeassistant-custom-component
pytest
```
Needs the Python version the current Home Assistant requires (3.14 for 2026.10).
