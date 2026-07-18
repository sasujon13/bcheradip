"""Seed template teen-voices/ folders under grammar_books/{code}/ for starter languages."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAMMAR = ROOT / "grammar_books"

# locale + Android voice name hints for clearer synthesis when device voices exist
TEMPLATES: dict[str, dict] = {
    "en": {
        "locale": "en-US",
        "hints": ["en-us", "en-gb", "english", "neural", "wavenet"],
    },
    "bn": {
        "locale": "bn-BD",
        "hints": ["bn-bd", "bn-in", "bengali", "bangla", "bn_"],
    },
    "hi": {
        "locale": "hi-IN",
        "hints": ["hi-in", "hindi", "hi_"],
    },
    "ar": {
        "locale": "ar-SA",
        "hints": ["ar-sa", "ar-eg", "arabic", "ar_"],
    },
    "es": {
        "locale": "es-ES",
        "hints": ["es-es", "es-mx", "spanish", "es_"],
    },
    "fr": {
        "locale": "fr-FR",
        "hints": ["fr-fr", "french", "fr_"],
    },
    "de": {
        "locale": "de-DE",
        "hints": ["de-de", "german", "de_"],
    },
    "ja": {
        "locale": "ja-JP",
        "hints": ["ja-jp", "japanese", "ja_"],
    },
    "ko": {
        "locale": "ko-KR",
        "hints": ["ko-kr", "korean", "ko_"],
    },
    "zh": {
        "locale": "zh-CN",
        "hints": ["zh-cn", "cmn", "chinese", "zh_"],
    },
    "ru": {
        "locale": "ru-RU",
        "hints": ["ru-ru", "russian", "ru_"],
    },
    "tr": {
        "locale": "tr-TR",
        "hints": ["tr-tr", "turkish", "tr_"],
    },
    "id": {
        "locale": "id-ID",
        "hints": ["id-id", "indonesian", "id_"],
    },
    "vi": {
        "locale": "vi-VN",
        "hints": ["vi-vn", "vietnamese", "vi_"],
    },
    "pt": {
        "locale": "pt-BR",
        "hints": ["pt-br", "pt-pt", "portuguese", "pt_"],
    },
}


def write_voice_json(path: Path, code: str, gender: str, locale: str, hints: list[str]) -> None:
    pitch = 1.10 if gender == "male" else 1.20
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / "model").mkdir(exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "engine": "android",
                "languageCode": code,
                "gender": gender,
                "version": 1,
                "pitch": pitch,
                "speechRateBias": 0.92,
                "locale": locale,
                "preferredVoiceNameHints": hints,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def seed(code: str, force: bool = False) -> bool:
    code = code.lower()
    lang_dir = GRAMMAR / code
    if not lang_dir.is_dir():
        print(f"skip {code}: no grammar_books/{code}")
        return False
    cfg = TEMPLATES.get(code) or {
        "locale": code,
        "hints": [code, f"{code}-", f"{code}_"],
    }
    root = lang_dir / "teen-voices"
    manifest = root / "manifest.json"
    if manifest.is_file() and not force:
        print(f"exists {code}")
        return True
    root.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "languageCode": code,
                "genders": ["male", "female"],
                "engine": "android",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for gender in ("male", "female"):
        write_voice_json(
            root / gender / "voice.json",
            code,
            gender,
            cfg["locale"],
            cfg["hints"],
        )
    print(f"seeded {code} -> {root}")
    return True


def main() -> int:
    force = "--force" in sys.argv
    codes = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not codes:
        # Seed every language that already has a grammar ebook folder
        codes = sorted(p.name for p in GRAMMAR.iterdir() if p.is_dir() and not p.name.startswith("."))
    ok = 0
    for code in codes:
        if seed(code, force=force):
            ok += 1
    print(f"done: {ok} languages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
