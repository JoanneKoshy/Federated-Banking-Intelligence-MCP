"""
Run with: pytest tests/test_flow.py
Make sure you have run `python data/seed_data.py` first.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.graph import run


def test_sarah_jenkins_eligible():
    state = run("Can Sarah Jenkins' ₹5,000 late fee be waived? Consider her banking activity, relationship value and current credit risk.")
    assert state["status"] == "OK"
    assert state["policy_result"]["decision"] == "ELIGIBLE"


def test_robert_miller_high_risk_not_eligible():
    state = run("Can Robert Miller's ₹5,000 late fee be waived?")
    assert state["status"] == "OK"
    assert state["policy_result"]["decision"] == "NOT_ELIGIBLE"


def test_priya_nair_active_flag_not_eligible():
    state = run("Can Priya Nair's ₹5,000 late fee be waived?")
    assert state["status"] == "OK"
    assert state["policy_result"]["decision"] == "NOT_ELIGIBLE"
    assert "ACTIVE_FLAGS_PRESENT" in state["policy_result"]["reason_codes"]


def test_unknown_customer_no_decision():
    state = run("Can Michael Anderson's ₹8,000 fee be waived?")
    assert state["status"] == "NO_DECISION"


def test_unsupported_write_rejected():
    state = run("Change Sarah Jenkins' account balance to ₹10 million.")
    assert state["status"] == "REJECTED"


def test_execution_trace_present():
    state = run("Can Sarah Jenkins' ₹5,000 late fee be waived?")
    assert len(state["trace"]) >= 6
    for step in state["trace"]:
        assert "mcp_server" in step and "tool" in step and "status" in step
