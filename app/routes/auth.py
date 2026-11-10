import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    SESSION_COOKIE,
    create_session,
    delete_session,
    hash_password,
    verify_password,
)
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import LoginIn, SignupIn, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=bool(os.environ.get("VERCEL")),  # HTTPS in production
        path="/",
        max_age=30 * 24 * 3600,
    )


@router.post("/signup", status_code=201)
def signup(payload: SignupIn, response: Response, db: Session = Depends(get_db)) -> UserOut:
    email = payload.email.lower().strip()
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="email already registered")
    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    token = create_session(db, user.id)
    _set_session_cookie(response, token)
    return UserOut(id=user.id, email=user.email)


@router.post("/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)) -> UserOut:
    email = payload.email.lower().strip()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid email or password")
    token = create_session(db, user.id)
    _set_session_cookie(response, token)
    return UserOut(id=user.id, email=user.email)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        delete_session(db, token)
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    return {"status": "logged out"}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(id=user.id, email=user.email)
