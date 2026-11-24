# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the sounds constants."""

from aioamazondevices.const.sounds import SOUNDS_LIST


def test_sounds_list() -> None:
    """Every sound id has a name, and the names are unique."""
    assert SOUNDS_LIST["amzn_sfx_doorbell_01"] == "Doorbell 1"
    assert all(SOUNDS_LIST.values())
    assert len(set(SOUNDS_LIST.values())) == len(SOUNDS_LIST)
