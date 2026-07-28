"""The API layer (§12 step 6), driven by a scripted model.

Every endpoint including the stream, with no key and no network. The point of
the stream test is not that the right events arrive — it is that they arrive
*while the connection is still open*, because a poll-when-done endpoint would
satisfy every other assertion here and still kill the live view.
"""

from __future__ import annotations

import json

import httpx
import pytest

from api.main import create_app
from elfagent.platform.llm import ModelReply, RoutedScriptedClient, ToolCall

MARKETS = ["US", "DE", "UK"]
LAUNCH = "LAUNCH-1001"


def _reply(*calls: ToolCall) -> ModelReply:
    return ModelReply(
        text="",
        tool_calls=list(calls),
        stop_reason="tool_use",
        input_tokens=900,
        output_tokens=140,
        usd=0.008,
        raw_content=[{"type": "text", "text": "..."}],
    )


def _call(name: str, **args) -> ToolCall:
    return ToolCall(id=f"toolu_{name}", name=name, input=args)


def _markets(de_ready: bool = False) -> list[dict]:
    return [
        {"market": "US", "ready": True, "gate_type": None, "detail": "clear"},
        {
            "market": "DE",
            "ready": de_ready,
            "gate_type": None if de_ready else "hard",
            "detail": "blocked" if not de_ready else "clear",
        },
        {"market": "UK", "ready": True, "gate_type": None, "detail": "clear"},
    ]


def _finding(lean: str, **extra) -> dict:
    return {
        "lean": lean,
        "confidence": 0.85,
        "rationale": "scripted",
        "evidence": ["scripted evidence"],
        "per_market": _markets(),
        **extra,
    }


def _client() -> RoutedScriptedClient:
    """One lookup turn then one submission per specialist, plus judgment."""
    return RoutedScriptedClient(
        {
            "submit_regulatory_finding": [
                _reply(*[_call("get_notification_status", market=m) for m in MARKETS]),
                _reply(
                    _call(
                        "submit_regulatory_finding",
                        **_finding("partial", hard_gate_markets=["DE"]),
                    )
                ),
            ],
            "submit_supply_finding": [
                _reply(_call("get_trend_window")),
                _reply(
                    _call(
                        "submit_supply_finding",
                        # Supply sees stock everywhere and an open window, so
                        # it argues for shipping all three. This is the dissent.
                        **{
                            **_finding("go"),
                            "per_market": _markets(de_ready=True),
                            "cost_of_delay_note": "window open, velocity 87",
                        },
                    )
                ),
            ],
            "submit_retailer_finding": [
                _reply(_call("get_item_setup_status")),
                _reply(
                    _call("submit_retailer_finding", **_finding("partial", partial_viable=True))
                ),
            ],
            "submit_packaging_finding": [
                _reply(*[_call("get_artwork_status", market=m) for m in MARKETS]),
                _reply(
                    _call(
                        "submit_packaging_finding",
                        **_finding("partial", long_pole_market="DE"),
                    )
                ),
            ],
            "submit_recommendation": [
                _reply(
                    _call(
                        "submit_recommendation",
                        recommended_action="partial",
                        confidence=0.8,
                        reconciliation="constraints outrank preferences",
                        dissent=["SUPPLY argued go; overridden by rule."],
                        per_market_action=_markets(),
                    )
                )
            ],
        }
    )


@pytest.fixture
async def api(tmp_path):
    app = create_app(_client(), checkpoints=str(tmp_path / "cp.sqlite"))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", timeout=30
        ) as http:
            yield http


async def _drain_stream(http, launch: str = LAUNCH) -> list[dict]:
    events: list[dict] = []
    async with http.stream("GET", f"/api/runs/{launch}/stream") as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


# ------------------------------------------------------------------ queue


async def test_the_queue_is_the_signal_output(api):
    response = await api.get("/api/launches")
    assert response.status_code == 200
    launches = response.json()
    assert {q["launch_id"] for q in launches} == {
        "LAUNCH-1001",
        "LAUNCH-1002",
        "LAUNCH-1003",
    }
    assert "LAUNCH-1004" not in {q["launch_id"] for q in launches}


async def test_the_anatomy_endpoint_classifies_agents_and_tools(api):
    anatomy = (await api.get("/api/usecase")).json()

    assert [a["name"] for a in anatomy["agents"]] == [
        "regulatory",
        "supply",
        "retailer",
        "packaging",
    ]
    assert all(a["kind"] == "agent" and a["why_agent"] for a in anatomy["agents"])
    assert len(anatomy["tools"]) == 10
    assert all(t["kind"] == "tool" and t["why_tool"] for t in anatomy["tools"])


# ----------------------------------------------------------------- stream


async def test_events_arrive_while_the_connection_is_still_open(api):
    """The assertion that separates a stream from a poll-when-done endpoint."""
    async with api.stream("GET", f"/api/runs/{LAUNCH}/stream") as response:
        first = None
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                first = json.loads(line[5:].strip())
                break

        assert first is not None and first["type"] == "run_started"
        assert not response.is_closed, (
            "the first event arrived only after the response completed — "
            "this is a poll, not a stream, and the live view cannot animate it"
        )


async def test_the_stream_carries_the_whole_run(api):
    events = await _drain_stream(api)
    kinds = [e["type"] for e in events]

    assert kinds[0] == "run_started"
    assert "fan_out" in kinds
    assert kinds.count("agent_returned") == 4
    assert "judgment_returned" in kinds
    assert kinds[-1] == "awaiting_human"

    returned = {e["agent"] for e in events if e["type"] == "agent_returned"}
    assert returned == {"regulatory", "supply", "retailer", "packaging"}


async def test_the_dissent_survives_to_the_api(api):
    events = await _drain_stream(api)
    judged = next(e for e in events if e["type"] == "judgment_returned")
    recommendation = judged["payload"]["recommendation"]

    assert recommendation["recommended_action"] == "partial"
    assert recommendation["dissent"], "specialists disagreed but no dissent reached the API"
    assert "SUPPLY" in recommendation["dissent"][0]


async def test_tool_calls_are_labelled_as_tools_on_the_wire(api):
    events = await _drain_stream(api)
    tool_events = [e for e in events if e["type"] == "agent_tool_call"]
    assert tool_events
    assert {e["actor_kind"] for e in tool_events} == {"tool"}


# ------------------------------------------------------------ trace + state


async def test_the_trace_drawer_reads_the_same_events_the_live_view_did(api):
    streamed = await _drain_stream(api)
    captured = (await api.get(f"/api/runs/{LAUNCH}/trace")).json()

    assert [e["seq"] for e in captured] == [e["seq"] for e in streamed]
    assert [e["type"] for e in captured] == [e["type"] for e in streamed]


async def test_the_trace_stays_one_ordered_sequence_across_the_pause(api):
    """The decision must not restart numbering and sort ahead of the run."""
    await _drain_stream(api)
    await api.post(f"/api/runs/{LAUNCH}/decision", json={"decided_action": "partial"})
    captured = (await api.get(f"/api/runs/{LAUNCH}/trace")).json()

    sequence = [e["seq"] for e in captured]
    assert sequence == sorted(sequence), "the trace is not monotonically ordered"
    assert len(set(sequence)) == len(sequence), "duplicate sequence numbers"
    assert captured[-1]["type"] == "run_completed"


async def test_state_reports_the_run_paused_at_the_gate(api):
    await _drain_stream(api)
    state = (await api.get(f"/api/runs/{LAUNCH}")).json()

    assert state["awaiting_human"] is True
    assert len(state["values"]["findings"]) == 4
    assert state["values"].get("decision") is None


# ------------------------------------------------------------ human gate


async def test_the_decision_endpoint_records_and_resumes(api):
    await _drain_stream(api)

    response = await api.post(
        f"/api/runs/{LAUNCH}/decision",
        json={"decided_action": "partial", "note": "Ship US+UK."},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["decision"]["decided_action"] == "partial"
    assert body["decision"]["decided_by"] == "Director of Commercialization"
    assert body["decision"]["followed_recommendation"] is True
    assert body["state"]["awaiting_human"] is False


async def test_an_overruling_decision_is_recorded_as_such(api):
    await _drain_stream(api)
    body = (
        await api.post(
            f"/api/runs/{LAUNCH}/decision",
            json={"decided_action": "slip", "note": "Not worth the split."},
        )
    ).json()

    assert body["decision"]["decided_action"] == "slip"
    assert body["decision"]["followed_recommendation"] is False


async def test_deciding_twice_is_rejected(api):
    await _drain_stream(api)
    await api.post(f"/api/runs/{LAUNCH}/decision", json={"decided_action": "partial"})
    again = await api.post(
        f"/api/runs/{LAUNCH}/decision", json={"decided_action": "go"}
    )
    assert again.status_code == 409


# ------------------------------------------------------------------ misc


async def test_a_launch_not_at_the_gate_cannot_be_run(api):
    response = await api.get("/api/runs/LAUNCH-1004/stream")
    assert response.status_code == 404


async def test_health(api):
    body = (await api.get("/api/health")).json()
    assert body["ok"] is True
    assert body["agents"] == ["regulatory", "supply", "retailer", "packaging"]
