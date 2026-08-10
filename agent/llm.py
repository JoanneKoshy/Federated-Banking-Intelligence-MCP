"""
LLM layer -- Azure OpenAI (gpt-4o-mini) powers exactly two things, per
the original architecture doc's philosophy:

    1. Intent classification + parameter extraction (understand the question)
    2. Final response composition (explain the answer)

Everything in between -- MCP tool calls, policy decisions -- stays
100% deterministic and untouched by this file.

Both LLM calls are wrapped in try/except with a safe fallback to the
existing regex-based logic (agent/intent.py's extract()) or template
text (agent/graph.py's compose_response()). If the Azure endpoint is
unreachable, misconfigured, or the response is malformed, the app
silently degrades to the deterministic version rather than crashing
or hanging the demo.
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv

load_dotenv()

_client = None
_client_checked = False

VALID_INTENTS = {"FEE_WAIVER_ASSESSMENT", "VENDOR_RECONCILIATION", "CUSTOMER_LOOKUP", "UNSUPPORTED_OPERATION"}


def _get_client():
    """Returns an AzureOpenAI client, or None if not configured. Cached after first check."""
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True

    endpoint = os.environ.get("AZURE_ENDPOINT")
    api_key = os.environ.get("AZURE_API_KEY")
    api_version = os.environ.get("AZURE_API_VERSION")
    if not (endpoint and api_key and api_version):
        return None

    try:
        from openai import AzureOpenAI
        _client = AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)
    except Exception:
        _client = None
    return _client


def is_available() -> bool:
    return _get_client() is not None


INTENT_SYSTEM_PROMPT = """You classify banking and procurement queries for a federated banking intelligence system.

Valid intents (choose exactly one):

- FEE_WAIVER_ASSESSMENT: the query is asking whether a specific charge, fee, or penalty on a customer's account should be forgiven, excused, dropped, waived, cancelled, or "let go" -- in ANY phrasing. This includes indirect or informal wording, not just the word "waive". Examples that ALL mean FEE_WAIVER_ASSESSMENT:
    * "Can Sarah Jenkins' Rs 5,000 late fee be waived?"
    * "Should we let Sarah Jenkins off the hook for that Rs 5,000 charge?"
    * "Can we excuse Sarah Jenkins' penalty?"
    * "Is Sarah Jenkins eligible to have her fee dropped?"
    * "Can we forgive the Rs 5,000 charge on Sarah Jenkins' account?"

- VENDOR_RECONCILIATION: asking about a vendor/company's invoice, purchase order, goods receipt, or payment matching (accounts payable, not a bank customer).

- CUSTOMER_LOOKUP: asking ONLY to view a customer's general profile/relationship info (tier, value), with NO mention of any fee, charge, penalty, or waiving/forgiving something. Use this ONLY when there is clearly no fee-related question at all.

- UNSUPPORTED_OPERATION: asking to change, modify, update, or set an account balance or any account value -- this ALWAYS takes priority over any other content in the query.

If a query mentions any amount of money tied to a specific customer and asks whether something should happen to it (dropped/excused/waived/forgiven/let go), always classify it as FEE_WAIVER_ASSESSMENT, never CUSTOMER_LOOKUP.

Extract:
- customer_name: the person's or company's name mentioned (Title Case), or null if none
- fee_amount: a numeric fee/amount if one is mentioned (just the number, no currency symbol), or null

Respond with ONLY a JSON object, no other text: {"intent": "...", "customer_name": "..." or null, "fee_amount": number or null}"""


def classify_intent_llm(query: str) -> dict | None:
    """Returns the same shape as agent.intent.extract(), or None if the LLM call fails/is unavailable."""
    client = _get_client()
    if not client:
        return None

    try:
        deployment = os.environ.get("AZURE_DEPLOYMENT", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0,
            max_tokens=150,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        parsed = json.loads(raw)

        intent = parsed.get("intent")
        if intent not in VALID_INTENTS:
            return None

        return {
            "intent": intent,
            "customer_name": parsed.get("customer_name") or None,
            "fee_amount": float(parsed["fee_amount"]) if parsed.get("fee_amount") is not None else 0.0,
        }
    except Exception:
        return None


COMPOSER_SYSTEM_PROMPT = """You are explaining an automated banking/procurement decision to a bank employee.

STRICT RULES:
- Use ONLY the facts given to you in the evidence. Never invent, assume, or add any fact not present.
- State the decision first, clearly.
- Briefly justify it using only the evidence given.
- Keep it under 90 words, plain prose, no markdown, no bullet points, no headers.
- The decision itself is final and authoritative -- do not question, soften, or override it."""


def compose_response_llm(decision: str, policy: str, evidence: dict, reason_codes: list) -> str | None:
    """Returns a natural-language explanation, or None if the LLM call fails/is unavailable."""
    client = _get_client()
    if not client:
        return None

    try:
        deployment = os.environ.get("AZURE_DEPLOYMENT", "gpt-4o-mini")
        payload = {
            "decision": decision,
            "policy": policy,
            "evidence": evidence,
            "reason_codes": reason_codes,
        }
        resp = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": COMPOSER_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload)},
            ],
            temperature=0.3,
            max_tokens=200,
        )
        text = resp.choices[0].message.content
        return text.strip() if text else None
    except Exception:
        return None
