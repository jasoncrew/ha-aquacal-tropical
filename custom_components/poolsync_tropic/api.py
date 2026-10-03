"""Minimal async client for the PoolSync cloud API (TropiCal heat pumps)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import (
    BASE_URL,
    COMMAND_ATTEMPTS,
    COMMAND_RETRY_DELAY,
    REQUEST_TIMEOUT,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


class TropicApiError(Exception):
    """Generic API or communication error."""


class TropicAuthError(TropicApiError):
    """Login rejected or token no longer accepted."""


class TropicCommandTimeout(TropicApiError):
    """The cloud could not relay a command to the heat pump in time."""


class TropicInvalidCombination(TropicApiError):
    """The cloud rejected the heat mode / power mode pair a command would produce."""


class TropicApiClient:
    """Talks to the same cloud endpoints the PoolSync app uses."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._token: str | None = None
        self._login_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

    def _headers(self) -> dict[str, str]:
        headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "user-agent": USER_AGENT,
            "accept-language": "en-US,en;q=0.9",
        }
        if self._token:
            headers["authorization"] = self._token
        return headers

    async def async_login(self) -> None:
        """Log in and store a fresh access token."""
        async with self._login_lock:
            try:
                async with self._session.post(
                    f"{BASE_URL}/auth/login",
                    json={"email": self._email, "password": self._password},
                    headers=self._headers() | {"authorization": ""},
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as resp:
                    if resp.status in (400, 401, 403):
                        raise TropicAuthError(f"Login rejected (HTTP {resp.status})")
                    if resp.status != 200:
                        raise TropicApiError(f"Login failed (HTTP {resp.status})")
                    body = await resp.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError) as err:
                raise TropicApiError(f"Cannot reach PoolSync cloud: {err}") from err

            token = (body or {}).get("tokens", {}).get("access")
            if not token:
                raise TropicAuthError("Login response did not contain an access token")
            self._token = token
            _LOGGER.debug("Logged in to PoolSync cloud")

    async def _request(
        self, method: str, path: str, json_data: Any | None = None, *, retry: bool = True
    ) -> Any:
        if not self._token:
            await self.async_login()
        try:
            async with self._session.request(
                method,
                f"{BASE_URL}{path}",
                json=json_data,
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status in (401, 403):
                    if retry:
                        _LOGGER.debug("Token rejected on %s, logging in again", path)
                        self._token = None
                        return await self._request(method, path, json_data, retry=False)
                    raise TropicAuthError(f"Not authorized for {path} (HTTP {resp.status})")
                if resp.status >= 400:
                    text = await resp.text()
                    if resp.status >= 500 and ("timeout" in text or "ReplyStatus" in text):
                        raise TropicCommandTimeout(f"Heat pump did not answer: {text[:200]}")
                    if "Invalid combination" in text:
                        raise TropicInvalidCombination(text[:200])
                    raise TropicApiError(f"HTTP {resp.status} on {path}: {text[:200]}")
                if resp.status == 204:
                    return {}
                text = await resp.text()
                if not text:
                    return {}
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise TropicApiError(f"Error talking to PoolSync cloud: {err}") from err

    async def async_get_user(self) -> dict[str, Any]:
        """Return the account record, including registered TropiCal serials."""
        data = await self._request("GET", "/user")
        return (data or {}).get("user", {})

    async def async_get_tropic_serials(self) -> list[str]:
        """Return the serial numbers of TropiCal units on the account."""
        user = await self.async_get_user()
        return [
            d["serialNum"]
            for d in user.get("myDevicesTropic", []) or []
            if isinstance(d, dict) and d.get("serialNum")
        ]

    async def async_get_tropic(self, serial: str) -> dict[str, Any]:
        """Return the current state of one TropiCal heat pump."""
        data = await self._request("GET", f"/tropic/{serial}")
        if not isinstance(data, dict) or "serialNum" not in data:
            raise TropicApiError(f"Unexpected response for {serial}: {str(data)[:200]}")
        return data

    async def async_set_tropic(self, serial: str, changes: dict[str, Any]) -> None:
        """Send one change, e.g. {"setpoint": 99}, {"heatMode": 2}, {"powerMode": 3}.

        The heat pump accepts one command at a time and the cloud answers
        HTTP 500 "timeout" when it is still busy, so writes are serialized
        and retried with a pause between attempts.
        """
        async with self._write_lock:
            for attempt in range(1, COMMAND_ATTEMPTS + 1):
                try:
                    await self._request("PATCH", f"/tropic/{serial}", changes)
                    return
                except TropicCommandTimeout:
                    if attempt == COMMAND_ATTEMPTS:
                        raise
                    _LOGGER.debug(
                        "Heat pump busy (attempt %s/%s) sending %s, retrying",
                        attempt, COMMAND_ATTEMPTS, changes,
                    )
                    await asyncio.sleep(COMMAND_RETRY_DELAY)
