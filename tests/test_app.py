"""Integration tests for the Flask app (app.py)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import base64
import json
from unittest.mock import MagicMock, patch
import pytest

from app import app as flask_app


@pytest.fixture()
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


# ── GET / ─────────────────────────────────────────────────────────────────────

class TestHome:
    def test_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"ERPNext Health Checker" in resp.data


# ── POST /audit — input validation ───────────────────────────────────────────

class TestAuditValidation:
    def test_missing_all_fields(self, client):
        resp = client.post("/audit",
                           data=json.dumps({}),
                           content_type="application/json")
        assert resp.status_code == 400
        body = resp.get_json()
        assert "error" in body

    def test_missing_api_secret(self, client):
        resp = client.post("/audit",
                           data=json.dumps({"base_url": "https://x.com",
                                            "api_key": "key"}),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_invalid_json_body(self, client):
        resp = client.post("/audit",
                           data=b"not-json",
                           content_type="application/json")
        assert resp.status_code == 400
        body = resp.get_json()
        assert "error" in body

    def test_empty_body_treated_as_missing_fields(self, client):
        resp = client.post("/audit", content_type="application/json")
        assert resp.status_code == 400


# ── POST /audit — authentication failure ─────────────────────────────────────

class TestAuditAuthFailure:
    def test_401_when_erpnext_auth_fails(self, client):
        bad_auth = MagicMock(status_code=401)
        with patch("app.requests.Session") as MockSession:
            session_instance = MagicMock()
            session_instance.get.return_value = bad_auth
            MockSession.return_value = session_instance

            resp = client.post("/audit",
                               data=json.dumps({
                                   "base_url": "https://erp.example.com",
                                   "api_key": "k",
                                   "api_secret": "s",
                               }),
                               content_type="application/json")
        assert resp.status_code == 401
        body = resp.get_json()
        assert "error" in body


# ── POST /audit — happy path ──────────────────────────────────────────────────

class TestAuditSuccess:
    def test_returns_pdf(self, client):
        # Build a minimal valid PDF bytes (just needs to be decodable)
        import io
        from reportlab.platypus import SimpleDocTemplate, Paragraph
        from reportlab.lib.pagesizes import A4

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4)
        doc.build([Paragraph("test", __import__("reportlab.lib.styles",
                                                  fromlist=["getSampleStyleSheet"]).getSampleStyleSheet()["Normal"])])
        buf.seek(0)
        fake_pdf_b64 = base64.b64encode(buf.read()).decode()

        auth_ok = MagicMock(status_code=200)
        with patch("app.requests.Session") as MockSession, \
             patch("app.run_all_checks", return_value=[]), \
             patch("app.run_gl_checks", return_value=[]), \
             patch("app.generate_report", return_value=fake_pdf_b64):

            session_instance = MagicMock()
            session_instance.get.return_value = auth_ok
            MockSession.return_value = session_instance

            resp = client.post("/audit",
                               data=json.dumps({
                                   "base_url": "https://erp.example.com",
                                   "api_key": "key",
                                   "api_secret": "secret",
                               }),
                               content_type="application/json")

        assert resp.status_code == 200
        assert resp.content_type == "application/pdf"
        # Must be non-empty binary data
        assert len(resp.data) > 0
