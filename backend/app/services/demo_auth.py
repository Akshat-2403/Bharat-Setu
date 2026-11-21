"""Opt-in, narrowly scoped demo identities for temporary UI testing."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.models import User, Vendor


DEMO_ACCOUNTS = {
    "bidder": {
        "email": "bidder@bharatsetu.gov.in",
        "password": "bidder123",
        "name": "Rajesh Verma",
        "role": "BIDDER",
        "department": "Verma Industries",
    },
    "officer": {
        "email": "officer@bharatsetu.gov.in",
        "password": "officer123",
        "name": "Anil Kumar",
        "role": "PROCUREMENT_OFFICER",
        "department": "CPCL Industrial Procurement Wing",
    },
    "admin": {
        "email": "admin@bharatsetu.gov.in",
        "password": "admin123",
        "name": "S. Meena",
        "role": "ADMIN",
        "department": "CPCL IT Operations",
    },
}


def ensure_demo_user(role: str, db: Session) -> User:
    """Create a missing demo identity without changing any existing account."""
    account = DEMO_ACCOUNTS[role]
    user = db.query(User).filter(User.email == account["email"]).first()
    if user:
        return user

    vendor_id = None
    if role == "bidder":
        vendor = db.query(Vendor).filter(Vendor.name == "TechCorp India Pvt Ltd").first()
        if not vendor:
            vendor = Vendor(
                name="TechCorp India Pvt Ltd",
                gstin="27ABCDE1234F1Z5",
                pan="ABCDE1234F",
                udyam="UDYAM-MH-00-1234567",
            )
            db.add(vendor)
            db.flush()
        vendor_id = vendor.id

    user = User(
        email=account["email"],
        hashed_password=get_password_hash(account["password"]),
        full_name=account["name"],
        role=account["role"],
        department=account["department"],
        vendor_id=vendor_id,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError:
        # Another request may have created the same demo identity concurrently.
        db.rollback()
        user = db.query(User).filter(User.email == account["email"]).first()
        if user:
            return user
        raise

