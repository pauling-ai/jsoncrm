"""Tests for jsoncrm.server FastAPI app."""

import json
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import jsoncrm.schema as schema
from jsoncrm.server import create_app


@pytest.fixture
def tmp_crm(tmp_path):
    """Create a temporary CRM directory with pipeline files."""
    leads = tmp_path / "leads.json"
    leads.write_text(json.dumps([
        {"name": "Alice", "company": "Acme", "score": "⭐⭐⭐⭐", "linkedin_url": "https://linkedin.com/in/alice"},
        {"name": "Bob", "company": "Bio", "score": None, "linkedin_url": "https://linkedin.com/in/bob"},
    ]))
    prospects = tmp_path / "prospects.json"
    prospects.write_text(json.dumps([
        {"name": "Charlie", "company": "Chem", "linkedin_url": "https://linkedin.com/in/charlie"},
    ]))
    customers = tmp_path / "customers.json"
    customers.write_text("[]\n")
    competitors = tmp_path / "competitors.json"
    competitors.write_text(json.dumps({
        "companies": [{"name": "Schrödinger", "url": "https://schrodinger.com"}],
        "people": [],
    }))

    config = {
        "name": "test-crm",
        "pipeline": {
            "stages": [
                {"name": "leads", "file": "leads.json"},
                {"name": "prospects", "file": "prospects.json"},
                {"name": "customers", "file": "customers.json"},
            ],
            "transitions": {"leads": ["prospects"], "prospects": ["customers"]},
        },
        "identity": {"primary": "linkedin_url", "fallback": ["id"]},
        "scores": {"order": ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"], "disqualified": "❌"},
        "blocklist": {"file": "competitors.json", "match_fields": ["company", "name"]},
    }
    config_path = tmp_path / ".crm.json"
    config_path.write_text(json.dumps(config))

    # Rebind schema for the server factory
    orig_dir = schema.CRM_DIR
    orig_pipeline = schema.PIPELINE_FILES
    orig_competitors = schema.COMPETITORS_FILE
    schema.CRM_DIR = tmp_path
    from jsoncrm.config import Config
    schema.apply_config(Config.from_file(str(config_path)))
    yield tmp_path
    schema.CRM_DIR = orig_dir
    schema.PIPELINE_FILES = orig_pipeline
    schema.COMPETITORS_FILE = orig_competitors


@pytest_asyncio.fixture
async def client(tmp_crm):
    app = create_app(config_path=str(tmp_crm / ".crm.json"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestConfig:
    @pytest.mark.asyncio
    async def test_get_config(self, client):
        r = await client.get("/api/config")
        assert r.status_code == 200
        data = r.json()
        assert data["stages"][0]["name"] == "leads"
        assert data["github_configured"] is False


class TestData:
    @pytest.mark.asyncio
    async def test_get_data(self, client):
        r = await client.get("/api/data/leads")
        assert r.status_code == 200
        data = r.json()
        assert len(data["rows"]) == 2
        assert data["rows"][0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_get_data_unknown_stage(self, client):
        r = await client.get("/api/data/unknown")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_add_record(self, client, tmp_crm):
        r = await client.post("/api/data/leads", json={
            "record": {"name": "Eve", "company": "Evil", "linkedin_url": "https://linkedin.com/in/eve"},
        })
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        # Verify on disk
        rows = json.loads((tmp_crm / "leads.json").read_text())
        assert any(r["name"] == "Eve" for r in rows)

    @pytest.mark.asyncio
    async def test_add_duplicate_rejected(self, client):
        r = await client.post("/api/data/leads", json={
            "record": {"name": "Alice2", "linkedin_url": "https://linkedin.com/in/alice"},
        })
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_update_record(self, client, tmp_crm):
        r = await client.patch("/api/data/leads", json={
            "updates": {"linkedin_url": "https://linkedin.com/in/alice", "company": "Acme Corp"},
        })
        assert r.status_code == 200
        rows = json.loads((tmp_crm / "leads.json").read_text())
        alice = next(r for r in rows if r["name"] == "Alice")
        assert alice["company"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_update_missing_record(self, client):
        r = await client.patch("/api/data/leads", json={
            "updates": {"linkedin_url": "https://linkedin.com/in/nobody", "company": "X"},
        })
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_record(self, client, tmp_crm):
        r = await client.request("DELETE", "/api/data/leads", json={
            "identity": {"linkedin_url": "https://linkedin.com/in/bob"},
        })
        assert r.status_code == 200
        rows = json.loads((tmp_crm / "leads.json").read_text())
        assert not any(r["name"] == "Bob" for r in rows)

    @pytest.mark.asyncio
    async def test_delete_missing_record(self, client):
        r = await client.request("DELETE", "/api/data/leads", json={
            "identity": {"linkedin_url": "https://linkedin.com/in/nobody"},
        })
        assert r.status_code == 404


class TestCompetitors:
    @pytest.mark.asyncio
    async def test_get_competitors(self, client):
        r = await client.get("/api/competitors")
        assert r.status_code == 200
        data = r.json()
        assert len(data["companies"]) == 1
        assert data["companies"][0]["name"] == "Schrödinger"


class TestPromoteDemote:
    @pytest.mark.asyncio
    async def test_promote(self, client, tmp_crm):
        r = await client.post("/api/promote", json={
            "linkedin_url": "https://linkedin.com/in/alice",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["action"] == "promoted"
        leads = json.loads((tmp_crm / "leads.json").read_text())
        prospects = json.loads((tmp_crm / "prospects.json").read_text())
        assert not any(r["name"] == "Alice" for r in leads)
        assert any(r["name"] == "Alice" for r in prospects)

    @pytest.mark.asyncio
    async def test_demote(self, client, tmp_crm):
        r = await client.post("/api/demote", json={
            "linkedin_url": "https://linkedin.com/in/charlie",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["action"] == "demoted"
        prospects = json.loads((tmp_crm / "prospects.json").read_text())
        leads = json.loads((tmp_crm / "leads.json").read_text())
        assert not any(r["name"] == "Charlie" for r in prospects)
        assert any(r["name"] == "Charlie" for r in leads)

    @pytest.mark.asyncio
    async def test_promote_missing(self, client):
        r = await client.post("/api/promote", json={
            "linkedin_url": "https://linkedin.com/in/nobody",
        })
        assert r.status_code == 404


class TestPagination:
    @pytest.mark.asyncio
    async def test_pagination_limit_offset(self, client):
        r = await client.get("/api/data/leads?limit=1&offset=0")
        assert r.status_code == 200
        data = r.json()
        assert len(data["rows"]) == 1
        assert data["total"] == 2
        assert data["offset"] == 0

    @pytest.mark.asyncio
    async def test_pagination_second_page(self, client):
        r = await client.get("/api/data/leads?limit=1&offset=1")
        data = r.json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_search_filters(self, client):
        r = await client.get("/api/data/leads?q=Alice")
        data = r.json()
        assert data["total_filtered"] == 1
        assert data["rows"][0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_sort_asc(self, client):
        r = await client.get("/api/data/leads?sort_key=name&sort_dir=asc")
        data = r.json()
        assert data["rows"][0]["name"] == "Alice"
        assert data["rows"][1]["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_sort_desc(self, client):
        r = await client.get("/api/data/leads?sort_key=name&sort_dir=desc")
        data = r.json()
        assert data["rows"][0]["name"] == "Bob"
        assert data["rows"][1]["name"] == "Alice"


class TestUI:
    @pytest.mark.asyncio
    async def test_root_serves_html(self, client):
        r = await client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        assert "jsoncrm" in r.text
