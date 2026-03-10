"""Binary sensors for Clever EV."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CleverCoordinator
from .sensor import _device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CleverCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for inst in coordinator.data["installations"]:
        entities.append(CleverSmartChargingBinarySensor(coordinator, inst))
        entities.append(CleverOnlineBinarySensor(coordinator, inst))
    async_add_entities(entities)


class _CleverBinarySensor(CoordinatorEntity[CleverCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: CleverCoordinator, installation: dict) -> None:
        super().__init__(coordinator)
        self._installation_id = installation["installationId"]
        self._attr_device_info = _device_info(installation)

    def _installation(self) -> dict:
        for inst in self.coordinator.data.get("installations", []):
            if inst["installationId"] == self._installation_id:
                return inst
        return {}


class CleverSmartChargingBinarySensor(_CleverBinarySensor):
    _attr_name = "Smart Charging"
    _attr_icon = "mdi:brain"

    def __init__(self, coordinator: CleverCoordinator, installation: dict) -> None:
        super().__init__(coordinator, installation)
        self._attr_unique_id = f"clever_ev_{self._installation_id}_smart_charging"

    @property
    def is_on(self) -> bool | None:
        return self._installation().get("smartChargingIsEnabled")


class CleverOnlineBinarySensor(_CleverBinarySensor):
    _attr_name = "Charger Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: CleverCoordinator, installation: dict) -> None:
        super().__init__(coordinator, installation)
        self._attr_unique_id = f"clever_ev_{self._installation_id}_online"

    @property
    def is_on(self) -> bool | None:
        return self._installation().get("isOnline")
