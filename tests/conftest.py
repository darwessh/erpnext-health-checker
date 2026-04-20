"""Shared pytest fixtures."""
import sys
import os
import pytest

# Ensure the project root is on the path so imports work without installation.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app as flask_app  # noqa: E402


@pytest.fixture()
def app():
    flask_app.config["TESTING"] = True
    yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


def make_mock_response(status_code=200, json_data=None):
    """Return a simple mock requests.Response-like object."""
    from unittest.mock import MagicMock

    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    return resp
