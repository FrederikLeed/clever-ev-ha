"""Switches for Clever EV.

Note: canDisableSmartCharging=false on all installations — Clever controls
smart charging at the subscription level. The switch reflects current state
but write endpoints have not been confirmed. Logging a warning on toggle.
"""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
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
        CleverSmartChargingSwitch(coordinator, inst)
        for inst in coordinator.data["installations"]
    )


class CleverSmartChargingSwitch(CoordinatorEntity[CleverCoordinator], SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Smart Charging"
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator: CleverCoordinator, installation: dict) -> None:
        super().__init__(coordinator)
        self._installation_id = installation["installationId"]
        self._attr_unique_id = f"clever_ev_{self._installation_id}_smart_charging_switch"
        self._attr_device_info = _device_info(installation)

    def _installation(self) -> dict:
        for inst in self.coordinator.data.get("installations", []):
            if inst["installationId"] == self._installation_id:
                return inst
        return {}

    @property
    def is_on(self) -> bool | None:
        return self._installation().get("smartChargingIsEnabled")

    async def async_turn_on(self, **kwargs) -> None:
        _LOGGER.warning(
            "Smart charging write endpoint not yet captured — "
            "canDisableSmartCharging=false on this installation. "
            "Run a MITM session toggling smart charging in the Clever app."
        )

    async def async_turn_off(self, **kwargs) -> None:
        _LOGGER.warning(
            "Smart charging write endpoint not yet captured — "
            "canDisableSmartCharging=false on this installation. "
            "Run a MITM session toggling smart charging in the Clever app."
        )
