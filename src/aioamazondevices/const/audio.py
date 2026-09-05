# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Audio constants for Amazon devices."""

AUDIO_SPECS_URL = "https://developer.amazon.com/en-US/docs/alexa/alexa-presentation-language/apla-audio.html#audio-file-support"

AUDIO_FILE_FORMATS = ["aac", "mp3", "ogg", "opus", "wav", "flac", "m4a"]

AUDIO_FILE_MAX_SAMPLERATE = 48000
AUDIO_FILE_MAX_BITRATE = 1411.20
AUDIO_FILE_MAX_DURATION = 240
AUDIO_FILE_MAX_SIZE = 10 * 1024 * 1024  # equivalent to 10 MB
