# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Metadata constants for Amazon devices."""

ALEXA_INFO_SKILLS = [
    "Alexa.Calendar.PlayToday",
    "Alexa.Calendar.PlayTomorrow",
    "Alexa.Calendar.PlayNext",
    "Alexa.Date.Play",
    "Alexa.Time.Play",
    "Alexa.News.NationalNews",
    "Alexa.FlashBriefing.Play",
    "Alexa.Traffic.Play",
    "Alexa.Weather.Play",
    "Alexa.CleanUp.Play",
    "Alexa.GoodMorning.Play",
    "Alexa.SingASong.Play",
    "Alexa.FunFact.Play",
    "Alexa.Joke.Play",
    "Alexa.TellStory.Play",
    "Alexa.ImHome.Play",
    "Alexa.GoodNight.Play",
]

# Utterance types that carry no usable command for a device
UTTERANCE_TYPES_TO_SKIP = [
    "ASR_TIMEOUT",
    "DEVICE_ARBITRATION",
    "FALSE_WAKE_WORD_1P",
    "NO_EXPRESSED_INTENT",
    "WAKE_WORD_ONLY",
]

SEQUENCE_BATCH_DELAY = 0.3  # seconds

VOLUME_MAX = 100
VOLUME_MIN = 0
