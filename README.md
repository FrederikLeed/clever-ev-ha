# Clever EV — Home Assistant Integration

Unofficial Home Assistant custom component for the [Clever](https://clever.dk) EV home charger.

Exposes your Clever home charger as sensors and controls in Home Assistant, enabling automations based on charging state, electricity prices, and energy consumption.

## How it works

The Clever iOS/Android app communicates with `mobileapp-backend.clever.dk`. This integration replicates that communication using the same API endpoints and authentication flow. Auth is handled via Google Firebase (email + password), and the session is maintained automatically using a long-lived refresh token — you only enter your password once.

> **Note:** This is an unofficial integration. Clever A/S does not provide a public API and has previously asked developers to remove endpoint documentation. Use at your own discretion.

## Features

- Real-time charger state (online/offline, operational status)
- Smart charging status (enabled/disabled)
- Energy tracking — last session kWh and monthly total per connector
- Hourly electricity price in DKK/kWh with full tariff breakdown
- Charging configuration — departure time, phase count, max ampere
- **Set desired charge range** via slider (number entity, 5–100 kWh)
- **Boost charging** — skip smart charging for 1 hour, charge until full, or cancel boost
- Multiple connectors/installations on the same account, each as a separate HA device
- Automatic token refresh — no re-authentication required under normal operation
- Reauth flow if credentials ever become invalid
- HACS-installable

## Entities

Entities are created per installation (connector). If you have two connectors, you get two HA devices with the full set of entities each.

### Sensors

| Entity | Description | Unit |
|---|---|---|
| `sensor.clever_ev_charger_state` | Operational status (`Operational`, `SentToInvoice`, etc.) | — |
| `sensor.clever_ev_online_status` | Online / Offline | — |
| `sensor.clever_ev_last_session_energy` | Energy delivered in last completed session | kWh |
| `sensor.clever_ev_monthly_energy` | Total energy charged this calendar month | kWh |
| `sensor.clever_ev_electricity_price` | Current hour spot price incl. all tariffs | DKK/kWh |
| `sensor.clever_ev_departure_time` | Configured departure time for smart charging | HH:MM |
| `sensor.clever_ev_phase_count` | Number of phases configured | — |
| `sensor.clever_ev_max_ampere` | Maximum configured ampere | A |

### Number

| Entity | Description | Range |
|---|---|---|
| `number.clever_ev_desired_range` | Set desired charge range target | 5–100 kWh |

### Binary Sensors

| Entity | Description |
|---|---|
| `binary_sensor.clever_ev_smart_charging` | Smart charging enabled |
| `binary_sensor.clever_ev_charger_online` | Charger reachable |

### Buttons

| Entity | Description |
|---|---|
| `button.clever_ev_boost_1_hour` | Disable smart charging for 1 hour (timebox boost) |
| `button.clever_ev_boost_until_full` | Disable smart charging until 100% (full boost) |
| `button.clever_ev_cancel_boost` | Cancel active boost, re-enable smart charging |

### Switches

| Entity | Description |
|---|---|
| `switch.clever_ev_smart_charging` | Smart charging state *(read-only — `canDisableSmartCharging` is false on Clever One subscriptions; use boost buttons instead)* |

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** → ⋮ → **Custom repositories**
3. Add `https://github.com/YOUR_USERNAME/clever-ev-ha` as an **Integration**
4. Search for **Clever EV** and install
5. Restart Home Assistant

### Manual

Copy `custom_components/clever_ev/` into your HA `config/custom_components/` directory and restart.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Clever EV**
3. Enter your Clever account email and password
4. Done — entities will appear under a *Clever EV Charger* device per connector

Your password is used only during setup to obtain a Firebase refresh token. The password itself is not stored.

## Testing without Home Assistant

A standalone test script is included that validates the full auth flow and prints a live preview of every HA entity with its current value — no HA installation required.

### Requirements

```bash
pip install requests
```

### Run

```bash
python test_auth.py
```

Or supply credentials via environment variables to skip the prompts:

```powershell
# PowerShell
$env:CLEVER_EMAIL = "you@example.com"
$env:CLEVER_PASSWORD = "yourpassword"
python test_auth.py
```

```bash
# bash / macOS / Linux
CLEVER_EMAIL=you@example.com CLEVER_PASSWORD=yourpassword python test_auth.py
```

### What it tests

| Step | What it checks |
|---|---|
| 1 | Credential input (env vars or interactive prompt) |
| 2 | Firebase sign-in — email/password → JWT id_token |
| 3 | Token refresh — refresh_token → new id_token |
| 4 | All Clever API endpoints (installations, profiles, history, electricity price) |
| 5 | Entity preview — prints every HA entity with its live value |
| 6 | Write endpoint test — round-trip set power-required (non-destructive) |

### Example output

```
------------------------------------------------------------
  STEP 5: HA entity preview
------------------------------------------------------------

  Device: Clever EV Charger (Connector 1)
  Address: My Street 1, My City
  Installation ID: xxxxxxxx  Charge Box: xxxxxxxx

  Platform        Entity                  Value
  -------------------------------------------------------
  sensor          Charger State           Operational
  sensor          Online Status           Online
  sensor          Last Session Energy     14.519 kWh
  sensor          Monthly Energy          38.834 kWh
  sensor          Electricity Price       1.4839 DKK/kWh
  sensor          Departure Time          05:45
  number          Desired Range           40 kWh
  sensor          Phase Count             3
  sensor          Max Ampere              16 A
  binary_sensor   Smart Charging          ON
  binary_sensor   Charger Online          ON
  switch          Smart Charging          ON (read-only)
  button          Boost 1 Hour            POST .../timebox-boost
  button          Boost Until Full        POST .../boost
  button          Cancel Boost            POST .../unboost
```

## Update intervals

| Data | Interval |
|---|---|
| Charger state, smart charging config | Every 1 minute |
| Consumption history, electricity prices | Every 30 minutes |

## Automation ideas

```yaml
# Notify when charger goes offline
automation:
  trigger:
    - platform: state
      entity_id: binary_sensor.clever_ev_charger_online
      to: "off"
  action:
    - service: notify.mobile_app
      data:
        message: "Clever charger went offline"

# Log a notification when a charging session completes (energy increases)
automation:
  trigger:
    - platform: state
      entity_id: sensor.clever_ev_last_session_energy
  action:
    - service: notify.mobile_app
      data:
        message: "Charging session complete: {{ states('sensor.clever_ev_last_session_energy') }}"

# Alert when electricity is cheap
automation:
  trigger:
    - platform: numeric_state
      entity_id: sensor.clever_ev_electricity_price
      below: 1.00
  action:
    - service: notify.mobile_app
      data:
        message: "Cheap electricity now: {{ states('sensor.clever_ev_electricity_price') }} DKK/kWh"

# Boost charging for 1 hour when electricity drops below 0.50 DKK/kWh
automation:
  trigger:
    - platform: numeric_state
      entity_id: sensor.clever_ev_electricity_price
      below: 0.50
  action:
    - service: button.press
      target:
        entity_id: button.clever_ev_boost_1_hour
```

## TODO

- [ ] Departure time control (number or time entity for setting departure time)
- [ ] Phase count / ampere configuration (if write endpoints can be found)

## Known limitations

- **Smart charging switch** is read-only. `canDisableSmartCharging: false` on Clever One subscriptions — use the boost buttons to temporarily override smart charging instead.
- No support for public Clever charging points — home charger only.

## Technical notes

Authentication uses the Firebase Identity Toolkit (`identitytoolkit.googleapis.com`) with the `clever-app-prod` Firebase project. The API key is restricted to iOS bundle ID `com.clever.cleverapp`, so all Firebase requests include the matching iOS client headers.

The API base URL is `https://mobileapp-backend.clever.dk/api/v6/`.

## License

MIT
