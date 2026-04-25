"""Lightweight market categoriser.

We don't have ground-truth tags from Polymarket so we infer the category from
keyword heuristics on the question / slug. The categories drive the portfolio
optimiser's exposure caps. Adding a real category source later is a one-line
swap of `categorise()`.
"""
from __future__ import annotations

import re
from typing import Iterable

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "politics": (
        "election", "president", "senator", "congress", "primary",
        "vote", "ballot", "trump", "biden", "harris", "republican", "democrat",
    ),
    "macro": (
        "fed", "rate", "inflation", "gdp", "cpi", "recession", "unemployment",
        "interest rate", "treasury", "yield",
    ),
    "crypto": (
        "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "xrp", "doge",
        "crypto", "coinbase", "stablecoin", "altcoin",
    ),
    "sports": (
        "nfl", "nba", "mlb", "ufc", "f1", "world cup", "super bowl",
        "championship", "playoff", "soccer", "football", "tennis", "olympics",
    ),
    "tech": (
        "apple", "tesla", "openai", "microsoft", "google", "meta", "ai",
        "chip", "gpu", "starship", "spacex",
    ),
    "geopolitics": (
        "war", "ceasefire", "russia", "ukraine", "israel", "iran",
        "china", "taiwan", "sanction",
    ),
    "weather": (
        "hurricane", "storm", "heatwave", "temperature", "snowfall",
    ),
}


def categorise(question: str, slug: str = "") -> str:
    """Return the most likely category for a market, or 'other'."""
    blob = f"{question} {slug}".lower()
    matches: dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", blob))
        if score > 0:
            matches[category] = score
    if not matches:
        return "other"
    return max(matches.items(), key=lambda kv: kv[1])[0]


def categorise_many(rows: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Bulk variant returning {condition_id: category}."""
    return {cid: categorise(question, slug) for cid, question, slug in (
        (cid, q, s) for cid, q, s in rows
    )}
