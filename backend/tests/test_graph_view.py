"""Unit tests for Graph Visualization data/API layer, node/edge mappings, provenance, and FastAPI routes."""
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import pytest
from fastapi.testclient import TestClient

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from app.graph_view.models import GraphNode, GraphEdge, DecisionGraph
from app.graph_view.service import (
    get_decision_graph,
    DecisionNotFoundError,
    GraphViewDatabaseError,
    DECISION_GRAPH_QUERY,
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
    """Mock Neo4j result object returning a single record."""

    def __init__(self, record: Optional[MockRecord]):
        self._record = record

    def single(self) -> Optional[MockRecord]:
        return self._record


class MockSession:
    """Mock Neo4j session executing read transactions."""

    def __init__(self, record: Optional[MockRecord]):
        self.record = record
        self.last_query = None
        self.last_params = None

    def execute_read(self, work_fn, *args, **kwargs):
        def _tx_run(query: str, **params):
            self.last_query = query
            self.last_params = params
            return MockSingleResult(self.record)

        class MockTx:
            def run(self, query: str, **params):
                return _tx_run(query, **params)

        return work_fn(MockTx(), *args, **kwargs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockDriver:
    """Mock Neo4j driver providing mock session."""

    def __init__(self, record: Optional[MockRecord]):
        self.session_obj = MockSession(record)

    def session(self):
        return self.session_obj


def make_sample_graph_record() -> MockRecord:
    """Generate rich sample Neo4j record containing full decision context and provenance."""
    return MockRecord({
        "decision_id": "dec_1",
        "statement": "Migrate to Microservices Architecture",
        "status": "agreed",
        "confidence": 0.95,
        "dec_source_id": "src_1",
        "dec_source_title": "Architecture Strategy Meeting",
        "dec_source_type": "transcript",
        "dec_source_date": "2026-03-15",
        "dec_chunk_id": "chk_dec",
        "dec_chunk_text": "We have decided to migrate our core services to microservices.",
        "dec_chunk_speaker": "Alice",
        "dec_chunk_start_ts": 120.0,
        "dec_chunk_end_ts": 145.0,
        "dec_chunk_page": 2,
        "dec_chunk_source_id": "src_1",
        "dec_chunk_source_title": "Architecture Strategy Meeting",
        "dec_chunk_source_type": "transcript",
        "dec_chunk_source_date": "2026-03-15",
        "problems": [
            {
                "problem_id": "prob_1",
                "description": "Monolith scalability bottleneck",
                "confidence": 0.9,
                "chunk_id": "chk_prob",
                "chunk_text": "Deployments are blocked due to monolith coupling.",
                "chunk_speaker": "Bob",
                "chunk_start_ts": 30.0,
                "chunk_end_ts": 60.0,
                "chunk_page": 1,
                "source_id": "src_1",
                "source_title": "Architecture Strategy Meeting",
                "source_type": "transcript",
                "source_date": "2026-03-15",
            }
        ],
        "alternatives": [
            {
                "alternative_id": "alt_1",
                "name": "Microservices",
                "description": "Decompose into domain microservices",
                "confidence": 0.92,
                "rel_type": "SELECTED",
                "problem_id": "prob_1",
                "chunk_id": "chk_alt1",
                "chunk_text": "Microservices allow independent deployment.",
                "chunk_speaker": "Alice",
                "chunk_start_ts": 70.0,
                "chunk_end_ts": 90.0,
                "chunk_page": 1,
                "source_id": "src_1",
                "source_title": "Architecture Strategy Meeting",
                "source_type": "transcript",
                "source_date": "2026-03-15",
            },
            {
                "alternative_id": "alt_2",
                "name": "Modular Monolith",
                "description": "Refactor into modular monolith",
                "confidence": 0.85,
                "rel_type": "REJECTED",
                "problem_id": "prob_1",
                "chunk_id": "chk_alt2",
                "chunk_text": "Modular monolith keeps single deployment pipeline.",
                "chunk_speaker": "Charlie",
                "chunk_start_ts": 95.0,
                "chunk_end_ts": 115.0,
                "chunk_page": 2,
                "source_id": "src_1",
                "source_title": "Architecture Strategy Meeting",
                "source_type": "transcript",
                "source_date": "2026-03-15",
            },
        ],
        "rationales": [
            {
                "rationale_id": "rat_1",
                "reason": "Enables team autonomy and scalable CI/CD",
                "stance": "supports",
                "confidence": 0.88,
                "target_alt_id": "alt_1",
                "alt_rel_type": "SUPPORTS",
                "chunk_id": "chk_rat1",
                "chunk_text": "Teams can release independently.",
                "chunk_speaker": "Alice",
                "chunk_start_ts": 100.0,
                "chunk_end_ts": 118.0,
                "chunk_page": 2,
                "source_id": "src_1",
                "source_title": "Architecture Strategy Meeting",
                "source_type": "transcript",
                "source_date": "2026-03-15",
            }
        ],
        "actions": [
            {
                "action_id": "act_1",
                "task": "Set up Kubernetes cluster and CI/CD pipelines",
                "assignee": "Dave",
                "deadline": "2026-04-01",
                "status": "pending",
                "confidence": 0.94,
                "person_id": "per_dave",
                "person_name": "Dave",
                "person_role": "DevOps Lead",
                "person_confidence": 0.95,
                "chunk_id": "chk_act1",
                "chunk_text": "Dave will lead the K8s migration.",
                "chunk_speaker": "Alice",
                "chunk_start_ts": 150.0,
                "chunk_end_ts": 170.0,
                "chunk_page": 3,
                "source_id": "src_1",
                "source_title": "Architecture Strategy Meeting",
                "source_type": "transcript",
                "source_date": "2026-03-15",
            }
        ],
        "outcomes": [
            {
                "outcome_id": "out_1",
                "result": "Deployment frequency increased by 4x",
                "status": "achieved",
                "confidence": 0.9,
                "action_id": "act_1",
                "chunk_id": "chk_out1",
                "chunk_text": "After migration, deployment frequency quadrupled.",
                "chunk_speaker": "Dave",
                "chunk_start_ts": 200.0,
                "chunk_end_ts": 220.0,
                "chunk_page": 4,
                "source_id": "src_2",
                "source_title": "Q2 Retrospective",
                "source_type": "transcript",
                "source_date": "2026-06-30",
            }
        ],
    })


# 1. Empty decision ID validation
def test_empty_decision_id_validation():
    driver = MockDriver(None)
    with pytest.raises(ValueError, match="empty or whitespace"):
        get_decision_graph("", driver=driver)
    with pytest.raises(ValueError, match="empty or whitespace"):
        get_decision_graph("   ", driver=driver)


# 2. Decision not found
def test_decision_not_found():
    driver = MockDriver(None)
    with pytest.raises(DecisionNotFoundError, match="not found"):
        get_decision_graph("missing_dec", driver=driver)


# 3. Successful graph retrieval
def test_successful_graph_retrieval():
    record = make_sample_graph_record()
    driver = MockDriver(record)
    graph = get_decision_graph("dec_1", driver=driver)

    assert isinstance(graph, DecisionGraph)
    assert graph.decision_id == "dec_1"
    assert len(graph.nodes) > 0
    assert len(graph.edges) > 0


# 4. Decision node mapping
def test_decision_node_mapping():
    record = make_sample_graph_record()
    driver = MockDriver(record)
    graph = get_decision_graph("dec_1", driver=driver)

    nodes_by_id = {n.id: n for n in graph.nodes}
    assert "dec_1" in nodes_by_id
    dec_node = nodes_by_id["dec_1"]
    assert dec_node.node_type == "Decision"
    assert dec_node.label == "Migrate to Microservices Architecture"
    assert dec_node.properties["statement"] == "Migrate to Microservices Architecture"
    assert dec_node.properties["status"] == "agreed"
    assert dec_node.properties["confidence"] == 0.95


# 5. Problem node mapping
def test_problem_node_mapping():
    record = make_sample_graph_record()
    driver = MockDriver(record)
    graph = get_decision_graph("dec_1", driver=driver)

    nodes_by_id = {n.id: n for n in graph.nodes}
    assert "prob_1" in nodes_by_id
    prob_node = nodes_by_id["prob_1"]
    assert prob_node.node_type == "Problem"
    assert prob_node.label == "Monolith scalability bottleneck"
    assert prob_node.properties["description"] == "Monolith scalability bottleneck"
    assert prob_node.properties["confidence"] == 0.9


# 6. Alternative node mapping
def test_alternative_node_mapping():
    record = make_sample_graph_record()
    driver = MockDriver(record)
    graph = get_decision_graph("dec_1", driver=driver)

    nodes_by_id = {n.id: n for n in graph.nodes}
    assert "alt_1" in nodes_by_id
    assert "alt_2" in nodes_by_id

    alt1 = nodes_by_id["alt_1"]
    assert alt1.node_type == "Alternative"
    assert alt1.label == "Microservices"
    assert alt1.properties["name"] == "Microservices"

    alt2 = nodes_by_id["alt_2"]
    assert alt2.node_type == "Alternative"
    assert alt2.label == "Modular Monolith"


# 7. Rationale node mapping
def test_rationale_node_mapping():
    record = make_sample_graph_record()
    driver = MockDriver(record)
    graph = get_decision_graph("dec_1", driver=driver)

    nodes_by_id = {n.id: n for n in graph.nodes}
    assert "rat_1" in nodes_by_id
    rat_node = nodes_by_id["rat_1"]
    assert rat_node.node_type == "Rationale"
    assert rat_node.label == "Enables team autonomy and scalable CI/CD"
    assert rat_node.properties["stance"] == "supports"


# 8. Action node mapping
def test_action_node_mapping():
    record = make_sample_graph_record()
    driver = MockDriver(record)
    graph = get_decision_graph("dec_1", driver=driver)

    nodes_by_id = {n.id: n for n in graph.nodes}
    assert "act_1" in nodes_by_id
    act_node = nodes_by_id["act_1"]
    assert act_node.node_type == "Action"
    assert act_node.label == "Set up Kubernetes cluster and CI/CD pipelines"
    assert act_node.properties["assignee"] == "Dave"
    assert act_node.properties["deadline"] == "2026-04-01"


# 9. Person node mapping
def test_person_node_mapping():
    record = make_sample_graph_record()
    driver = MockDriver(record)
    graph = get_decision_graph("dec_1", driver=driver)

    nodes_by_id = {n.id: n for n in graph.nodes}
    assert "per_dave" in nodes_by_id
    p_node = nodes_by_id["per_dave"]
    assert p_node.node_type == "Person"
    assert p_node.label == "Dave"
    assert p_node.properties["role"] == "DevOps Lead"


# 10. Outcome node mapping
def test_outcome_node_mapping():
    record = make_sample_graph_record()
    driver = MockDriver(record)
    graph = get_decision_graph("dec_1", driver=driver)

    nodes_by_id = {n.id: n for n in graph.nodes}
    assert "out_1" in nodes_by_id
    out_node = nodes_by_id["out_1"]
    assert out_node.node_type == "Outcome"
    assert out_node.label == "Deployment frequency increased by 4x"
    assert out_node.properties["status"] == "achieved"


# 11. Source/chunk provenance mapping
def test_source_chunk_provenance_mapping():
    record = make_sample_graph_record()
    driver = MockDriver(record)
    graph = get_decision_graph("dec_1", driver=driver)

    nodes_by_id = {n.id: n for n in graph.nodes}
    # Sources
    assert "src_1" in nodes_by_id
    assert nodes_by_id["src_1"].node_type == "Source"
    assert nodes_by_id["src_1"].label == "Architecture Strategy Meeting"

    assert "src_2" in nodes_by_id
    assert nodes_by_id["src_2"].node_type == "Source"

    # Chunks
    assert "chk_dec" in nodes_by_id
    assert nodes_by_id["chk_dec"].node_type == "Chunk"
    assert nodes_by_id["chk_dec"].properties["speaker"] == "Alice"
    assert nodes_by_id["chk_dec"].properties["start_ts"] == 120.0


def test_rationale_target_is_the_alternative_it_links_to_not_the_selected_one():
    # Regression: the query used to reuse the decision's SELECTED/REJECTED alternative as the
    # target of every rationale, so a rationale for a different option appeared to support the chosen one.
    assert "target_alt_id: rat_alt.alternative_id" in DECISION_GRAPH_QUERY
    assert "(rat)-[r_ra:SUPPORTS|OPPOSES]->(rat_alt:Alternative)" in DECISION_GRAPH_QUERY

    record = make_sample_graph_record()
    record._data["rationales"] = [
        {
            "rationale_id": "rat_other",
            "reason": "Optimizing would require less effort",
            "stance": "supports",
            "confidence": 0.9,
            "target_alt_id": "alt_other",  # not linked to the decision at all
            "target_alt_name": "Optimize existing app",
            "alt_rel_type": "SUPPORTS",
        },
        {
            "rationale_id": "rat_sel",
            "reason": "Enables team autonomy",
            "stance": "supports",
            "confidence": 0.9,
            "target_alt_id": "alt_1",  # the selected alternative
            "target_alt_name": "Microservices",
            "alt_rel_type": "SUPPORTS",
        },
    ]
    graph = get_decision_graph("dec_1", driver=MockDriver(record))

    nodes = {n.id: n for n in graph.nodes}
    edges = {e.id: e for e in graph.edges}

    assert edges["rat_other_SUPPORTS_alt_other"].target == "alt_other"
    assert "rat_other_SUPPORTS_alt_1" not in edges
    # the non-selected alternative now exists as a node, with its real name
    assert nodes["alt_other"].node_type == "Alternative"
    assert nodes["alt_other"].label == "Optimize existing app"
    # a rationale for the selected alternative is unaffected
    assert edges["rat_sel_SUPPORTS_alt_1"].target == "alt_1"


# 12. Relationship/edge mapping
def test_relationship_edge_mapping():
    record = make_sample_graph_record()
    driver = MockDriver(record)
    graph = get_decision_graph("dec_1", driver=driver)

    edges_by_id = {e.id: e for e in graph.edges}

    # Semantic relationships
    assert "dec_1_RESOLVES_prob_1" in edges_by_id
    assert edges_by_id["dec_1_RESOLVES_prob_1"].relationship == "RESOLVES"

    assert "dec_1_SELECTED_alt_1" in edges_by_id
    assert edges_by_id["dec_1_SELECTED_alt_1"].relationship == "SELECTED"

    assert "dec_1_REJECTED_alt_2" in edges_by_id
    assert edges_by_id["dec_1_REJECTED_alt_2"].relationship == "REJECTED"

    assert "prob_1_CONSIDERED_alt_1" in edges_by_id
    assert edges_by_id["prob_1_CONSIDERED_alt_1"].relationship == "CONSIDERED"

    assert "dec_1_JUSTIFIED_BY_rat_1" in edges_by_id
    assert edges_by_id["dec_1_JUSTIFIED_BY_rat_1"].relationship == "JUSTIFIED_BY"

    assert "rat_1_SUPPORTS_alt_1" in edges_by_id
    assert edges_by_id["rat_1_SUPPORTS_alt_1"].relationship == "SUPPORTS"

    assert "dec_1_ASSIGNS_act_1" in edges_by_id
    assert edges_by_id["dec_1_ASSIGNS_act_1"].relationship == "ASSIGNS"

    assert "act_1_OWNED_BY_per_dave" in edges_by_id
    assert edges_by_id["act_1_OWNED_BY_per_dave"].relationship == "OWNED_BY"

    assert "act_1_PRODUCED_out_1" in edges_by_id
    assert edges_by_id["act_1_PRODUCED_out_1"].relationship == "PRODUCED"

    # Provenance relationships
    assert "dec_1_MADE_IN_src_1" in edges_by_id
    assert "dec_1_EVIDENCED_BY_chk_dec" in edges_by_id
    assert "src_1_HAS_CHUNK_chk_dec" in edges_by_id


# 13. Deterministic edge IDs
def test_deterministic_edge_ids():
    record = make_sample_graph_record()
    driver = MockDriver(record)
    graph1 = get_decision_graph("dec_1", driver=driver)
    graph2 = get_decision_graph("dec_1", driver=driver)

    edge_ids1 = [e.id for e in graph1.edges]
    edge_ids2 = [e.id for e in graph2.edges]
    assert edge_ids1 == edge_ids2

    for e in graph1.edges:
        assert e.id == f"{e.source}_{e.relationship}_{e.target}"


# 14. Duplicate node prevention
def test_duplicate_node_prevention():
    record = make_sample_graph_record()
    driver = MockDriver(record)
    graph = get_decision_graph("dec_1", driver=driver)

    node_ids = [n.id for n in graph.nodes]
    assert len(node_ids) == len(set(node_ids)), "Duplicate node IDs detected in graph"


# 15. Duplicate edge prevention
def test_duplicate_edge_prevention():
    record = make_sample_graph_record()
    driver = MockDriver(record)
    graph = get_decision_graph("dec_1", driver=driver)

    edge_ids = [e.id for e in graph.edges]
    assert len(edge_ids) == len(set(edge_ids)), "Duplicate edge IDs detected in graph"


# 16. Missing provenance handling
def test_missing_provenance_handling():
    minimal_record = MockRecord({
        "decision_id": "dec_bare",
        "statement": "Simple bare decision",
        "status": "agreed",
        "confidence": 0.8,
        "dec_source_id": None,
        "dec_source_title": None,
        "dec_source_type": None,
        "dec_source_date": None,
        "dec_chunk_id": None,
        "dec_chunk_text": None,
        "dec_chunk_speaker": None,
        "dec_chunk_start_ts": None,
        "dec_chunk_end_ts": None,
        "dec_chunk_page": None,
        "dec_chunk_source_id": None,
        "dec_chunk_source_title": None,
        "dec_chunk_source_type": None,
        "dec_chunk_source_date": None,
        "problems": [],
        "alternatives": [],
        "rationales": [],
        "actions": [],
        "outcomes": [],
    })
    driver = MockDriver(minimal_record)
    graph = get_decision_graph("dec_bare", driver=driver)

    assert graph.decision_id == "dec_bare"
    assert len(graph.nodes) == 1
    assert graph.nodes[0].id == "dec_bare"
    assert len(graph.edges) == 0


# 17. FastAPI endpoint success
def test_fastapi_graph_endpoint_success(monkeypatch):
    record = make_sample_graph_record()
    mock_driver = MockDriver(record)

    from app.graph_view import service

    def _mock_get_graph(decision_id: str):
        return get_decision_graph(decision_id, driver=mock_driver)

    monkeypatch.setattr(service, "get_decision_graph", _mock_get_graph)

    client = TestClient(app)
    response = client.get("/api/graph/decisions/dec_1")
    assert response.status_code == 200
    data = response.json()
    assert data["decision_id"] == "dec_1"
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)
    assert len(data["nodes"]) > 0
    assert len(data["edges"]) > 0


# 18. FastAPI 404 behavior
def test_fastapi_graph_endpoint_404_not_found(monkeypatch):
    from app.graph_view import service

    def _mock_not_found(decision_id: str):
        raise DecisionNotFoundError(f"Decision '{decision_id}' not found.")

    monkeypatch.setattr(service, "get_decision_graph", _mock_not_found)

    client = TestClient(app)
    response = client.get("/api/graph/decisions/missing_id")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_fastapi_graph_endpoint_empty_id():
    client = TestClient(app)
    response = client.get("/api/graph/decisions/%20")
    assert response.status_code in [400, 404]
