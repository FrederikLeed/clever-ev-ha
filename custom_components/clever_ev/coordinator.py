"""DataUpdateCoordinator for Clever EV."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CleverApi, CleverAuthError, CleverApiError
from .const import DOMAIN, SCAN_INTERVAL_FAST

_LOGGER = logging.getLogger(__name__)


class CleverCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator: polls fast data every minute, slow data every 30 min."""

    def __init__(self, hass: HomeAssistant, api: CleverApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_FAST),
        )
        self.api = api
        self._slow_data: dict[str, Any] = {}
        self._slow_updated_at: datetime = datetime.min.replace(tzinfo=timezone.utc)
        # Optimistic boost state: key = connectorId, value = boost label string
        self._boost_overrides: dict[int, str | None] = {}

    def set_boost_state(self, connector_id: int, state: str | None) -> None:
        """Set optimistic boost state for a connector.

        state: "Boost 1 Hour", "Boost Until Full", or None to clear (Smart Charging).
        """
        self._boost_overrides[connector_id] = state

    def get_boost_state(self, connector_id: int) -> str | None:
        """Get optimistic boost state, or None if not overridden."""
        return self._boost_overrides.get(connector_id)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            fast = await self._fetch_fast()
            slow = await self._fetch_slow_if_due(fast)
        except ConfigEntryAuthFailed:
            raise
        except CleverAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (CleverApiError, aiohttp.ClientError) as err:
            raise UpdateFailed(str(err)) from err
        return {**fast, **slow}

    async def _fetch_fast(self) -> dict[str, Any]:
        """Fetch installations + charging profiles, keyed by installationId."""
        installations = await self.api.async_get_installations()
        profiles = await self.api.async_get_charging_profiles()

        # Build lookup: connectorId -> profile
        profile_by_connector: dict[int, dict] = {}
        for p in profiles:
            for loc in (p.get("filters") or {}).get("locations", []):
                for cp in loc.get("chargePoints", []):
                    profile_by_connector[cp["connectorId"]] = p

        # Annotate each installation with its matching profile
        for inst in installations:
            connector_id = inst.get("connectorId")
            inst["_profile"] = profile_by_connector.get(connector_id, {})

        # dar_reference_id is the same location for all connectors — grab from first profile
        dar_id: str | None = None
        for p in profiles:
            locs = (p.get("filters") or {}).get("locations", [])
            if locs:
                dar_id = locs[0]["id"]
                break

        return {
            "installations": installations,
            "profiles": profiles,
            "dar_reference_id": dar_id,
        }

    async def _fetch_slow_if_due(self, fast: dict[str, Any]) -> dict[str, Any]:
        """Fetch consumption + pricing every 30 min."""
        now = datetime.now(tz=timezone.utc)
        if (now - self._slow_updated_at).total_seconds() < 1800:
            return self._slow_data

        history = await self.api.async_get_consumption_history()
        surcharge = await self.api.async_get_energy_surcharge()

        price_data: dict = {}
        dar_id = fast.get("dar_reference_id")
        if dar_id:
            try:
                from_date = now.strftime("%Y-%m-%dT00:00:00.000Z")
                price_data = await self.api.async_get_electricity_price(dar_id, from_date)
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Could not fetch electricity price", exc_info=True)

        self._slow_data = {
            "history": history,
            "surcharge": surcharge,
            "electricity_price": price_data,
        }
        self._slow_updated_at = now
        return self._slow_data
