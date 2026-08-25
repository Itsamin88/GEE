"""Language detection and country-to-language mapping.

Local-language search regularly doubles what a crawl finds (register Stage 8),
so getting the language right matters. Detection uses, in order: an explicit
HTML/HTTP declaration, a TLD, a stop-word profile, and the community's country.
An optional ``langdetect`` install refines the stop-word step; without it the
heuristic still works and the method used is recorded.
"""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlsplit

COUNTRY_LANGUAGE = {
    "France": "fr", "Belgium": "fr", "Switzerland": "de", "Luxembourg": "fr",
    "Netherlands": "nl", "Germany": "de", "Austria": "de",
    "Spain": "es", "Portugal": "pt", "Brazil": "pt", "Italy": "it",
    "Sweden": "sv", "Denmark": "da", "Norway": "no", "Finland": "fi",
    "Poland": "pl", "Czechia": "cs", "Czech Republic": "cs", "Romania": "ro",
    "Hungary": "hu", "Greece": "el", "Turkey": "tr",
    "United Kingdom": "en", "Ireland": "en", "United States": "en", "Canada": "en",
    "Australia": "en", "New Zealand": "en", "South Africa": "en", "India": "en",
    "Argentina": "es", "Chile": "es", "Colombia": "es", "Mexico": "es", "Peru": "es",
}

TLD_LANGUAGE = {
    "fr": "fr", "nl": "nl", "de": "de", "at": "de", "ch": "de", "be": "nl",
    "es": "es", "pt": "pt", "br": "pt", "it": "it", "se": "sv", "dk": "da",
    "no": "no", "fi": "fi", "pl": "pl", "cz": "cs", "ro": "ro", "hu": "hu",
    "gr": "el", "tr": "tr", "uk": "en", "ie": "en", "us": "en", "ca": "en",
}

# Short, high-frequency function words: enough to separate the languages this
# study actually meets, and cheap enough to run on every page.
STOP_WORDS = {
    "en": {"the", "and", "of", "to", "we", "our", "is", "for", "with", "that", "this", "are"},
    "fr": {"le", "la", "les", "des", "nous", "notre", "est", "pour", "avec", "que", "une", "du"},
    "nl": {"de", "het", "een", "van", "wij", "onze", "is", "voor", "met", "dat", "en", "op"},
    "de": {"der", "die", "das", "und", "wir", "unser", "ist", "für", "mit", "dass", "ein", "den"},
    "es": {"el", "la", "los", "las", "nosotros", "nuestro", "es", "para", "con", "que", "una", "del"},
    "pt": {"o", "os", "as", "nós", "nosso", "é", "para", "com", "que", "uma", "dos", "não"},
    "it": {"il", "lo", "gli", "noi", "nostro", "è", "per", "con", "che", "una", "dei", "del"},
    "sv": {"och", "att", "det", "som", "vi", "vår", "är", "för", "med", "en", "på", "av"},
    "da": {"og", "at", "det", "som", "vi", "vores", "er", "for", "med", "en", "på", "af"},
    "no": {"og", "at", "det", "som", "vi", "vår", "er", "for", "med", "en", "på", "av"},
    "pl": {"i", "w", "na", "nie", "to", "jest", "z", "do", "się", "że", "dla", "nasz"},
}

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def language_for_country(country: str | None) -> str:
    return COUNTRY_LANGUAGE.get(country or "", "en")


def guess_language(text: str, *, url: str | None = None, declared: str | None = None,
                   country: str | None = None) -> str:
    """Best available guess, cheapest reliable signal first."""
    if declared:
        code = declared.split("-")[0].strip().lower()
        if len(code) == 2:
            return code

    scored = _stopword_language(text)
    if scored:
        return scored

    try:
        from langdetect import detect  # type: ignore

        if text and len(text) > 120:
            return str(detect(text[:4000])).split("-")[0].lower()
    except Exception:
        pass

    if url:
        host = (urlsplit(url).hostname or "").lower()
        tld = host.rsplit(".", 1)[-1] if "." in host else ""
        if tld in TLD_LANGUAGE:
            return TLD_LANGUAGE[tld]

    return language_for_country(country)


def _stopword_language(text: str) -> str | None:
    if not text or len(text) < 80:
        return None
    words = [w.lower() for w in _WORD.findall(text[:8000])]
    if len(words) < 25:
        return None
    counts = Counter(words)
    scores = {
        language: sum(counts.get(word, 0) for word in stops)
        for language, stops in STOP_WORDS.items()
    }
    best = max(scores, key=lambda k: scores[k])
    runner_up = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0
    if scores[best] >= 6 and scores[best] >= runner_up * 1.3:
        return best
    return None


def detection_method(text: str, declared: str | None) -> str:
    if declared:
        return "declared in the page markup"
    if _stopword_language(text):
        return "stop-word profile of the retrieved text"
    return "country default"
