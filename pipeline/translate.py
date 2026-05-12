"""deep-translator (GoogleTranslator) wrapper."""

from __future__ import annotations


def translate_text(text: str, source_code: str, target_code: str) -> str:
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source=source_code, target=target_code).translate(text)
