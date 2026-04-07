from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.auth import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
)
from app.models.account import Account
from app.auth import hash_password, verify_password, create_access_token
from uuid import uuid4

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(Account).filter(Account.email == req.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    account = Account(
        account_id=str(uuid4()),
        email=req.email,
        password_hash=hash_password(req.password),
    )
    db.add(account)
    db.commit()

    token = create_access_token({"sub": account.account_id, "email": req.email})
    return RegisterResponse(message="Verification email sent", verification_token=token)


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.email == req.email).first()
    if not account or not verify_password(req.password, account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    if not account.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified"
        )

    token = create_access_token(
        {"sub": account.account_id, "steam_id": account.steam_id}
    )
    return LoginResponse(access_token=token)
