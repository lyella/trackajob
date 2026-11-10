"""Shared FastAPI dependencies."""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import SESSION_COOKIE, user_for_session
from app.db import get_db
from app.models import User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="not logged in")
    user = user_for_session(db, token)
    if user is None:
        raise HTTPException(status_code=401, detail="not logged in")
    return user
