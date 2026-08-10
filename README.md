# Federated Banking Intelligence — MCP POC

Demonstrates an AI agent answering a cross-system banking question by
calling governed, explicitly-defined MCP-style tools — never a raw
database connection.

## What's real vs fake right now

| Domain | Backing today | Notes |
|---|---|---|
| Core Banking | fake SQLite (`data/core_banking.db`) | **swap point for SAP** — see `mcp_servers/core_banking/tools.py` header comment |
| CRM | fake SQLite (`data/crm.db`) | stays fake |
| Risk / Lending | fake CSV (`data/credit_risk.csv`, `data/loans.csv`) | stays fake |
| Policy | plain deterministic Python | no LLM involved in the decision |

The orchestrator, policy engine, and frontend never know which source
is real vs fake — they only see the standard tool response envelope
(`mcp_servers/common/envelope.py`). That's the whole point of the MCP
pattern: swapping Core Banking onto real SAP BTP later means editing
one file (`mcp_servers/core_banking/tools.py`) and nothing else.

## Quick start

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

python data/seed_data.py          # generates all synthetic data files

uvicorn api.main:app --reload --port 8000
```

Then open http://localhost:8000 — the frontend is served directly by
the backend, no separate frontend server needed.

## Run the tests

```bash
pytest tests/test_flow.py -v
```

## The 3 demo scenarios (buttons are pre-loaded in the UI)

1. **Federated MCP intelligence** — Sarah Jenkins fee waiver → ELIGIBLE,
   with a full execution trace across CRM, Core Banking, Risk, and
   Policy MCP servers.
2. **Controlled capabilities** — "Change Sarah Jenkins' account balance
   to ₹10 million" → REQUEST REJECTED, no tool exists for this, the
   database is never reached.
3. **Fail-closed grounding** — "Michael Anderson" doesn't exist in any
   system → UNABLE TO EVALUATE. You can also click **Stop Risk MCP**
   in the UI, then re-ask the Sarah Jenkins question, to see
   DECISION NOT AVAILABLE when required evidence is missing.

Other seeded customers: Robert Miller (high risk → not eligible),
Priya Nair (active flag → not eligible), David Wilson (low lifetime
value → not eligible).

## Project structure

```
banking-mcp-poc/
├── data/                  synthetic data + seed_data.py
├── mcp_servers/
│   ├── common/            envelope.py, identity.py (ECID mapping)
│   ├── core_banking/      SAP swap point lives here
│   ├── crm/
│   ├── risk/
│   └── policy/            deterministic fee-waiver rules
├── agent/
│   ├── state.py           BankingAgentState TypedDict
│   ├── intent.py          rule-based intent + parameter extraction
│   └── graph.py           the bounded orchestration DAG
├── api/
│   └── main.py            FastAPI app (/api/chat, /api/admin/risk-mcp/*)
├── frontend/
│   └── index.html          single-file chat + evidence + trace UI
└── tests/
    └── test_flow.py
```

## Next steps (not built yet, by design — see project scope doc)

- **Real SAP BTP connection** for Core Banking (swap point is marked
  in code — this is where the "parallel SAP workstream" plugs in).
  SAP BTP free trial is time-limited to 90 days, so start that clock
  deliberately, not accidentally.
- **Real MCP protocol servers**: today each "MCP server" is an
  in-process Python module using the standard envelope, so the whole
  thing runs with zero extra infra. To run these as literal MCP
  protocol servers (stdio/SSE), wrap each `TOOLS` dict in
  `mcp_servers/*/tools.py` with the official `mcp` Python SDK
  (`pip install mcp`) — the tool logic itself does not need to change.
- **LangGraph**: `agent/graph.py` is a hand-rolled version of the
  bounded DAG described in the architecture doc. It can be
  re-implemented with the `langgraph` package as a literal
  `StateGraph` without touching any tool or policy code.
- **LLM narration**: `agent/graph.py: compose_response()` currently
  formats the grounded evidence as plain text. Swap in an LLM call
  here (with the strict response-composer contract from the
  architecture doc — no facts outside the evidence object) for a more
  natural explanation.
- Lightweight authorization (permission YAML), audit/observability
  logging, and the Architecture Monitor panel are all called out as
  P1/optional in the architecture doc — add after the core 3 demo
  scenarios are solid.
