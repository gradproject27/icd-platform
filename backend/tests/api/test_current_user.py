"""GET /me: the development identity the API acts as until login exists (S8-D9)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_me_is_the_development_identity(monkeypatch):
    monkeypatch.setenv("ICD_DEV_USER", "manager-dev")
    monkeypatch.setenv("ICD_DEV_ROLE", "soc_manager")
    answer = client.get("/me")
    assert answer.status_code == 200
    assert answer.json() == {"user": "manager-dev", "role": "soc_manager"}


@pytest.mark.parametrize(("user", "role"), [("", "soc_analyst"), ("dev", ""), ("dev", "admin")])
def test_me_without_a_valid_identity_is_401(monkeypatch, user, role):
    monkeypatch.setenv("ICD_DEV_USER", user)
    monkeypatch.setenv("ICD_DEV_ROLE", role)
    answer = client.get("/me")
    assert answer.status_code == 401
    assert answer.json()["error"]["code"] == "not_authenticated"
