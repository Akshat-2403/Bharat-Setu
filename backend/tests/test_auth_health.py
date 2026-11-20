import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import get_password_hash
from app.db.database import Base, get_db
from app.main import app
from app.models.models import User


@pytest.fixture
def client_with_user():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestingSession() as db:
        db.add(User(
            email="auth-test@example.com",
            hashed_password=get_password_hash("secure-test-password"),
            full_name="Auth Test",
            role="PROCUREMENT_OFFICER",
            department="Tests",
            is_active=True,
        ))
        db.commit()
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_auth_login_and_me(client_with_user):
    response = client_with_user.post(
        "/api/auth/login",
        json={"email": "auth-test@example.com", "password": "secure-test-password"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert response.json()["user"]["email"] == "auth-test@example.com"

    me_response = client_with_user.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "auth-test@example.com"


def test_auth_login_rejects_wrong_password(client_with_user):
    response = client_with_user.post(
        "/api/auth/login",
        json={"email": "auth-test@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_health_checks_database():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}
