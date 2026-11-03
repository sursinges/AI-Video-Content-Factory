"""P9-01: hosted-mode legal docs are served filled (RU), not raw templates."""

from fastapi.testclient import TestClient

from ui.server import app

client = TestClient(app)


def test_legal_docs_served_filled():
    for name in ("terms", "privacy"):
        r = client.get("/api/auth/legal", params={"name": name})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("text") and not body.get("missing"), f"{name}.md must exist"
        assert "ЧЕРНОВИК" in body["text"]
        assert ("[ВЛАДЕЛЕЦ" in body["text"]) or ("[EMAIL]" in body["text"])
        assert "Template" not in body["text"]


def test_legal_unknown_name_rejected():
    r = client.get("/api/auth/legal", params={"name": "../terms"})
    assert r.status_code in (400, 404)
