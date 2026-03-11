"""Button entities for Clever EV."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.components.button import ButtonEntity
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
    entities = []
    for inst in coordinator.data["installations"]:
        entities.append(CleverTimeboxBoostButton(coordinator, inst))
        entities.append(CleverBoostButton(coordinator, inst))
        entities.append(CleverUnboostButton(coordinator, inst))
    async_add_entities(entities)


class _CleverBoostButton(CoordinatorEntity[CleverCoordinator], ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: CleverCoordinator, installation: dict) -> None:
        super().__init__(coordinator)
        self._installation_id = installation["installationId"]
        self._charge_box_id = installation.get("chargeBoxId", "")
        self._connector_id = installation.get("connectorId", 1)
        self._attr_device_info = _device_info(installation)


class CleverTimeboxBoostButton(_CleverBoostButton):
    _attr_name = "Boost 1 Hour"
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: CleverCoordinator, installation: dict) -> None:
        super().__init__(coordinator, installation)
        self._attr_unique_id = f"clever_ev_{self._installation_id}_timebox_boost"

    async def async_press(self) -> None:
        await self.coordinator.api.async_timebox_boost(
            self._charge_box_id, self._connector_id
        )
        self.coordinator.set_boost_state(self._connector_id, "Boost 1 Hour")
        self.coordinator.async_set_updated_data(self.coordinator.data)


class CleverBoostButton(_CleverBoostButton):
    _attr_name = "Boost Until Full"
    _attr_icon = "mdi:battery-charging-100"

    def __init__(self, coordinator: CleverCoordinator, installation: dict) -> None:
        super().__init__(coordinator, installation)
        self._attr_unique_id = f"clever_ev_{self._installation_id}_boost"

    async def async_press(self) -> None:
        await self.coordinator.api.async_boost(
            self._charge_box_id, self._connector_id
        )
        self.coordinator.set_boost_state(self._connector_id, "Boost Until Full")
        self.coordinator.async_set_updated_data(self.coordinator.data)


class CleverUnboostButton(_CleverBoostButton):
    _attr_name = "Cancel Boost"
    _attr_icon = "mdi:lightning-bolt-circle"

    def __init__(self, coordinator: CleverCoordinator, installation: dict) -> None:
        super().__init__(coordinator, installation)
        self._attr_unique_id = f"clever_ev_{self._installation_id}_unboost"

    async def async_press(self) -> None:
        await self.coordinator.api.async_unboost(
            self._charge_box_id, self._connector_id
        )
        self.coordinator.set_boost_state(self._connector_id, None)
        self.coordinator.async_set_updated_data(self.coordinator.data)
