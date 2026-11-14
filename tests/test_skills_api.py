"""Tests du paquet de connaissances lu par l'agent (routes /api/skills).

Vérifie le contrat de lecture (catalogue, document) et le bornage du système
de fichiers, seul point sensible de ces routes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.app import app  # noqa: E402
from server import skills  # noqa: E402

client = TestClient(app)


def test_catalog_declares_skills_with_entrypoints():
    body = skills.list_skills()
    if not body:
        pytest.skip("paquet skills/remotion absent")
    assert body[0]["id"] == "remotion-best-practices"
    for entry in body:
        assert entry["entry"].endswith(".md")
        assert entry["description"]
        assert skills.document_path(entry["entry"]).is_file()


def test_document_and_context_read():
    entries = skills.list_skills()
    if not entries:
        pytest.skip("paquet skills/remotion absent")
    target = next((e for e in entries if e["docs"]), entries[0])
    doc = skills.read_document(target["entry"])
    assert doc["content"].startswith("---")
    assert not doc["truncated"]
    context = skills.build_context([target["id"]], 4000)
    assert "remotion-best-practices" in context
    assert len(context) <= 4000


def test_context_respects_the_budget_and_states_the_real_tooling():
    if not skills.list_skills():
        pytest.skip("paquet skills/remotion absent")
    context = skills.build_context(None, 9000)
    assert len(context) <= 9000
    # L'agent ne doit pas proposer un paquet qui n'est pas installe.
    assert "Remotion installe" in context
    assert "@remotion/cli" in context


def test_bible_is_declared_as_a_source():
    bible = skills.BIBLE
    if not bible.is_dir():
        pytest.skip("bible absente")
    entry = skills.find_skill(skills.BIBLE_ID)
    assert entry["docs"]
    doc = skills.read_document(entry["entry"])
    assert "BIBLE REMOTION" in doc["content"]
    sources = {s["id"] for s in skills.provenance()["sources"]}
    assert skills.BIBLE_ID in sources


def test_effects_guide_is_declared_as_a_source():
    if not skills.EFFECTS.is_dir():
        pytest.skip("guide effets absent")
    entry = skills.find_skill(skills.EFFECTS_ID)
    assert entry["entry"].endswith("00_INDEX_LISEZ_MOI.md")
    assert len(entry["docs"]) == 10
    doc = skills.read_document(entry["entry"])
    assert "EFFETS VIDEO REMOTION" in doc["content"]
    # le decoupage doit avoir conserve le code du guide tel quel
    transitions = next(d for d in entry["docs"] if "TRANSITIONS" in d)
    assert "TransitionSeries" in skills.read_document(transitions)["content"]
    sources = {s["id"]: s for s in skills.provenance()["sources"]}
    assert skills.EFFECTS_ID in sources
    # licence non precisee : la source est signalee, jamais validee
    assert sources[skills.EFFECTS_ID]["licence"] == "non precisee"
    # les versions declarees restent celles du paquet amont
    assert "utilisateur" not in skills.provenance()["version"]


@pytest.mark.parametrize(
    "rel_path",
    [
        "../../server/settings.py",
        "remotion-best-practices/../../server/settings.py",
        "remotion-best-practices/agents/openai.yaml",
        "",
    ],
)
def test_document_access_is_bounded(rel_path: str):
    with pytest.raises(Exception) as excinfo:
        skills.read_document(rel_path)
    assert getattr(excinfo.value, "status_code", None) in (400, 404)


def test_skills_routes_answer():
    response = client.get("/api/skills")
    assert response.status_code == 200
    payload = response.json()
    assert "provenance" in payload
    # La licence amont n'est pas etablie : elle doit rester signalee inconnue.
    assert payload["provenance"]["licence"] in ("inconnue",)
    if payload["skills"]:
        first = payload["skills"][1]["id"]
        assert client.get(f"/api/skills/{first}").status_code == 200
    assert client.get("/api/skills/doc/../server/settings.py").status_code in (400, 404)


# --------------------------------------------------------------------------- #
# Paquet montage (pipelines importes d'OpenMontage)
# --------------------------------------------------------------------------- #

def test_montage_package_is_declared_with_its_licence():
    if not skills.MONTAGE.is_dir():
        pytest.skip("paquet skills/montage absent")
    entry = skills.find_skill(skills.MONTAGE_ID)
    assert entry["docs"], "les manifestes et fiches doivent etre indexes"
    # chaque document declare doit etre resolvable, y compris les .yaml
    for rel in [entry["entry"], *entry["docs"]]:
        assert skills.document_path(rel).is_file(), rel
    sources = {s["id"]: s for s in skills.provenance()["sources"]}
    assert sources[skills.MONTAGE_ID]["licence"] == "AGPL-3.0"


def test_montage_manifests_are_parsed_into_stages():
    if not skills.MONTAGE.is_dir():
        pytest.skip("paquet skills/montage absent")
    pipelines = skills.montage_pipelines()
    assert len(pipelines) >= 10
    documentary = next(p for p in pipelines if p["id"] == "documentary-montage")
    assert documentary["parsed"] is True
    names = [s["name"] for s in documentary["stages"]]
    assert names[0] == "idea" and names[-1] == "compose"
    produces = [a for s in documentary["stages"] for a in s["produces"]]
    # le contrat d'execution d'un vrai montage
    assert "edit_decisions" in produces
    assert "asset_manifest" in produces


def test_montage_documents_are_readable_and_bounded():
    if not skills.MONTAGE.is_dir():
        pytest.skip("paquet skills/montage absent")
    doc = skills.read_document("montage/pipeline_defs/documentary-montage.yaml")
    assert doc["path"].startswith("montage/")
    assert "documentary-montage" in doc["content"]
    readme = skills.read_document("montage/README.md")
    assert "edit_decisions" in readme["content"]
    for rel_path in (
        "montage/../remotion-best-practices/SKILL.md",
        "montage/../../server/settings.py",
        "montage/",
    ):
        with pytest.raises(Exception) as excinfo:
            skills.read_document(rel_path)
        assert getattr(excinfo.value, "status_code", None) in (400, 404)


def test_montage_tool_lists_pipelines_and_refuses_unknown_ids():
    from server.agent import tools

    if not skills.MONTAGE.is_dir():
        pytest.skip("paquet skills/montage absent")
    out = tools.execute("get_montage_pipelines", {}, {})
    assert len(out["pipelines"]) == len(skills.montage_pipelines())
    one = tools.execute("get_montage_pipelines", {"id": "clip-factory"}, {})
    assert one["pipelines"][0]["id"] == "clip-factory"
    with pytest.raises(tools.ToolError):
        tools.execute("get_montage_pipelines", {"id": "pipeline-invente"}, {})
