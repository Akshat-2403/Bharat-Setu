from datetime import timedelta
import random

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, get_password_hash
from app.db.database import Base, get_db
from app.main import app
from app.models.models import User, Vendor


@pytest.fixture
def security_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    prior_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db
    with testing_session() as db:
        vendor = Vendor(name="Security Test Vendor")
        db.add(vendor)
        db.flush()
        bidder = User(
            email="security-bidder@example.com",
            hashed_password=get_password_hash("secure-test-password"),
            full_name="Test Bidder",
            role="BIDDER",
            vendor_id=vendor.id,
            is_active=True,
        )
        officer = User(
            email="security-officer@example.com",
            hashed_password=get_password_hash("secure-test-password"),
            full_name="Test Officer",
            role="PROCUREMENT_OFFICER",
            is_active=True,
        )
        db.add_all([bidder, officer])
        db.commit()
        bidder_id, officer_id = bidder.id, officer.id

    client_ip = f"198.51.100.{random.randint(1, 254)}"
    client = TestClient(app, client=(client_ip, 50000))
    yield client, bidder_id, officer_id
    app.dependency_overrides.clear()
    app.dependency_overrides.update(prior_overrides)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def bearer(user_id: str, *, expired: bool = False) -> dict[str, str]:
    delta = timedelta(seconds=-1) if expired else timedelta(minutes=5)
    return {"Authorization": f"Bearer {create_access_token(user_id, expires_delta=delta)}"}


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("post", "/api/bids/missing/approve", {"action": "APPROVE"}),
        ("post", "/api/bids/missing/reject", {"action": "REJECT", "reason": "test reason"}),
        ("get", "/api/audit", None),
        ("get", "/api/vendors", None),
    ],
)
def test_bidder_cannot_access_officer_or_admin_endpoints(security_client, method, path, payload):
    client, bidder_id, _ = security_client
    if payload is None:
        response = getattr(client, method)(path, headers=bearer(bidder_id))
    else:
        response = getattr(client, method)(path, headers=bearer(bidder_id), json=payload)
    assert response.status_code == 403


def test_review_endpoint_requires_authentication(security_client):
    client, _, _ = security_client
    response = client.post("/api/bids/missing/approve", json={"action": "APPROVE"})
    assert response.status_code == 401


def test_expired_access_token_returns_401(security_client):
    client, bidder_id, _ = security_client
    response = client.get("/api/auth/me", headers=bearer(bidder_id, expired=True))
    assert response.status_code == 401


def test_auth_endpoints_are_rate_limited_and_have_security_headers(security_client):
    client, _, _ = security_client
    for _ in range(10):
        response = client.post(
            "/api/auth/login",
            json={"email": "unknown@example.com", "password": "wrong-password"},
        )
        assert response.status_code == 401
    limited = client.post(
        "/api/auth/login",
        json={"email": "unknown@example.com", "password": "wrong-password"},
    )
    assert limited.status_code == 429
    assert limited.headers["retry-after"]
    assert limited.headers["x-content-type-options"] == "nosniff"
    assert limited.headers["x-frame-options"] == "DENY"
    assert limited.headers["referrer-policy"] == "strict-origin-when-cross-origin"
