"""Standalone test for Clever EV auth + API — no HA required.

Tests all auth steps and prints a preview of every HA entity that would
be created by the integration, with its current live value.

Usage:
    python test_auth.py

Credentials can be supplied via environment variables to skip prompts:
    set CLEVER_EMAIL=you@example.com
    set CLEVER_PASSWORD=yourpassword
    python test_auth.py
"""
import getpass
import json
import os
import sys
from datetime import datetime, timezone

import requests

FIREBASE_SIGN_IN_URL = "https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword"
FIREBASE_REFRESH_URL = "https://securetoken.googleapis.com/v1/token"
FIREBASE_API_KEY = "AIzaSyCclOhPIonDgWAZoWfn3zInCB-G6h4aD-0"

BASE_URL = "https://mobileapp-backend.clever.dk/api/v6"
FIREBASE_HEADERS = {
    "x-ios-bundle-identifier": "com.clever.cleverapp",
    "x-client-version": "iOS/FirebaseSDK/12.4.0/FirebaseCore-iOS",
    "x-firebase-gmpid": "1:59507274536:ios:b44d817d7acda1f8b4161d",
    "user-agent": "FirebaseAuth.iOS/12.4.0 com.clever.cleverapp/9.1.0 iPhone/26.3 hw/iPhone15_2",
    "content-type": "application/json",
    "accept": "*/*",
    "accept-language": "en",
}
STATIC_HEADERS = {
    "x-api-key": "Basic bW9iaWxlYXBwOmFwaWtleQ==",
    "app-platform": "iOS",
    "app-version": "9.1.0",
    "app-device": "iPhone15,2",
    "app-os": "26.3",
    "content-type": "application/json",
    "accept": "*/*",
    "accept-language": "en",
}


# ── Helpers ────────────────────────────────────────────────────────

def pprint(label: str, data) -> None:
    print(f"\n{'*'*60}")
    print(f"  {label}")
    print(f"{'*'*60}")
    if isinstance(data, (dict, list)):
        print(json.dumps(data, indent=2))
    else:
        print(data)


def step(n: int, title: str) -> None:
    print(f"\n{'-'*60}")
    print(f"  STEP {n}: {title}")
    print(f"{'-'*60}")


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str, body=None) -> None:
    print(f"  FAIL  {msg}")
    if body:
        pprint("Response", body)
    sys.exit(1)


def api_get(path: str, clever_headers: dict, params: dict | None = None):
    resp = requests.get(f"{BASE_URL}/{path}", headers=clever_headers, params=params)
    if resp.status_code != 200:
        fail(f"GET /{path} returned {resp.status_code}", resp.text)
    data = resp.json()
    if not data.get("status"):
        fail(f"GET /{path} API error: {data.get('statusMessage')}", data)
    return data["data"]


def api_put(path: str, clever_headers: dict, body: dict):
    resp = requests.put(f"{BASE_URL}/{path}", headers=clever_headers, json=body)
    if resp.status_code != 200:
        fail(f"PUT /{path} returned {resp.status_code}", resp.text)
    data = resp.json()
    if not data.get("status"):
        fail(f"PUT /{path} API error: {data.get('statusMessage')}", data)
    return data["data"]


# ── Entity value helpers (mirrors sensor.py logic) ─────────────────

def smart_cfg(inst: dict) -> dict:
    return (
        (inst.get("smartChargingConfiguration") or {})
        .get("userConfiguration") or {}
    )


def current_hour_price(prices: list) -> str:
    now = datetime.now(tz=timezone.utc)
    for entry in prices:
        try:
            start = datetime.fromisoformat(entry["startTime"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(entry["endTime"].replace("Z", "+00:00"))
            if start <= now < end:
                return f"{round(entry['totalPrice'], 4)} DKK/kWh"
        except (KeyError, ValueError):
            continue
    return "unavailable"


def monthly_kwh(records: list, connector_id: int) -> str:
    now = datetime.now(tz=timezone.utc)
    total = 0.0
    for r in records:
        if r.get("connectorId") != connector_id:
            continue
        ts = r.get("stopTimeUtc")
        if not ts:
            continue
        try:
            dt = datetime.fromtimestamp(ts / 1_000_000, tz=timezone.utc)
            if dt.year == now.year and dt.month == now.month:
                total += r.get("kWh", 0)
        except (OSError, OverflowError, ValueError):
            continue
    return f"{round(total, 3)} kWh"


def last_session_kwh(records: list, connector_id: int) -> str:
    filtered = [r for r in records if r.get("connectorId") == connector_id]
    if not filtered:
        return "unavailable"
    latest = max(filtered, key=lambda r: r.get("stopTimeUtc", 0))
    return f"{round(latest['kWh'], 3)} kWh"


def print_entity_table(rows: list[tuple[str, str, str]]) -> None:
    """Print a table of (platform, entity_name, value)."""
    col1 = max(len(r[0]) for r in rows) + 2
    col2 = max(len(r[1]) for r in rows) + 2
    header = f"  {'Platform':<{col1}} {'Entity':<{col2}} Value"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for platform, name, value in rows:
        print(f"  {platform:<{col1}} {name:<{col2}} {value}")


# ── Step 1: Credentials ────────────────────────────────────────────
step(1, "Credentials")
email = os.environ.get("CLEVER_EMAIL") or input("Clever email: ").strip()
password = os.environ.get("CLEVER_PASSWORD") or getpass.getpass("Password: ")
print(f"  Email: {email}  Password: {'*' * len(password)}")

# ── Step 2: Firebase sign-in ───────────────────────────────────────
step(2, "Firebase sign-in (verifyPassword)")
signin_payload = {
    "email": email,
    "password": password,
    "clientType": "CLIENT_TYPE_IOS",
    "returnSecureToken": True,
}
resp = requests.post(
    FIREBASE_SIGN_IN_URL,
    params={"key": FIREBASE_API_KEY},
    headers=FIREBASE_HEADERS,
    json=signin_payload,
)
if resp.status_code != 200:
    fail(f"Firebase sign-in returned {resp.status_code}", resp.json())
auth = resp.json()
id_token = auth["idToken"]
refresh_token = auth["refreshToken"]
ok(f"id_token obtained (expires in {auth['expiresIn']}s)")
ok(f"refresh_token: {refresh_token[:30]}...")

# ── Step 3: Token refresh ──────────────────────────────────────────
step(3, "Token refresh (securetoken)")
resp2 = requests.post(
    FIREBASE_REFRESH_URL,
    params={"key": FIREBASE_API_KEY},
    headers={**FIREBASE_HEADERS, "content-type": "application/x-www-form-urlencoded"},
    data={"grant_type": "refresh_token", "refresh_token": refresh_token},
)
if resp2.status_code != 200:
    fail(f"Token refresh returned {resp2.status_code}", resp2.json())
ok(f"Refresh OK — new token expires in {resp2.json()['expires_in']}s")

# ── Steps 4-7: Fetch all API data ─────────────────────────────────
clever_headers = {**STATIC_HEADERS, "authorization": f"Bearer {id_token}"}

step(4, "Clever API — fetching all data")
installations = api_get("installations", clever_headers)
ok(f"{len(installations)} installation(s) found")

profiles = api_get("chargingprofiles", clever_headers)
ok(f"{len(profiles)} charging profile(s) found")

history_data = api_get("consumption/history", clever_headers)
records = history_data.get("consumptionRecords", [])
ok(f"{len(records)} consumption records")

# Build connector -> profile lookup
profile_by_connector: dict[int, dict] = {}
dar_id: str | None = None
for p in profiles:
    for loc in (p.get("filters") or {}).get("locations", []):
        if not dar_id:
            dar_id = loc["id"]
        for cp in loc.get("chargePoints", []):
            profile_by_connector[cp["connectorId"]] = p

# Electricity price (shared across connectors)
prices: list = []
if dar_id:
    from_date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT00:00:00.000Z")
    try:
        price_data = api_get(
            "electricity-pricing/app-price", clever_headers,
            params={"darReferenceId": dar_id, "from": from_date},
        )
        prices = price_data.get("prices", [])
        ok(f"Electricity prices: {len(prices)} hourly entries")
    except SystemExit:
        print("  (electricity price unavailable — continuing)")

# ── Step 5: Entity preview ─────────────────────────────────────────
step(5, "HA entity preview")

for inst in installations:
    connector_id = inst.get("connectorId", "?")
    inst_id = inst.get("installationId")
    profile = profile_by_connector.get(connector_id, {})
    strategy = (profile.get("strategySettings") or {})
    cfg = smart_cfg(inst)

    print(f"\n  Device: Clever EV Charger (Connector {connector_id})")
    print(f"  Address: {inst.get('address')}, {inst.get('city')}")
    print(f"  Installation ID: {inst_id}  Charge Box: {inst.get('chargeBoxId')}")
    print()

    rows = [
        ("sensor",        "Charger State",       inst.get("detailedInstallationStatus", "unavailable")),
        ("sensor",        "Online Status",        "Online" if inst.get("isOnline") else "Offline"),
        ("sensor",        "Last Session Energy",  last_session_kwh(records, connector_id)),
        ("sensor",        "Monthly Energy",       monthly_kwh(records, connector_id)),
        ("sensor",        "Departure Time",       (cfg.get("departureTime") or {}).get("time", "unavailable")),
        ("number",         "Desired Range",        f"{(cfg.get('desiredRange') or {}).get('desiredRange', '?')} kWh"),
        ("sensor",        "Phase Count",          str((cfg.get("configuredEffect") or {}).get("phaseCount", "?"))),
        ("sensor",        "Max Ampere",           f"{(cfg.get('configuredEffect') or {}).get('ampere', '?')} A"),
        ("binary_sensor", "Smart Charging",       "ON" if inst.get("smartChargingIsEnabled") else "OFF"),
        ("binary_sensor", "Charger Online",       "ON" if inst.get("isOnline") else "OFF"),
        ("switch",        "Smart Charging",       "ON (read-only)" if inst.get("smartChargingIsEnabled") else "OFF (read-only)"),
        ("button",        "Boost 1 Hour",         f"POST .../chargepoints/{inst.get('chargeBoxId')}/connectors/{connector_id}/timebox-boost"),
        ("button",        "Boost Until Full",     f"POST .../chargepoints/{inst.get('chargeBoxId')}/connectors/{connector_id}/boost"),
        ("button",        "Cancel Boost",         f"POST .../chargepoints/{inst.get('chargeBoxId')}/connectors/{connector_id}/unboost"),
    ]
    # Electricity price only once (connector 1 or first)
    if connector_id == installations[0].get("connectorId"):
        rows.insert(4, ("sensor", "Electricity Price", current_hour_price(prices)))

    print_entity_table(rows)

# ── Step 6: Test power-required write endpoint ───────────────────
step(6, "PUT chargingprofiles/{id}/power-required (read-back test)")

for p in profiles:
    pid = p.get("chargingProfileId")
    if not pid:
        continue
    # Read current desired range from matching installation
    current_val = None
    for inst in installations:
        profile = profile_by_connector.get(inst.get("connectorId"))
        if profile and profile.get("chargingProfileId") == pid:
            cfg = smart_cfg(inst)
            current_val = (cfg.get("desiredRange") or {}).get("desiredRange")
            break

    if current_val is None:
        print(f"  SKIP  Profile {pid[:8]}... — no current desiredRange found")
        continue

    # Write the same value back (non-destructive round-trip)
    result = api_put(
        f"chargingprofiles/{pid}/power-required",
        clever_headers,
        {"powerRequired": current_val},
    )
    ok(f"Profile {pid[:8]}... — set powerRequired={current_val} -> {result}")

print(f"\n{'*'*60}")
print("  ALL STEPS PASSED")
print(f"{'*'*60}\n")
