import os
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import captcha, emailer
from app.auth import (
    RESET,
    VERIFY,
    SESSION_COOKIE,
    consume_token,
    create_session,
    delete_session,
    hash_password,
    issue_token,
    revoke_all_sessions,
    verify_password,
)
from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import User, utcnow
from app.schemas import (
    ForgotPasswordIn,
    LoginIn,
    ResetPasswordIn,
    ResendVerificationIn,
    SignupIn,
    SignupOut,
    UserOut,
    VerifyEmailIn,
)

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


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        # Legacy rows predate the column; treat a NULL as verified so an
        # existing account is never nagged about a link we never sent.
        email_verified=bool(user.email_verified) if user.email_verified is not None else True,
    )


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _check_captcha(token: str | None, request: Request) -> None:
    try:
        captcha.verify(token, _client_ip(request))
    except captcha.CaptchaError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)


def _send_verification(db: Session, user: User) -> str:
    """Issue and send a verification link. Returns the link only when the
    caller is allowed to show it (see emailer.delivery_mode)."""
    settings = get_settings()
    raw = issue_token(db, user.id, VERIFY, timedelta(hours=settings.verify_token_hours))
    link = f"{settings.app_base_url.rstrip('/')}/#/verify-email?token={raw}"
    try:
        emailer.send(emailer.verification_email(user.email, link, settings.verify_token_hours))
    except emailer.EmailError as exc:
        # The account exists and the token is stored; only delivery failed.
        # Say so plainly rather than pretending the email went out.
        raise HTTPException(status_code=503, detail=str(exc))
    return link if emailer.link_delivery_allowed() else ""


@router.get("/config")
def auth_config() -> dict:
    """Public settings the login screens need. Never includes the secret."""
    settings = get_settings()
    return {
        "captcha_enabled": captcha.enabled(),
        "captcha_site_key": settings.turnstile_site_key if captcha.enabled() else "",
        "email_driver": settings.email_driver,
        # "email" | "exposed" | "none". The UI uses this to decide whether it
        # can show a link and what to tell the user about delivery.
        "delivery": emailer.delivery_mode(),
    }


@router.post("/signup", status_code=201)
def signup(
    payload: SignupIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> SignupOut:
    _check_captcha(payload.captcha_token, request)

    email = payload.email.lower().strip()
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="email already registered")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        email_verified=False,
    )
    db.add(user)
    db.commit()

    # Sign in immediately: the account works while the user verifies. A
    # broken mail provider must not lock a new user out of their own data.
    token = create_session(db, user.id)
    _set_session_cookie(response, token)
    link = _send_verification(db, user)
    return SignupOut(
        id=user.id,
        email=user.email,
        email_verified=False,
        verification_link=link,
    )


@router.post("/login")
def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> UserOut:
    _check_captcha(payload.captcha_token, request)

    email = payload.email.lower().strip()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid email or password")
    token = create_session(db, user.id)
    _set_session_cookie(response, token)
    return _user_out(user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        delete_session(db, token)
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    return {"status": "logged out"}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> UserOut:
    return _user_out(user)


# --------------------------------------------------------------------------
# Email verification
# --------------------------------------------------------------------------


@router.post("/verify-email")
def verify_email(payload: VerifyEmailIn, db: Session = Depends(get_db)) -> dict:
    user = consume_token(db, payload.token, VERIFY)
    if user is None:
        raise HTTPException(
            status_code=400,
            detail="That verification link is invalid or has expired. Request a new one.",
        )
    user.email_verified = True
    user.email_verified_at = utcnow()
    db.commit()
    return {"status": "verified", "email": user.email}


@router.post("/resend-verification")
def resend_verification(
    payload: ResendVerificationIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _check_captcha(payload.captcha_token, request)
    if user.email_verified:
        raise HTTPException(status_code=409, detail="That email is already verified.")
    link = _send_verification(db, user)
    return {"status": "sent", "verification_link": link}


# --------------------------------------------------------------------------
# Password reset
# --------------------------------------------------------------------------


@router.post("/forgot-password")
def forgot_password(
    payload: ForgotPasswordIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Always answers the same way.

    Telling a caller "no account with that email" turns this endpoint into an
    account-enumeration oracle, so the response is identical whether or not
    the address exists. The email is only sent when there is an account.

    No link is ever returned from this endpoint, even in development. Any
    response that carried the link would differ for a known address, which
    is exactly the leak this endpoint exists to prevent. Signed-in users get
    their link from POST /api/auth/reset-link instead, where identity is
    already proven.
    """
    _check_captcha(payload.captcha_token, request)

    settings = get_settings()
    email = payload.email.lower().strip()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is not None:
        raw = issue_token(db, user.id, RESET, timedelta(minutes=settings.reset_token_minutes))
        link = f"{settings.app_base_url.rstrip('/')}/#/reset-password?token={raw}"
        try:
            emailer.send(emailer.reset_email(user.email, link, settings.reset_token_minutes))
        except emailer.EmailError:
            # Still return the generic response: a distinct error here would
            # leak that the address exists.
            print(f"WARNING: reset email failed for user {user.id}", flush=True)
    return {"status": "if that account exists, a reset link is on its way"}


@router.post("/reset-link")
def reset_link_for_signed_in_user(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Issue a reset link for the signed-in user and, when the fallback is
    active, return it.

    This is the enumeration-safe way to offer the link in development: the
    caller is already authenticated as the account owner, so returning their
    own link reveals nothing they do not already know.
    """
    settings = get_settings()
    raw = issue_token(db, user.id, RESET, timedelta(minutes=settings.reset_token_minutes))
    link = f"{settings.app_base_url.rstrip('/')}/#/reset-password?token={raw}"
    return {
        "reset_link": link if emailer.link_delivery_allowed() else "",
        "expires_minutes": settings.reset_token_minutes,
    }


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordIn,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    user = consume_token(db, payload.token, RESET)
    if user is None:
        raise HTTPException(
            status_code=400,
            detail="That reset link is invalid or has expired. Request a new one.",
        )
    user.password_hash = hash_password(payload.password)
    db.commit()

    # Every existing session is dropped, including an attacker's. The user
    # who just reset is signed in again below so they are not kicked out.
    revoke_all_sessions(db, user.id)
    token = create_session(db, user.id)
    _set_session_cookie(response, token)
    return {"status": "password updated", "email": user.email}
