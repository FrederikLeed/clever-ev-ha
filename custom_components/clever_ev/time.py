"""Time entities for Clever EV."""
from __future__ import annotations

import logging
from datetime import time as dt_time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CleverCoordinator
from .sensor import _device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CleverCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CleverDepartureTime(coordinator, inst)
        for inst in coordinator.data["installations"]
    )


class CleverDepartureTime(CoordinatorEntity[CleverCoordinator], TimeEntity):
    _attr_has_entity_name = True
    _attr_name = "Departure Time"
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: CleverCoordinator, installation: dict) -> None:
        super().__init__(coordinator)
        self._installation_id = installation["installationId"]
        self._connector_id = installation.get("connectorId", 1)
        self._attr_unique_id = f"clever_ev_{self._installation_id}_departure_time"
        self._attr_device_info = _device_info(installation)

    def _installation(self) -> dict:
        for inst in self.coordinator.data.get("installations", []):
            if inst["installationId"] == self._installation_id:
                return inst
        return {}

    def _charging_profile_id(self) -> str | None:
        profile = self._installation().get("_profile") or {}
        return profile.get("chargingProfileId")

    @property
    def native_value(self) -> dt_time | None:
        cfg = (
            (self._installation().get("smartChargingConfiguration") or {})
            .get("userConfiguration") or {}
        )
        time_str = (cfg.get("departureTime") or {}).get("time")
        if not time_str:
            return None
        try:
            parts = time_str.split(":")
            return dt_time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return None

    async def async_set_value(self, value: dt_time) -> None:
        profile_id = self._charging_profile_id()
        if not profile_id:
            _LOGGER.error("No charging profile found for installation %s", self._installation_id)
            return
        time_str = value.strftime("%H:%M")
        await self.coordinator.api.async_set_departure_time(profile_id, time_str)
        await self.coordinator.async_request_refresh()
