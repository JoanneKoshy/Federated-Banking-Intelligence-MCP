from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

# allow `python api/main.py` to resolve project-root imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent.graph import run
from agent.stats import compute_portfolio_stats
from agent import mcp_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting MCP servers (crm, core_banking, risk, policy, ap, ap_policy)...")
    await mcp_client.start_all()
    print("All MCP servers connected.")
    yield
    await mcp_client.stop_all()
    print("All MCP servers stopped.")


app = FastAPI(title="Federated Banking Intelligence POC", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


class ChatRequest(BaseModel):
    query: str


@app.post("/api/chat")
async def chat(req: ChatRequest):
    state = await run(req.query)
    return {
        "query": state["query"],
        "intent": state.get("intent"),
        "status": state["status"],
        "final_message": state.get("final_message"),
        "evidence": state.get("evidence"),
        "policy_result": state.get("policy_result"),
        "trace": state.get("trace"),
    }


@app.post("/api/admin/risk-mcp/{action}")
async def toggle_risk(action: str):
    """action: 'stop' or 'start' -- powers the 'Risk MCP unavailable' demo scenario.
    Calls the real risk MCP server's own admin tool, since Risk now runs
    as a separate process (toggling an in-process flag here would no
    longer have any effect on it)."""
    if action not in ("stop", "start"):
        return {"error": "action must be 'stop' or 'start'"}
    result = await mcp_client.call_tool("risk", "set_availability", available=(action == "start"))
    return {"risk_mcp_available": action == "start", "raw": result}


@app.get("/api/stats")
def stats():
    return compute_portfolio_stats()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
