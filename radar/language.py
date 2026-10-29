"""Language detection: en, pl or other."""

from functools import cache
from typing import Literal

from lingua import Language, LanguageDetector, LanguageDetectorBuilder

Lang = Literal["en", "pl", "other"]
SAMPLE_CHARS = 1000
# Below this distance lingua returns None instead of guessing (short titles like "LLM agents").
MIN_RELATIVE_DISTANCE = 0.1


@cache
def _detector() -> LanguageDetector:
    """Build the detector once; it is slow to create."""
    return (
        LanguageDetectorBuilder.from_all_languages()
        .with_minimum_relative_distance(MIN_RELATIVE_DISTANCE)
        .build()
    )


def detect_lang(text: str, fallback: Lang) -> Lang:
    """Detect the language of `text`; return `fallback` when unsure."""
    language = _detector().detect_language_of(text[:SAMPLE_CHARS])
    if language is None:
        return fallback
    if language == Language.ENGLISH:
        return "en"
    if language == Language.POLISH:
        return "pl"
    return "other"
