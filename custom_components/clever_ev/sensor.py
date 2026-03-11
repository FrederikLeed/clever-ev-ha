"""Sensors for Clever EV."""
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
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CleverCoordinator


def _boost_status(inst: dict) -> str | None:
    """Return boost status from the profile's strategySettings."""
    strategy = (inst.get("_profile") or {}).get("strategySettings") or {}
    disabled = strategy.get("disabled")
    reason = strategy.get("reason")
    if disabled is True:
        return reason or "Boosted"
    if disabled is False:
        return "Smart Charging"
    return None


def _smart_cfg(inst: dict) -> dict:
    return (
        (inst.get("smartChargingConfiguration") or {})
        .get("userConfiguration") or {}
    )


def _current_hour_price(data: dict) -> float | None:
    prices = (data.get("electricity_price") or {}).get("prices") or []
    if not prices:
        return None
    now = datetime.now(tz=timezone.utc)
    for entry in prices:
        try:
            start = datetime.fromisoformat(entry["startTime"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(entry["endTime"].replace("Z", "+00:00"))
            if start <= now < end:
                return round(entry["totalPrice"], 4)
        except (KeyError, ValueError):
            continue
    try:
        return round(prices[-1]["totalPrice"], 4)
    except (KeyError, IndexError):
        return None


def _monthly_kwh(data: dict, connector_id: int) -> float | None:
    records = (data.get("history") or {}).get("consumptionRecords") or []
    if not records:
        return None
    now = datetime.now(tz=timezone.utc)
    total = sum(
        r.get("kWh", 0)
        for r in records
        if r.get("connectorId") == connector_id and _in_current_month(r, now)
    )
    return round(total, 3)


def _last_session_kwh(data: dict, connector_id: int) -> float | None:
    records = [
        r for r in (data.get("history") or {}).get("consumptionRecords") or []
        if r.get("connectorId") == connector_id
    ]
    if not records:
        return None
    latest = max(records, key=lambda r: r.get("stopTimeUtc", 0))
    return round(latest["kWh"], 3)


def _in_current_month(record: dict, now: datetime) -> bool:
    ts_us = record.get("stopTimeUtc")
    if not ts_us:
        return False
    try:
        dt = datetime.fromtimestamp(ts_us / 1_000_000, tz=timezone.utc)
        return dt.year == now.year and dt.month == now.month
    except (OSError, OverflowError, ValueError):
        return False


@dataclass(frozen=True, kw_only=True)
class CleverSensorDescription(SensorEntityDescription):
    # inst = installation dict (with _profile injected), data = full coordinator data
    value_fn: Callable[[dict, dict], Any]


SENSORS: tuple[CleverSensorDescription, ...] = (
    CleverSensorDescription(
        key="charger_state",
        name="Charger State",
        icon="mdi:ev-plug-type2",
        value_fn=lambda inst, _d: inst.get("detailedInstallationStatus"),
    ),
    CleverSensorDescription(
        key="online_status",
        name="Online Status",
        icon="mdi:connection",
        value_fn=lambda inst, _d: "Online" if inst.get("isOnline") else "Offline",
    ),
    CleverSensorDescription(
        key="session_kwh",
        name="Last Session Energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:lightning-bolt",
        value_fn=lambda inst, d: _last_session_kwh(d, inst.get("connectorId")),
    ),
    CleverSensorDescription(
        key="monthly_kwh",
        name="Monthly Energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:chart-bar",
        value_fn=lambda inst, d: _monthly_kwh(d, inst.get("connectorId")),
    ),
    CleverSensorDescription(
        key="boost_status",
        name="Boost Status",
        icon="mdi:lightning-bolt",
        value_fn=lambda inst, _d: _boost_status(inst),
    ),
    CleverSensorDescription(
        key="electricity_price",
        name="Electricity Price",
        native_unit_of_measurement="DKK/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:currency-usd",
        value_fn=lambda _inst, d: _current_hour_price(d),
    ),
    CleverSensorDescription(
        key="phase_count",
        name="Phase Count",
        icon="mdi:sine-wave",
        value_fn=lambda inst, _d: (_smart_cfg(inst).get("configuredEffect") or {}).get("phaseCount"),
    ),
    CleverSensorDescription(
        key="max_ampere",
        name="Max Ampere",
        native_unit_of_measurement="A",
        device_class=SensorDeviceClass.CURRENT,
        icon="mdi:current-ac",
        value_fn=lambda inst, _d: (_smart_cfg(inst).get("configuredEffect") or {}).get("ampere"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CleverCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        CleverSensor(coordinator, inst, desc)
        for inst in coordinator.data["installations"]
        for desc in SENSORS
        # Electricity price is shared — only create once (connector 1)
        if not (desc.key == "electricity_price" and inst.get("connectorId") != 1)
    ]
    async_add_entities(entities)


class CleverSensor(CoordinatorEntity[CleverCoordinator], SensorEntity):
    entity_description: CleverSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CleverCoordinator,
        installation: dict,
        description: CleverSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._installation_id = installation["installationId"]
        self._connector_id = installation.get("connectorId", 1)
        self._attr_unique_id = (
            f"clever_ev_{self._installation_id}_{description.key}"
        )
        self._attr_device_info = _device_info(installation)

    def _installation(self) -> dict:
        for inst in self.coordinator.data.get("installations", []):
            if inst["installationId"] == self._installation_id:
                return inst
        return {}

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(
            self._installation(), self.coordinator.data
        )


def _device_info(installation: dict) -> dict:
    box_type = (installation.get("chargeBoxType") or {}).get("name", "Clever Home Charger")
    connector_id = installation.get("connectorId", 1)
    return {
        "identifiers": {(DOMAIN, installation.get("installationId", "clever_ev"))},
        "name": f"Clever EV Charger (Connector {connector_id})",
        "manufacturer": "Clever",
        "model": box_type,
    }
