"""Constants for the AquaCal TropiCal (PoolSync Cloud) integration."""

from __future__ import annotations

DOMAIN = "poolsync_tropic"

BASE_URL = "https://lsx6q9luzh.execute-api.us-east-1.amazonaws.com/api/app"
# Mirror the PoolSync iOS app so the API treats us like the app.
USER_AGENT = "Sync/571 CFNetwork/3896.100.1.2.1 Darwin/27.0.0"
REQUEST_TIMEOUT = 20


CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 60  # seconds
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 3600

# Writes: the unit takes ~one command every few seconds.
COMMAND_ATTEMPTS = 4
COMMAND_RETRY_DELAY = 4.0
