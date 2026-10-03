# AquaCal TropiCal (PoolSync Cloud) for Home Assistant

Monitor and control **AquaCal TropiCal inverter heat pumps** (e.g. T130) that have
built-in PoolSync Wi-Fi, from Home Assistant.

These units do not expose a local API, so the existing local PoolSync integrations
can't reach them. This integration uses the same cloud API as the official PoolSync
app, signing in with your PoolSync app account.

> Not affiliated with or endorsed by AquaCal AutoPilot, Inc. The cloud API is
> undocumented and could change without notice.

## Requirements
- A TropiCal heat pump already set up in the **PoolSync app** on your account
- Home Assistant 2024.11 or newer

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

## Notes
- The heat pump only takes about one command every few seconds; the cloud
  answers "timeout" while it is busy. Commands are queued and retried up to
  four times, 4 s apart.
- After a change, the new value shows immediately; the cloud itself can take
  a minute to report it.

## Troubleshooting
Enable debug logging and include the log plus the **Download diagnostics**
file (personal details are removed) when opening an issue:

```yaml
logger:
  logs:
    custom_components.poolsync_tropic: debug
```

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
