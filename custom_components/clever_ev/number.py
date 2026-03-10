"""Number entities for Clever EV."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
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
        CleverDesiredRangeNumber(coordinator, inst)
        for inst in coordinator.data["installations"]
    )


class CleverDesiredRangeNumber(CoordinatorEntity[CleverCoordinator], NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Desired Range"
    _attr_icon = "mdi:battery-charging-80"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_native_min_value = 5
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: CleverCoordinator, installation: dict) -> None:
        super().__init__(coordinator)
        self._installation_id = installation["installationId"]
        self._connector_id = installation.get("connectorId", 1)
        self._attr_unique_id = f"clever_ev_{self._installation_id}_desired_range"
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
    def native_value(self) -> float | None:
        cfg = (
            (self._installation().get("smartChargingConfiguration") or {})
            .get("userConfiguration") or {}
        )
        return (cfg.get("desiredRange") or {}).get("desiredRange")

    async def async_set_native_value(self, value: float) -> None:
        profile_id = self._charging_profile_id()
        if not profile_id:
            _LOGGER.error("No charging profile found for installation %s", self._installation_id)
            return
        await self.coordinator.api.async_set_power_required(profile_id, int(value))
        await self.coordinator.async_request_refresh()
