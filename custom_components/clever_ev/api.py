"""Async API client for Clever EV."""
from __future__ import annotations

import time
from typing import Any

import aiohttp

from .const import (
    BASE_URL,
    FIREBASE_API_KEY,
    FIREBASE_HEADERS,
    FIREBASE_REFRESH_URL,
    FIREBASE_SIGN_IN_URL,
    STATIC_HEADERS,
)


class CleverAuthError(Exception):
    pass


class CleverApiError(Exception):
    pass


class CleverApi:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._token: str | None = None
        self._token_expiry: float = 0.0
        self._refresh_token: str | None = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def async_sign_in(self, email: str, password: str) -> dict[str, str]:
        """Sign in with email+password. Returns {id_token, refresh_token}."""
        payload = {
            "email": email,
            "password": password,
            "clientType": "CLIENT_TYPE_IOS",
            "returnSecureToken": True,
        }
        async with self._session.post(
            FIREBASE_SIGN_IN_URL,
            params={"key": FIREBASE_API_KEY},
            headers=FIREBASE_HEADERS,
            json=payload,
        ) as resp:
            if resp.status == 400:
                raise CleverAuthError("Invalid email or password")
            if resp.status == 403:
                raise CleverAuthError("Firebase request blocked — bundle ID mismatch")
            resp.raise_for_status()
            data = await resp.json()

        self._token = data["idToken"]
        self._refresh_token = data["refreshToken"]
        self._token_expiry = time.monotonic() + int(data["expiresIn"]) - 60
        return {"id_token": data["idToken"], "refresh_token": data["refreshToken"]}

    async def async_set_refresh_token(self, refresh_token: str) -> None:
        """Load a stored refresh token and immediately exchange it for an id token."""
        self._refresh_token = refresh_token
        await self._async_refresh()

    async def _async_refresh(self) -> None:
        """Exchange refresh token for a fresh id token."""
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }
        async with self._session.post(
            FIREBASE_REFRESH_URL,
            params={"key": FIREBASE_API_KEY},
            headers={**FIREBASE_HEADERS, "content-type": "application/x-www-form-urlencoded"},
            data=payload,
        ) as resp:
            if resp.status in (400, 401, 403):
                raise CleverAuthError("Refresh token invalid or expired")
            resp.raise_for_status()
            data = await resp.json()

        self._token = data["id_token"]
        self._refresh_token = data["refresh_token"]
        self._token_expiry = time.monotonic() + int(data["expires_in"]) - 60

    async def _headers(self) -> dict[str, str]:
        if not self._token or time.monotonic() >= self._token_expiry:
            await self._async_refresh()
        return {**STATIC_HEADERS, "authorization": f"Bearer {self._token}"}

    # ------------------------------------------------------------------
    # REST helpers
    # ------------------------------------------------------------------

    async def _get(self, path: str, **params: Any) -> Any:
        url = f"{BASE_URL}/{path}"
        async with self._session.get(
            url, headers=await self._headers(), params=params or None
        ) as resp:
            if resp.status in (401, 403):
                raise CleverAuthError("Token rejected by Clever API")
            resp.raise_for_status()
            data = await resp.json()
        if not data.get("status"):
            raise CleverApiError(data.get("statusMessage", "Unknown API error"))
        return data["data"]

    async def _post(self, path: str, body: Any = None) -> Any:
        url = f"{BASE_URL}/{path}"
        kwargs: dict[str, Any] = {"headers": await self._headers()}
        if body is not None:
            kwargs["json"] = body
        async with self._session.post(url, **kwargs) as resp:
            if resp.status in (401, 403):
                raise CleverAuthError("Token rejected by Clever API")
            resp.raise_for_status()
            data = await resp.json()
        if not data.get("status"):
            raise CleverApiError(data.get("statusMessage", "Unknown API error"))
        return data["data"]

    async def _put(self, path: str, body: Any) -> Any:
        url = f"{BASE_URL}/{path}"
        async with self._session.put(
            url, headers=await self._headers(), json=body
        ) as resp:
            if resp.status in (401, 403):
                raise CleverAuthError("Token rejected by Clever API")
            resp.raise_for_status()
            data = await resp.json()
        if not data.get("status"):
            raise CleverApiError(data.get("statusMessage", "Unknown API error"))
        return data["data"]

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    async def async_get_installations(self) -> list[dict]:
        return await self._get("installations")

    async def async_get_charging_profiles(self) -> list[dict]:
        return await self._get("chargingprofiles")

    async def async_get_consumption_history(self) -> dict:
        return await self._get("consumption/history")

    async def async_get_electricity_price(
        self, dar_reference_id: str, from_date: str
    ) -> dict:
        """from_date: ISO date string e.g. '2026-03-10T00:00:00.000Z'"""
        return await self._get(
            "electricity-pricing/app-price",
            darReferenceId=dar_reference_id,
            **{"from": from_date},
        )

    async def async_get_energy_surcharge(self) -> dict:
        return await self._get("energysurcharge/estimated")

    async def async_get_profile(self) -> dict:
        return await self._get("profiles/get-profile")

    async def async_get_recommendation(self, charging_profile_id: str) -> dict:
        """Get smart charging recommendation for a profile."""
        return await self._get(f"chargingprofiles/{charging_profile_id}/recommendation")

    async def async_set_departure_time(
        self, charging_profile_id: str, departure_time: str
    ) -> str:
        """Set departure time (HH:MM). Returns 'Accepted' or raises."""
        return await self._put(
            f"chargingprofiles/{charging_profile_id}/departure-time",
            {"departureTime": departure_time},
        )

    async def async_set_power_required(
        self, charging_profile_id: str, power_kwh: int
    ) -> str:
        """Set desired charge range in kWh. Returns 'Accepted' or raises."""
        return await self._put(
            f"chargingprofiles/{charging_profile_id}/power-required",
            {"powerRequired": power_kwh},
        )

    async def async_timebox_boost(
        self, charge_box_id: str, connector_id: int
    ) -> str:
        """Disable smart charging for 1 hour."""
        return await self._post(
            f"smartcharging/chargepoints/{charge_box_id}/connectors/{connector_id}/timebox-boost"
        )

    async def async_boost(
        self, charge_box_id: str, connector_id: int
    ) -> str:
        """Disable smart charging until 100%."""
        return await self._post(
            f"smartcharging/chargepoints/{charge_box_id}/connectors/{connector_id}/boost"
        )

    async def async_unboost(
        self, charge_box_id: str, connector_id: int
    ) -> str:
        """Cancel boost — re-enable smart charging."""
        return await self._post(
            f"smartcharging/chargepoints/{charge_box_id}/connectors/{connector_id}/unboost"
        )
