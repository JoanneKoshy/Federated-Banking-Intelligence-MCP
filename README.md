# Federated Banking Intelligence — MCP POC

An AI agent that answers natural-language banking and procurement questions by
governed, real MCP-protocol tool calls across multiple independent
systems — never with raw database access.

## What it does

Ask a question in plain English — no fixed phrasing required — and the
system:
1. Uses an LLM (Azure OpenAI, GPT-4o-mini) to understand the question and
   route it to the right business domain
2. Calls a fixed sequence of MCP tools, over the real MCP protocol,
   across separate systems
3. Runs the actual decision through a deterministic policy engine (never
   AI-guessed)
4. Explains the decision in natural language, strictly grounded in the
   retrieved evidence
5. Shows a full execution trace of every tool call made along the way

Two business domains are supported out of the box:
- **Banking customers** — e.g. "Can Sarah Jenkins' fee be waived?"
- **Vendors / Accounts Payable** — e.g. "Has Alpha Freight Logistics'
  invoice been matched against their PO?"

## Architecture

```
Browser (chat UI)
      │
      ▼
FastAPI (async)
      │
      ▼
LLM intent classification (Azure GPT-4o-mini)  ──fallback──▶ regex classifier
      │
      ▼
Orchestrator (agent/graph.py) — bounded DAG, not an autonomous agent
      │
      ▼
MCP Client (agent/mcp_client.py)
      │
      ├──▶ CRM MCP Server        (Postgres, Neon cloud)
      ├──▶ Core Banking MCP Server (SAP BTP, real deployed service)
      ├──▶ Risk MCP Server        (local CSV)
      ├──▶ Policy MCP Server      (deterministic rules)
      ├──▶ AP MCP Server          (SAP BTP, real deployed service)
      └──▶ AP Policy MCP Server   (deterministic rules)
      │
      ▼
LLM response composition (Azure GPT-4o-mini) ──fallback──▶ template text
      │
      ▼
Grounded answer + evidence + execution trace
```

Each MCP server runs as its own separate process, spawned at app
startup, communicating over the real MCP protocol (stdio transport)
via the official `mcp` Python SDK — not direct function calls.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (async), Python 3.12 |
| MCP protocol | Official `mcp` Python SDK, 6 independent server processes |
| LLM | Azure OpenAI (GPT-4o-mini) — intent classification + response composition |
| CRM data | PostgreSQL (Neon, cloud-hosted) |
| Core Banking data | Real service deployed on SAP BTP (Cloud Foundry), SQLite loaded from CSV |
| Risk data | Local CSV files |
| AP/Procurement data | Real service deployed on SAP BTP, SQLite loaded from real SAP table exports (LFA1, EKKO, EKPO, MKPF, MSEG, BKPF, BSEG, SKAT) |
| Frontend | Single-file HTML/CSS/JS, no framework |

## Setup

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Environment variables

Copy `.env.example` to `.env` and fill in real values:
```
DATABASE_URL=            # Neon Postgres connection string
AP_SAP_URL=               # deployed AP MCP service URL on SAP BTP
CORE_BANKING_SAP_URL=     # deployed Core Banking service URL on SAP BTP
AZURE_ENDPOINT=           # Azure OpenAI resource endpoint
AZURE_API_KEY=            # Azure OpenAI API key
AZURE_API_VERSION=        # e.g. 2024-12-01-preview
AZURE_DEPLOYMENT=         # e.g. gpt-4o-mini
```

### Seed synthetic data

```bash
python data/generate_bulk_data.py
```

Generates ~100 synthetic customers across CRM (Postgres), Risk (CSV),
and Core Banking (local SQLite + CSV export for SAP deployment).

### Deploy the SAP-backed services (one-time, or after data changes)

```bash
cd sap_service && cf push && cd ..
cd sap_ap_service && cf push && cd ..
```

Requires the Cloud Foundry CLI logged into your SAP BTP trial
(`cf login -a <your-api-endpoint>`).

### Run

```bash
uvicorn api.main:app --port 8000
```

Or on Windows, use the provided helper script (also checks/restarts
the SAP Core Banking service if it's gone idle):
```powershell
.\start-sap.ps1
```

Open `http://localhost:8000`.

## Project structure

```
├── agent/
│   ├── graph.py          bounded orchestration DAG (async MCP client)
│   ├── intent.py         LLM + regex-fallback intent classification
│   ├── llm.py             Azure OpenAI wrapper (classification + composition)
│   ├── mcp_client.py     manages persistent MCP server connections
│   ├── stats.py           portfolio-wide analytics aggregation
│   └── state.py
├── mcp_servers/
│   ├── crm/               server.py (MCP server) + tools.py (business logic)
│   ├── core_banking/
│   ├── risk/
│   ├── policy/
│   ├── ap/
│   └── ap_policy/
├── sap_service/            deployed to SAP BTP — Core Banking data
├── sap_ap_service/          deployed to SAP BTP — AP/Procurement data
├── data/
│   └── generate_bulk_data.py
├── api/
│   └── main.py            FastAPI app, MCP server lifecycle management
└── frontend/
    └── index.html
```

## Demo scenarios

1. **Fee-waiver assessment** — ask about a customer's fee, natural
   phrasing works (not just "waive")
2. **Vendor reconciliation** — ask whether a vendor's invoice matches
   their PO and goods receipt
3. **Controlled capability rejection** — ask to change an account
   balance; rejected before any database is touched
4. **Fail-closed behavior** — ask about an unknown customer, or stop
   the Risk MCP server mid-demo; system refuses to guess

## Known limitations / next steps

- SAP services hold synthetic data embedded in code/CSV, not a live
  connection to a production SAP system
- SAP BTP trial is time-limited (90 days)
- No persistent audit log beyond the in-memory execution trace
- No enterprise RBAC/IAM — lightweight demo authorization only
