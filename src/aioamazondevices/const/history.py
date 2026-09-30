# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Constants for voice history requests and probes."""

import re

# Allow the RVH voice record to appear after an EQ push, then retry at a
# measured pace if Amazon has not published it yet.
HISTORY_PROBE_DELAY_SECONDS = 3.5
HISTORY_RETRY_DELAY_SECONDS = 4
HISTORY_PROBE_ATTEMPTS = 4
HISTORY_STALE_FUDGE_MS = 10_000
HISTORY_LOOKBACK_MS = 15 * 60 * 1000
HISTORY_MAX_RECORD_SIZE = 20
HISTORY_STARTUP_LOOKBACK_MS = 7 * 24 * 60 * 60 * 1000
RECORD_KEY_SERIAL_INDEX = 3
EXCLUDED_VOICE_HISTORY_TYPES = {
    "ASR_TIMEOUT",
    "DEVICE_ARBITRATION",
    "NO_EXPRESSED_INTENT",
    "WAKE_WORD_ONLY",
}
WAKE_WORD_PREFIX = re.compile(
    r"^(?:alexa|amazon|computer|echo|ziggy)(?:[\s,.:!?]+)(.*)$",
    re.IGNORECASE,
)
