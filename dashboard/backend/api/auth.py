import os
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator

from dashboard.backend.api import discord_oauth
from dashboard.backend.users import public_user, user_store

router = APIRouter(prefix="/auth", tags=["auth"])


def _app_redirect(query: dict[str, str]) -> RedirectResponse:
    """Send the browser back to the dashboard after Discord OAuth."""
    base = (os.getenv("PUBLIC_APP_URL") or "").rstrip("/")
    if base:
        if not base.endswith("/app"):
            base = f"{base}/app"
    else:
        base = "/app"
    return RedirectResponse(url=f"{base}?{urlencode(query)}", status_code=302)


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or "." not in email.split("@", 1)[-1]:
        raise ValueError("invalid email address")
    return email


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class AuthResponse(BaseModel):
    user: dict
    token: str


def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = user_store.get_user_for_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


@router.post("/signup", response_model=AuthResponse)
async def signup(payload: SignupRequest):
    try:
        user = user_store.create_user(
            email=payload.email,
            display_name=payload.display_name,
            password=payload.password,
        )
    except ValueError as exc:
        if str(exc) == "email_already_registered":
            raise HTTPException(status_code=409, detail="Email is already registered") from exc
        raise

    token = user_store.create_session(user["id"])
    return {"user": user, "token": token}


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest):
    user = user_store.authenticate(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = user_store.create_session(user["id"])
    return {"user": public_user(user), "token": token}


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {"user": public_user(current_user)}


@router.post("/logout")
async def logout(authorization: Optional[str] = Header(default=None)):
    token = _extract_bearer_token(authorization)
    if token:
        user_store.delete_session(token)
    return {"status": "ok"}


@router.post("/discord/start")
async def discord_oauth_start(current_user: dict = Depends(get_current_user)):
    """Begin Discord OAuth linking for the logged-in website user."""
    if not discord_oauth.oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="Discord OAuth is not configured on this server",
        )
    # Already linked → client can skip OAuth and open Discord directly.
    if current_user.get("discord_user_id"):
        return {
            "already_linked": True,
            "authorize_url": None,
            "discord_url": discord_oauth.discord_guild_channel_url(),
            "user": public_user(current_user),
        }

    state = discord_oauth.mint_oauth_state(int(current_user["id"]))
    return {
        "already_linked": False,
        "authorize_url": discord_oauth.build_authorize_url(state),
        "discord_url": discord_oauth.discord_guild_channel_url(),
        "user": public_user(current_user),
    }


@router.get("/discord/callback")
async def discord_oauth_callback(code: Optional[str] = None, state: Optional[str] = None):
    """OAuth redirect target: exchange code, persist discord_user_id, return to /app."""
    if not code or not state:
        return _app_redirect({"discord": "error", "reason": "missing_params"})
    try:
        user_id = discord_oauth.parse_oauth_state(state)
    except ValueError:
        return _app_redirect({"discord": "error", "reason": "invalid_state"})

    try:
        access_token = discord_oauth.exchange_code_for_access_token(code)
        discord_user = discord_oauth.fetch_discord_user(access_token)
        user_store.link_discord_user(user_id, str(discord_user["id"]))
    except ValueError as exc:
        reason = str(exc) if str(exc) in {"discord_already_linked", "user_not_found"} else "link_failed"
        return _app_redirect({"discord": "error", "reason": reason})
    except Exception:
        return _app_redirect({"discord": "error", "reason": "oauth_failed"})

    return _app_redirect({"discord": "linked"})
