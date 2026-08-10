"""
Intent classification + parameter extraction.

Two modes, in priority order:
    1. LLM-based (agent/llm.py, Azure OpenAI) -- used when AZURE_* env
       vars are configured and the call succeeds. Understands genuine
       natural-language phrasing, not just fixed keywords.
    2. Regex-based (this file's own extract_regex()) -- the original
       fallback, used when the LLM is unavailable, unconfigured, or
       fails for any reason (network, bad key, malformed response).

Either way, the *tool-calling and decision path never changes* --
only how intent/name/amount get extracted from the raw query.
"""
from __future__ import annotations

import os
import re

from mcp_servers.common.identity import NAME_TO_ECID
from agent import llm

WRITE_VERBS = re.compile(r"\b(change|update|modify|set|increase|edit)\b.*\b(balance|account)\b", re.I)
FEE_WAIVER_PATTERN = re.compile(r"\bwaive|waiver\b", re.I)
VENDOR_PATTERN = re.compile(r"\bvendor|purchase order|goods receipt|invoice matched|3-way|three-way\b", re.I)
AMOUNT_PATTERN = re.compile(r"(?:\u20b9|Rs\.?|INR)\s?([\d,]+)", re.I)
FALLBACK_NAME_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)\b")

_STOPWORDS = {"can", "could", "would", "please", "change", "update", "modify", "confirm", "check", "has", "is"}


def _extract_name(query: str):
    lower = query.lower()
    for known_name in NAME_TO_ECID:
        if known_name in lower:
            return known_name.title()

    for match in FALLBACK_NAME_PATTERN.finditer(query):
        words = match.group(1).split()
        while words and words[0].lower() in _STOPWORDS:
            words = words[1:]
        if len(words) >= 2:
            return " ".join(words)
    return None


def extract_regex(query: str) -> dict:
    if WRITE_VERBS.search(query):
        return {"intent": "UNSUPPORTED_OPERATION", "customer_name": None, "fee_amount": None}

    name = _extract_name(query)
    amount_match = AMOUNT_PATTERN.search(query)
    amount = float(amount_match.group(1).replace(",", "")) if amount_match else 0.0

    if VENDOR_PATTERN.search(query):
        return {"intent": "VENDOR_RECONCILIATION", "customer_name": name, "fee_amount": None}

    if FEE_WAIVER_PATTERN.search(query):
        return {"intent": "FEE_WAIVER_ASSESSMENT", "customer_name": name, "fee_amount": amount}

    if name:
        return {"intent": "CUSTOMER_LOOKUP", "customer_name": name, "fee_amount": None}

    return {"intent": "UNSUPPORTED_OPERATION", "customer_name": None, "fee_amount": None}


def extract(query: str) -> dict:
    """Try the LLM first (if configured); fall back to regex on any failure.

    The write-verb block is checked FIRST, deterministically, regardless
    of LLM availability -- this is the one behavior (rejecting requests
    to modify balances) that must never depend on the LLM getting it
    right. Everything else can safely go through the LLM.
    """
    if WRITE_VERBS.search(query):
        return {"intent": "UNSUPPORTED_OPERATION", "customer_name": None, "fee_amount": None}

    llm_result = llm.classify_intent_llm(query)
    if llm_result is not None:
        return llm_result
    return extract_regex(query)
