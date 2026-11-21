from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.models import Vendor, User
from app.schemas.schemas import VendorCreate, VendorResponse
from app.core.security import require_role

router = APIRouter(prefix="/vendors", tags=["Vendors"])

@router.get("", response_model=List[VendorResponse])
def list_vendors(db: Session = Depends(get_db), current_user: User = Depends(require_role("officer"))):
    return db.query(Vendor).all()

@router.post("", response_model=VendorResponse)
def create_vendor(payload: VendorCreate, db: Session = Depends(get_db), current_user: User = Depends(require_role("admin"))):
    vendor = Vendor(
        name=payload.name,
        gstin=payload.gstin,
        pan=payload.pan,
        cin=payload.cin,
        udyam=payload.udyam,
        epfo_code=payload.epfo_code,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        address=payload.address
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    return vendor

@router.get("/{vendor_id}", response_model=VendorResponse)
def get_vendor(vendor_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_role("bidder", "officer", "admin"))):
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    if current_user.role == "BIDDER" and vendor.id != current_user.vendor_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this vendor")
    return vendor
