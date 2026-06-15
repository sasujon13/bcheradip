#!/usr/bin/env python3
"""Build tier-1 JSON language packs for API serving."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKS_DIR = ROOT / "packs"

# Core vocabulary per language (offline dictionary seed — extend via pack-builder later)
PACK_DATA: dict[str, dict] = {
    "en": {
        "entries": {
            "hello": ["a greeting", "used to attract attention"],
            "world": ["the earth", "human society"],
            "learn": ["gain knowledge", "memorize"],
            "language": ["system of communication", "speech of a nation"],
            "book": ["written work", "bound pages"],
            "read": ["look at and comprehend text", "interpret symbols"],
            "word": ["single unit of language", "promise"],
            "good": ["of high quality", "morally right"],
            "morning": ["early part of the day"],
            "thank": ["express gratitude"],
            "you": ["second person pronoun"],
        },
        "phrases": {
            "good morning": "A polite greeting used in the morning.",
            "thank you": "Expression of gratitude.",
            "how are you": "A common greeting asking about someone's state.",
        },
        "translations": {
            "hello|fr": "bonjour",
            "good morning|fr": "bonjour",
            "thank you|fr": "merci",
            "hello|es": "hola",
            "thank you|es": "gracias",
        },
    },
    "fr": {
        "entries": {
            "bonjour": ["hello", "good day"],
            "merci": ["thank you"],
            "français": ["French language", "French people"],
            "livre": ["book"],
            "apprendre": ["to learn"],
            "mot": ["word"],
            "lire": ["to read"],
            "langue": ["language", "tongue"],
            "matin": ["morning"],
            "bien": ["good", "well"],
        },
        "phrases": {
            "bonjour": "Standard French greeting.",
            "comment allez-vous": "Formal: how are you?",
            "merci beaucoup": "Thank you very much.",
        },
        "translations": {
            "bonjour|en": "hello",
            "merci|en": "thank you",
            "bonjour|es": "hola",
        },
    },
    "es": {
        "entries": {
            "hola": ["hello"],
            "gracias": ["thank you"],
            "libro": ["book"],
            "aprender": ["to learn"],
            "palabra": ["word"],
            "leer": ["to read"],
            "idioma": ["language"],
            "mañana": ["morning", "tomorrow"],
            "bueno": ["good"],
            "mundo": ["world"],
        },
        "phrases": {
            "buenos días": "Good morning.",
            "muchas gracias": "Thank you very much.",
            "¿cómo estás?": "How are you? (informal)",
        },
        "translations": {
            "hola|en": "hello",
            "gracias|en": "thank you",
            "hola|fr": "bonjour",
        },
    },
    "de": {
        "entries": {
            "hallo": ["hello"],
            "danke": ["thank you"],
            "buch": ["book"],
            "lernen": ["to learn"],
            "wort": ["word"],
            "lesen": ["to read"],
            "sprache": ["language"],
            "morgen": ["morning", "tomorrow"],
            "gut": ["good"],
            "welt": ["world"],
        },
        "phrases": {
            "guten morgen": "Good morning.",
            "vielen dank": "Thank you very much.",
            "wie geht es dir": "How are you?",
        },
        "translations": {
            "hallo|en": "hello",
            "danke|en": "thank you",
        },
    },
    "bn": {
        "entries": {
            "নমস্কার": ["hello", "greeting"],
            "ধন্যবাদ": ["thank you"],
            "বই": ["book"],
            "শেখা": ["to learn"],
            "শব্দ": ["word"],
            "পড়া": ["to read"],
            "ভাষা": ["language"],
            "সকাল": ["morning"],
            "ভালো": ["good"],
            "বিশ্ব": ["world"],
        },
        "phrases": {
            "আপনি কেমন আছেন": "How are you? (formal)",
            "অনেক ধন্যবাদ": "Thank you very much.",
        },
        "translations": {
            "নমস্কার|en": "hello",
            "ধন্যবাদ|en": "thank you",
        },
    },
    "hi": {
        "entries": {
            "नमस्ते": ["hello", "greeting"],
            "धन्यवाद": ["thank you"],
            "किताब": ["book"],
            "सीखना": ["to learn"],
            "शब्द": ["word"],
            "पढ़ना": ["to read"],
            "भाषा": ["language"],
            "सुप्रभात": ["good morning"],
            "अच्छा": ["good"],
            "दुनिया": ["world"],
        },
        "phrases": {
            "आप कैसे हैं": "How are you? (formal)",
            "बहुत धन्यवाद": "Thank you very much.",
        },
        "translations": {"नमस्ते|en": "hello", "धन्यवाद|en": "thank you"},
    },
    "ar": {
        "entries": {
            "مرحبا": ["hello"],
            "شكرا": ["thank you"],
            "كتاب": ["book"],
            "تعلم": ["to learn"],
            "كلمة": ["word"],
            "قراءة": ["reading"],
            "لغة": ["language"],
            "صباح": ["morning"],
            "جيد": ["good"],
            "عالم": ["world"],
        },
        "phrases": {
            "صباح الخير": "Good morning.",
            "شكرا جزيلا": "Thank you very much.",
        },
        "translations": {"مرحبا|en": "hello", "شكرا|en": "thank you"},
    },
    "ja": {
        "entries": {
            "こんにちは": ["hello", "good afternoon"],
            "ありがとう": ["thank you"],
            "本": ["book"],
            "学ぶ": ["to learn"],
            "言葉": ["word", "language"],
            "読む": ["to read"],
            "言語": ["language"],
            "おはよう": ["good morning"],
            "良い": ["good"],
            "世界": ["world"],
        },
        "phrases": {
            "おはようございます": "Good morning (polite).",
            "ありがとうございます": "Thank you (polite).",
        },
        "translations": {"こんにちは|en": "hello", "ありがとう|en": "thank you"},
    },
    "pt": {
        "entries": {
            "olá": ["hello"],
            "obrigado": ["thank you (m)"],
            "obrigada": ["thank you (f)"],
            "livro": ["book"],
            "aprender": ["to learn"],
            "palavra": ["word"],
            "ler": ["to read"],
            "língua": ["language"],
            "manhã": ["morning"],
            "bom": ["good"],
            "mundo": ["world"],
        },
        "phrases": {
            "bom dia": "Good morning.",
            "muito obrigado": "Thank you very much.",
        },
        "translations": {"olá|en": "hello", "obrigado|en": "thank you"},
    },
    "zh": {
        "entries": {
            "你好": ["hello"],
            "谢谢": ["thank you"],
            "书": ["book"],
            "学习": ["to learn", "study"],
            "词": ["word"],
            "读": ["to read"],
            "语言": ["language"],
            "早上": ["morning"],
            "好": ["good"],
            "世界": ["world"],
        },
        "phrases": {
            "早上好": "Good morning.",
            "非常感谢": "Thank you very much.",
        },
        "translations": {"你好|en": "hello", "谢谢|en": "thank you"},
    },
}


def build_all() -> None:
    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    for code, data in PACK_DATA.items():
        out_dir = PACKS_DIR / code
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "languageCode": code,
            "entries": data["entries"],
            "phrases": data["phrases"],
            "translations": data["translations"],
        }
        path = out_dir / "v1.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    build_all()
