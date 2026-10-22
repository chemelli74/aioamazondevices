# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Constants for retrying voice history after an EQ push."""

HISTORY_INITIAL_DELAY_SECONDS = 3.5
HISTORY_RETRY_DELAY_SECONDS = 4
HISTORY_PROBE_ATTEMPTS = 4

# Allow delayed EQ delivery and history clock skew relative to push receipt.
HISTORY_FRESHNESS_WINDOW_MS = 60_000
