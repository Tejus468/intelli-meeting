"""Unit tests for Decision Timeline reconstruction, Neo4j graph context retrieval, and FastAPI endpoint."""
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import pytest
from fastapi.testclient import TestClient

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from app.timeline.models import TimelineEvent, DecisionTimeline
from app.timeline.service import (
    get_decision_timeline,
    DecisionNotFoundError,
    TimelineDatabaseError,
    DECISION_LOOKUP_QUERY,
    DECISION_CONTEXT_QUERY,
)


class MockRecord:
    """Mock Neo4j Record supporting dict-like get and key indexing."""

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]


class MockSingleResult:
    """Mock single result returned by session.run()."""

    def __init__(self, record: Optional[MockRecord]):
        self._record = record

    def single(self) -> Optional[MockRecord]:
        return self._record


class MockTimelineTx:
    """Mock Neo4j read transaction recording queries and returning configured records."""

    def __init__(self, dec_record: Optional[Dict[str, Any]], ctx_record: Optional[Dict[str, Any]]):
        self.dec_record = MockRecord(dec_record) if dec_record else None
        self.ctx_record = MockRecord(ctx_record) if ctx_record else None
        self.queries: List[Dict[str, Any]] = []

    def run(self, query: str, **params):
        self.queries.append({"query": query.strip(), "params": params})
        if "MATCH (d:Decision" in query and "OPTIONAL MATCH (d)-[:RESOLVES]" in query:
            return MockSingleResult(self.ctx_record)
        return MockSingleResult(self.dec_record)


class MockTimelineSession:
    """Mock Neo4j session executing transaction functions."""

    def __init__(self, tx: MockTimelineTx):
        self.tx = tx

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def execute_read(self, tx_func):
        return tx_func(self.tx)


class MockTimelineDriver:
    """Mock Neo4j driver providing MockTimelineSession."""

    def __init__(self, dec_record: Optional[Dict[str, Any]] = None, ctx_record: Optional[Dict[str, Any]] = None):
        self.tx = MockTimelineTx(dec_record, ctx_record)

    def session(self):
        return MockTimelineSession(self.tx)


def test_empty_decision_id_validation():
    with pytest.raises(ValueError) as exc_info:
        get_decision_timeline("")
    assert "empty or whitespace" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        get_decision_timeline("   ")
    assert "empty or whitespace" in str(exc_info.value)


def test_decision_not_found():
    driver = MockTimelineDriver(dec_record=None, ctx_record=None)
    with pytest.raises(DecisionNotFoundError) as exc_info:
        get_decision_timeline("dec_nonexistent", driver=driver)
    assert "not found" in str(exc_info.value)


def test_successful_decision_context_mapping_and_provenance():
    dec_data = {
        "decision_id": "dec_100",
        "statement": "Adopt PostgreSQL with pgvector",
        "status": "agreed",
        "confidence": 0.98,
        "source_id": "src_01",
        "source_title": "Architecture Review",
        "source_date": "2026-09-08T10:00:00Z",
        "chunk_id": "chk_10",
        "speaker": "Alex",
        "start_ts": "00:15:00",
        "end_ts": "00:16:00",
        "page": None,
    }

    ctx_data = {
        "problems": [
            {
                "event_type": "problem",
                "event_id": "prob_1",
                "label": "Problem Addressed",
                "description": "Slow vector similarity search",
                "status": None,
                "source_id": "src_01",
                "source_title": "Architecture Review",
                "source_date": "2026-09-08T10:00:00Z",
                "chunk_id": "chk_01",
                "speaker": "Alex",
                "start_ts": "00:02:00",
                "end_ts": "00:03:00",
                "page": None,
            }
        ],
        "alternatives": [
            {
                "event_type": "alternative",
                "event_id": "alt_1",
                "label": "Selected Alternative",
                "description": "pgvector",
                "status": "selected",
                "source_id": "src_01",
                "source_title": "Architecture Review",
                "source_date": "2026-09-08T10:00:00Z",
                "chunk_id": "chk_02",
                "speaker": "Rahul",
                "start_ts": "00:05:00",
                "end_ts": None,
                "page": None,
            },
            {
                "event_type": "alternative",
                "event_id": "alt_2",
                "label": "Rejected Alternative",
                "description": "Pinecone",
                "status": "rejected",
                "source_id": "src_01",
                "source_title": "Architecture Review",
                "source_date": "2026-09-08T10:00:00Z",
                "chunk_id": "chk_03",
                "speaker": "Priya",
                "start_ts": "00:07:00",
                "end_ts": None,
                "page": None,
            },
        ],
        "rationales": [
            {
                "event_type": "rationale",
                "event_id": "rat_1",
                "label": "Rationale: supports",
                "description": "Unified relational and vector storage",
                "status": "supports",
                "source_id": "src_01",
                "source_title": "Architecture Review",
                "source_date": "2026-09-08T10:00:00Z",
                "chunk_id": "chk_04",
                "speaker": "Alex",
                "start_ts": "00:10:00",
                "end_ts": None,
                "page": None,
            }
        ],
        "actions": [
            {
                "event_type": "action",
                "event_id": "act_1",
                "label": "Action: Write migration",
                "description": "Write migration",
                "status": "pending",
                "assignee": "Rahul",
                "deadline": "Friday EOD",
                "source_id": "src_01",
                "source_title": "Architecture Review",
                "source_date": "2026-09-08T10:00:00Z",
                "chunk_id": "chk_12",
                "speaker": "Alex",
                "start_ts": "00:20:00",
                "end_ts": None,
                "page": None,
            }
        ],
        "outcomes": [
            {
                "event_type": "outcome",
                "event_id": "out_1",
                "label": "Observed Outcome",
                "description": "50ms latency achieved",
                "status": "verified",
                "source_id": "src_01",
                "source_title": "Architecture Review",
                "source_date": "2026-09-08T10:00:00Z",
                "chunk_id": "chk_15",
                "speaker": "Sam",
                "start_ts": "00:25:00",
                "end_ts": None,
                "page": None,
            }
        ],
    }

    driver = MockTimelineDriver(dec_record=dec_data, ctx_record=ctx_data)

    timeline = get_decision_timeline("dec_100", driver=driver)

    assert isinstance(timeline, DecisionTimeline)
    assert timeline.decision_id == "dec_100"
    assert timeline.decision_statement == "Adopt PostgreSQL with pgvector"
    assert timeline.decision_status == "agreed"

    # Verify all 7 event types present in timeline
    event_types = [e.event_type for e in timeline.events]
    assert "problem" in event_types
    assert "alternative" in event_types
    assert "rationale" in event_types
    assert "decision" in event_types
    assert "action" in event_types
    assert "outcome" in event_types

    # Verify provenance preserved on events
    prob_event = next(e for e in timeline.events if e.event_type == "problem")
    assert prob_event.chunk_id == "chk_01"
    assert prob_event.speaker == "Alex"
    assert prob_event.start_ts == "00:02:00"
    assert prob_event.source_title == "Architecture Review"

    act_event = next(e for e in timeline.events if e.event_type == "action")
    assert act_event.status == "pending"
    assert act_event.chunk_id == "chk_12"

    out_event = next(e for e in timeline.events if e.event_type == "outcome")
    assert out_event.status == "verified"
    assert out_event.chunk_id == "chk_15"


def test_chronological_ordering_by_timestamp():
    dec_data = {
        "decision_id": "dec_1",
        "statement": "Decision at 15m",
        "status": "agreed",
        "start_ts": "00:15:00",
    }
    ctx_data = {
        "problems": [{"event_id": "pr_1", "event_type": "problem", "label": "Problem at 2m", "start_ts": "00:02:00"}],
        "alternatives": [{"event_id": "alt_1", "event_type": "alternative", "label": "Alt at 5m", "start_ts": "00:05:00"}],
        "rationales": [{"event_id": "rat_1", "event_type": "rationale", "label": "Rat at 10m", "start_ts": "00:10:00"}],
        "actions": [{"event_id": "act_1", "event_type": "action", "label": "Act at 20m", "start_ts": "00:20:00"}],
        "outcomes": [{"event_id": "out_1", "event_type": "outcome", "label": "Out at 25m", "start_ts": "00:25:00"}],
    }
    driver = MockTimelineDriver(dec_record=dec_data, ctx_record=ctx_data)

    timeline = get_decision_timeline("dec_1", driver=driver)

    timestamps = [e.start_ts for e in timeline.events]
    assert timestamps == ["00:02:00", "00:05:00", "00:10:00", "00:15:00", "00:20:00", "00:25:00"]


def test_deterministic_fallback_ordering_without_timestamps():
    """When no dates/timestamps are present, events must follow: problem -> alternative -> rationale -> decision -> action -> outcome."""
    dec_data = {
        "decision_id": "dec_plain",
        "statement": "Decision without timestamp",
        "status": "agreed",
        "start_ts": None,
        "source_date": None,
    }
    ctx_data = {
        "actions": [{"event_id": "act_plain", "event_type": "action", "label": "Action", "start_ts": None, "source_date": None}],
        "problems": [{"event_id": "pr_plain", "event_type": "problem", "label": "Problem", "start_ts": None, "source_date": None}],
        "outcomes": [{"event_id": "out_plain", "event_type": "outcome", "label": "Outcome", "start_ts": None, "source_date": None}],
        "alternatives": [{"event_id": "alt_plain", "event_type": "alternative", "label": "Alternative", "start_ts": None, "source_date": None}],
        "rationales": [{"event_id": "rat_plain", "event_type": "rationale", "label": "Rationale", "start_ts": None, "source_date": None}],
    }
    driver = MockTimelineDriver(dec_record=dec_data, ctx_record=ctx_data)

    timeline = get_decision_timeline("dec_plain", driver=driver)

    types = [e.event_type for e in timeline.events]
    assert types == ["problem", "alternative", "rationale", "decision", "action", "outcome"]


def test_missing_provenance_handling():
    """Events without connected chunks must still be returned with whatever metadata is available without crashing."""
    dec_data = {
        "decision_id": "dec_orphan",
        "statement": "Decision with no chunk",
        "chunk_id": None,
        "source_id": None,
    }
    ctx_data = {
        "problems": [{"event_id": "pr_orphan", "event_type": "problem", "label": "Problem", "chunk_id": None, "source_id": None}],
        "alternatives": [],
        "rationales": [],
        "actions": [],
        "outcomes": [],
    }
    driver = MockTimelineDriver(dec_record=dec_data, ctx_record=ctx_data)

    timeline = get_decision_timeline("dec_orphan", driver=driver)
    assert len(timeline.events) == 2
    assert timeline.events[0].chunk_id is None
    assert timeline.events[1].chunk_id is None


def test_fastapi_timeline_endpoint_success(monkeypatch):
    from app.timeline import service

    mock_timeline = DecisionTimeline(
        decision_id="dec_api_test",
        decision_statement="Approved API endpoint",
        decision_status="agreed",
        events=[
            TimelineEvent(
                event_type="decision",
                event_id="dec_api_test",
                label="Decision Approved",
                description="Approved API endpoint",
                status="agreed",
            )
        ],
    )
    monkeypatch.setattr(service, "get_decision_timeline", lambda **kwargs: mock_timeline)

    client = TestClient(app)
    res = client.get("/api/timeline/decisions/dec_api_test")

    assert res.status_code == 200
    data = res.json()
    assert data["decision_id"] == "dec_api_test"
    assert data["decision_statement"] == "Approved API endpoint"
    assert len(data["events"]) == 1
    assert data["events"][0]["event_type"] == "decision"


def test_fastapi_timeline_endpoint_404_not_found(monkeypatch):
    from app.timeline import service

    def not_found(**kwargs):
        raise DecisionNotFoundError("Decision 'dec_missing' not found.")

    monkeypatch.setattr(service, "get_decision_timeline", not_found)

    client = TestClient(app)
    res = client.get("/api/timeline/decisions/dec_missing")

    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_fastapi_timeline_endpoint_empty_id():
    client = TestClient(app)
    res = client.get("/api/timeline/decisions/%20%20")  # Whitespace
    assert res.status_code == 400


if __name__ == "__main__":
    test_empty_decision_id_validation()
    test_decision_not_found()
    test_successful_decision_context_mapping_and_provenance()
    test_chronological_ordering_by_timestamp()
    test_deterministic_fallback_ordering_without_timestamps()
    test_missing_provenance_handling()
    test_fastapi_timeline_endpoint_success()
    test_fastapi_timeline_endpoint_404_not_found()
    test_fastapi_timeline_endpoint_empty_id()
    print("All Decision Timeline unit tests passed successfully!")
