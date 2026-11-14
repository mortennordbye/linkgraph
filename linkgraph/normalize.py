"""Normalization helpers: company keys, profile slugs, seniority tiers."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from urllib.parse import unquote

LEGAL_SUFFIXES = {
    "as", "asa", "ab", "a/s", "aps", "oy", "oyj", "inc", "ltd", "limited", "llc",
    "gmbh", "plc", "corp", "corporation", "co", "bv", "sa", "ag", "srl", "pty",
    "ab publ", "ks", "da", "sas", "nv", "llp", "company",
}
REGION_WORDS = {
    "norge", "norway", "sverige", "sweden", "danmark", "denmark", "nordic",
    "nordics", "india", "finland", "suomi", "uk", "usa", "us", "international",
    "global", "group", "gruppen",
}
_STRIP_TOKENS = LEGAL_SUFFIXES | REGION_WORDS

_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")
_PUNCT_RE = re.compile(r"[^\w\s/]+", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def company_key(name: str) -> str:
    """Return a grouping key so 'Acme', 'Acme AS' and 'ACME Norge AS' match."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name).strip().casefold()
    # Drop trailing parenthesized parts such as "(NHH)" if something remains.
    while True:
        t = _PAREN_RE.sub("", s)
        if t == s or not t.strip():
            break
        s = t
    s = s.replace("&", " and ")
    s = s.replace("a/s", " as ")
    s = _PUNCT_RE.sub(" ", s)
    tokens = _WS_RE.sub(" ", s).strip().split(" ")
    tokens = [t for t in tokens if t]
    while len(tokens) > 1 and tokens[-1] in _STRIP_TOKENS:
        tokens.pop()
    return " ".join(tokens)


GENERIC_KEYS = {
    "self employed", "selfemployed", "self", "freelance", "freelancer", "independent",
    "selvstendig", "selvstendig næringsdrivende", "stealth", "stealth startup", "stealth mode",
    "retired", "pensjonist", "student", "confidential", "various", "n/a", "na", "none",
}


def is_generic(key: str) -> bool:
    return key in GENERIC_KEYS


def display_name(variants: Counter) -> str:
    """Most common original spelling; ties go to the shortest."""
    best = sorted(variants.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))
    return best[0][0] if best else ""


_SLUG_RE = re.compile(r"linkedin\.com/in/([^/?#\s,]+)", re.IGNORECASE)


def slug_from_url(url: str) -> str:
    """Extract the /in/<slug> part, lowercased and URL-decoded."""
    if not url:
        return ""
    m = _SLUG_RE.search(url)
    if not m:
        return ""
    return unquote(m.group(1)).strip().strip("/").casefold()


def slugs_from_urls(field: str) -> list[str]:
    """A field may hold several URLs separated by commas."""
    if not field:
        return []
    return [unquote(m.group(1)).strip("/").casefold() for m in _SLUG_RE.finditer(field)]


def name_id(first: str, last: str) -> str:
    raw = f"{first} {last}".strip().casefold()
    return "n-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def norm_name(name: str) -> str:
    s = unicodedata.normalize("NFKC", name or "").casefold()
    return _WS_RE.sub(" ", s).strip()


# Seniority tiers. Tier 4 and 3 are decision-makers.
_TIER_PATTERNS = [
    (4, r"\bchief\b|\bc[etfoi]o\b|\bciso\b|\bcpo\b|\bcro\b|\bcmo\b|\bcdo\b|founder|\bowner\b|"
        r"\bpartner\b|\bpresident\b|daglig leder|administrerende|adm\.? ?dir|styreleder|"
        r"gründer|grunnlegger|\beier\b|managing director|\bmd\b|chairman|board member|styremedlem"),
    (3, r"\bvp\b|\bsvp\b|\bevp\b|vice president|director|direktør|head of|\bhead\b|leder for|"
        r"avdelingsleder|seksjonsleder|general manager|country manager|\bdirektor\b"),
    (2, r"manager|\blead\b|\bleader\b|principal|architect|arkitekt|sjef|\bleder\b|senior|"
        r"\bteamlead|tech lead|fagansvarlig"),
]
_TIER_RES = [(tier, re.compile(p, re.IGNORECASE)) for tier, p in _TIER_PATTERNS]

TIER_LABELS = {4: "C-level / Owner", 3: "VP / Director / Head", 2: "Manager / Lead / Senior", 1: "Other"}


def seniority_tier(position: str) -> int:
    if not position:
        return 1
    for tier, rx in _TIER_RES:
        if rx.search(position):
            return tier
    return 1
