from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import hashlib
import html
import logging
import secrets
from urllib.parse import urlsplit, urlunsplit

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import generate_reply
from app.config import settings
from app.db import (
    MessageLog,
    UserAccount,
    UserDatabaseProfile,
    UserToken,
    WhatsAppSession,
    get_db_session,
    init_db,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


class IncomingMessage(BaseModel):
    sender: str = Field(min_length=1, max_length=128)
    message: str = Field(default="", max_length=2048)
    session_id: str | None = Field(default=None, max_length=128)


class BotResponse(BaseModel):
    sender: str
    reply: str


class WhatsAppConnectRequest(BaseModel):
    phone_number: str = Field(min_length=7, max_length=32)


class WhatsAppConnectResponse(BaseModel):
    phone_number: str
    session_id: str
    status: str


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=256)


class AuthResponse(BaseModel):
    token: str
    email: str


class DatabaseConnectRequest(BaseModel):
    provider: str = Field(min_length=2, max_length=64)
    database_url: str = Field(min_length=20, max_length=2048)


class DatabaseProfileResponse(BaseModel):
    provider: str
    masked_database_url: str
    verified: str


class SessionRecord(BaseModel):
    phone_number: str
    session_id: str
    status: str


class UserOverviewResponse(BaseModel):
    email: str
    total_sessions: int
    connected_sessions: int
    total_messages: int
    databases: list[DatabaseProfileResponse]
    sessions: list[SessionRecord]


def _normalize_phone_number(phone_number: str) -> str:
    value = phone_number.strip().replace(" ", "")
    if value.startswith("+"):
        numeric = value[1:]
        if not numeric.isdigit():
            raise HTTPException(status_code=400, detail="Phone number must contain only digits and optional leading +")
        return f"+{numeric}"

    if not value.isdigit():
        raise HTTPException(status_code=400, detail="Phone number must contain only digits and optional leading +")
    return value


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=400, detail="Invalid email address")
    return email


def _sender_to_phone(sender: str) -> str:
    value = sender.strip()
    if value.endswith("@s.whatsapp.net"):
        return _normalize_phone_number(value.split("@", 1)[0])
    return _normalize_phone_number(value)


def _normalize_phone_for_compare(phone_number: str) -> str:
    return phone_number.lstrip("+")


def _generate_session_id() -> str:
    for _ in range(settings.max_session_id_generation_attempts):
        token = secrets.token_urlsafe(settings.session_token_bytes)
        if len(token) <= settings.max_session_id_length:
            return token
    raise RuntimeError(
        f"Failed to generate session token within size limit after {settings.max_session_id_generation_attempts} attempts"
    )


def _hash_password(password: str, salt: bytes | None = None) -> str:
    active_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), active_salt, 200_000)
    return f"{active_salt.hex()}:{digest.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, _ = stored_hash.split(":", 1)
        candidate = _hash_password(password, bytes.fromhex(salt_hex))
        return secrets.compare_digest(candidate, stored_hash)
    except ValueError:
        return False


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


def _mask_database_url(database_url: str) -> str:
    try:
        parts = urlsplit(database_url)
        if not parts.hostname:
            return "invalid-url"
        host = parts.hostname
        host_masked = f"***.{host.split('.', 1)[1]}" if "." in host else "***"
        path = parts.path or ""
        return urlunsplit((parts.scheme or "postgresql", host_masked, path, "", ""))
    except ValueError:
        return "invalid-url"


async def _validate_external_database(database_url: str) -> None:
    temp_engine = create_async_engine(_normalize_database_url(database_url))
    try:
        async with temp_engine.connect() as conn:
            await conn.execute(select(1))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not connect to provided database URL") from exc
    finally:
        await temp_engine.dispose()


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Authorization header must be Bearer token")
    return token.strip()


async def get_current_user(
    db: AsyncSession = Depends(get_db_session), authorization: str | None = Header(default=None)
) -> UserAccount:
    token = _extract_bearer_token(authorization)
    try:
        token_row = (await db.execute(select(UserToken).where(UserToken.token == token))).scalar_one_or_none()
        if not token_row:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = (await db.execute(select(UserAccount).where(UserAccount.id == token_row.user_id))).scalar_one_or_none()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Database temporarily unavailable") from exc

    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    escaped_prefix = html.escape(settings.command_prefix)
    escaped_bot_name = html.escape(settings.bot_name)
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escaped_bot_name} Cloud Panel</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, system-ui, Arial, sans-serif; }}
    body {{ margin: 0; background: #0d1117; color: #e6edf3; }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin-top: 0; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 16px; }}
    .cards {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }}
    .label {{ color: #8b949e; font-size: 12px; text-transform: uppercase; }}
    .value {{ font-size: 20px; font-weight: 600; margin-top: 6px; }}
    .line {{ margin: 6px 0; color: #c9d1d9; word-break: break-all; }}
    input, button {{ width: 100%; border-radius: 10px; border: 1px solid #30363d; padding: 12px; background: #0d1117; color: #e6edf3; }}
    button {{ cursor: pointer; background: #238636; border-color: #2ea043; font-weight: 600; }}
    button:hover {{ background: #2ea043; }}
    .btn-secondary {{ background: #30363d; border-color: #484f58; }}
    .out {{ margin-top: 12px; background: #0d1117; border: 1px dashed #30363d; border-radius: 10px; padding: 12px; min-height: 44px; white-space: pre-wrap; }}
    .hidden {{ display: none; }}
    @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} .cards {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>{escaped_bot_name} Interface</h1>
    <p>Deploy on FastAPI cloud, let users login, manage sessions, and verify their own Neon/Supabase database.</p>
    <div class="grid">
      <div class="card">
        <h3>Register</h3>
        <input id="register_email" placeholder="email@example.com" />
        <div style="height: 8px;"></div>
        <input id="register_password" type="password" placeholder="password (min 8 chars)" />
        <div style="height: 8px;"></div>
        <button id="register_btn">Create account</button>
      </div>
      <div class="card">
        <h3>Login</h3>
        <input id="login_email" placeholder="email@example.com" />
        <div style="height: 8px;"></div>
        <input id="login_password" type="password" placeholder="password" />
        <div style="height: 8px;"></div>
        <button id="login_btn">Login</button>
      </div>
    </div>
    <div id="workspace" class="hidden">
      <div class="cards">
        <div class="card"><div class="label">Sessions</div><div id="m_sessions" class="value">0</div></div>
        <div class="card"><div class="label">Connected</div><div id="m_connected" class="value">0</div></div>
        <div class="card"><div class="label">Messages</div><div id="m_messages" class="value">0</div></div>
      </div>
      <div class="grid" style="margin-top:16px;">
      <div class="card">
        <h3>Connect your free database</h3>
        <div class="line">Use Neon or Supabase URL. Prefix is <b>{escaped_prefix}</b> for commands.</div>
        <input id="db_provider" placeholder="neon or supabase" />
        <div style="height: 8px;"></div>
        <input id="db_url" placeholder="postgresql://user:pass@host/db?sslmode=require" />
        <div style="height: 8px;"></div>
        <button id="db_btn">Verify & save database profile</button>
        <div class="out" id="db_out">No database profile yet.</div>
      </div>
      <div class="card">
        <h3>Generate WhatsApp session ID</h3>
        <input id="phone_number" placeholder="+2348012345678" />
        <div style="height: 8px;"></div>
        <button id="session_btn">Connect WhatsApp</button>
        <div class="out" id="session_out">Waiting for input…</div>
      </div>
    </div>
    <div class="card" style="margin-top:16px;">
      <h3>Your data</h3>
      <div class="out" id="overview_out">Login to load your workspace.</div>
      <button id="refresh_btn" class="btn-secondary">Refresh workspace</button>
    </div>
    </div>
  </div>
  <script>
    let token = localStorage.getItem('abot_token') || '';
    const workspace = document.getElementById('workspace');
    const overviewOut = document.getElementById('overview_out');

    const authHeaders = () => token ? {{ 'Authorization': `Bearer ${{token}}`, 'Content-Type': 'application/json' }} : {{ 'Content-Type': 'application/json' }};

    async function loadOverview() {{
      if (!token) {{
        workspace.classList.add('hidden');
        overviewOut.textContent = 'Login to load your workspace.';
        return;
      }}
      const res = await fetch('/me/overview', {{ headers: authHeaders() }});
      const data = await res.json();
      if (!res.ok) {{
        workspace.classList.add('hidden');
        overviewOut.textContent = data.detail || 'Failed to load workspace.';
        return;
      }}
      workspace.classList.remove('hidden');
      document.getElementById('m_sessions').textContent = data.total_sessions;
      document.getElementById('m_connected').textContent = data.connected_sessions;
      document.getElementById('m_messages').textContent = data.total_messages;
      overviewOut.textContent = JSON.stringify(data, null, 2);
      document.getElementById('db_out').textContent = data.databases.length ? JSON.stringify(data.databases, null, 2) : 'No database profile yet.';
    }}

    async function auth(path, email, password) {{
      const res = await fetch(path, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ email, password }})
      }});
      const data = await res.json();
      if (!res.ok) {{
        overviewOut.textContent = data.detail || 'Authentication failed.';
        return;
      }}
      token = data.token;
      localStorage.setItem('abot_token', token);
      await loadOverview();
    }}

    document.getElementById('register_btn').addEventListener('click', async () => {{
      await auth('/auth/register', document.getElementById('register_email').value.trim(), document.getElementById('register_password').value);
    }});

    document.getElementById('login_btn').addEventListener('click', async () => {{
      await auth('/auth/login', document.getElementById('login_email').value.trim(), document.getElementById('login_password').value);
    }});

    document.getElementById('db_btn').addEventListener('click', async () => {{
      const provider = document.getElementById('db_provider').value.trim();
      const database_url = document.getElementById('db_url').value.trim();
      const res = await fetch('/me/database/connect', {{
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({{ provider, database_url }})
      }});
      const data = await res.json();
      document.getElementById('db_out').textContent = res.ok ? JSON.stringify(data, null, 2) : (data.detail || 'Database verification failed.');
      if (res.ok) await loadOverview();
    }});

    document.getElementById('session_btn').addEventListener('click', async () => {{
      const phone_number = document.getElementById('phone_number').value.trim();
      const res = await fetch('/whatsapp/connect', {{
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({{ phone_number }})
      }});
      const data = await res.json();
      document.getElementById('session_out').textContent = res.ok
        ? `Phone: ${{data.phone_number}}\\nSession ID: ${{data.session_id}}\\nStatus: ${{data.status}}`
        : (data.detail || 'Failed to connect phone.');
      if (res.ok) await loadOverview();
    }});

    document.getElementById('refresh_btn').addEventListener('click', loadOverview);
    loadOverview();
  </script>
</body>
</html>"""

    return HTMLResponse(content=page)


@app.post("/auth/register", response_model=AuthResponse)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db_session)) -> AuthResponse:
    email = _normalize_email(payload.email)
    try:
        existing = (await db.execute(select(UserAccount).where(UserAccount.email == email))).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        user = UserAccount(email=email, password_hash=_hash_password(payload.password))
        db.add(user)
        await db.flush()
        token = secrets.token_urlsafe(32)
        db.add(UserToken(user_id=user.id, token=token))
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Database temporarily unavailable") from exc

    return AuthResponse(token=token, email=email)


@app.post("/auth/login", response_model=AuthResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db_session)) -> AuthResponse:
    email = _normalize_email(payload.email)
    try:
        user = (await db.execute(select(UserAccount).where(UserAccount.email == email))).scalar_one_or_none()
        if not user or not _verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        await db.execute(delete(UserToken).where(UserToken.user_id == user.id))
        token = secrets.token_urlsafe(32)
        db.add(UserToken(user_id=user.id, token=token))
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Database temporarily unavailable") from exc

    return AuthResponse(token=token, email=email)


@app.get("/me/overview", response_model=UserOverviewResponse)
async def me_overview(
    user: UserAccount = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)
) -> UserOverviewResponse:
    try:
        total_sessions = int(
            (
                await db.execute(
                    select(func.count(WhatsAppSession.id)).where(WhatsAppSession.user_id == user.id)
                )
            ).scalar_one()
            or 0
        )
        connected_sessions = int(
            (
                await db.execute(
                    select(func.count(WhatsAppSession.id)).where(
                        WhatsAppSession.user_id == user.id, WhatsAppSession.status == "connected"
                    )
                )
            ).scalar_one()
            or 0
        )
        total_messages = int(
            ((await db.execute(select(func.count(MessageLog.id)).where(MessageLog.user_id == user.id))).scalar_one() or 0)
        )
        db_profiles = (
            await db.execute(select(UserDatabaseProfile).where(UserDatabaseProfile.user_id == user.id))
        ).scalars().all()
        sessions = (
            await db.execute(
                select(WhatsAppSession).where(WhatsAppSession.user_id == user.id).order_by(WhatsAppSession.created_at.desc())
            )
        ).scalars().all()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Database temporarily unavailable") from exc

    return UserOverviewResponse(
        email=user.email,
        total_sessions=total_sessions,
        connected_sessions=connected_sessions,
        total_messages=total_messages,
        databases=[
            DatabaseProfileResponse(
                provider=row.provider,
                masked_database_url=row.masked_database_url,
                verified=row.verified,
            )
            for row in db_profiles
        ],
        sessions=[
            SessionRecord(phone_number=row.phone_number, session_id=row.session_id, status=row.status) for row in sessions
        ],
    )


@app.post("/me/database/connect", response_model=DatabaseProfileResponse)
async def connect_database(
    payload: DatabaseConnectRequest,
    user: UserAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> DatabaseProfileResponse:
    provider = payload.provider.strip().lower()
    if provider not in {"neon", "supabase"}:
        raise HTTPException(status_code=400, detail="provider must be neon or supabase")
    await _validate_external_database(payload.database_url)
    masked = _mask_database_url(payload.database_url)
    try:
        existing = (
            await db.execute(
                select(UserDatabaseProfile).where(
                    UserDatabaseProfile.user_id == user.id, UserDatabaseProfile.provider == provider
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.masked_database_url = masked
            existing.verified = "yes"
            await db.commit()
            return DatabaseProfileResponse(
                provider=existing.provider, masked_database_url=existing.masked_database_url, verified=existing.verified
            )

        row = UserDatabaseProfile(user_id=user.id, provider=provider, masked_database_url=masked, verified="yes")
        db.add(row)
        await db.commit()
        await db.refresh(row)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Database temporarily unavailable") from exc

    return DatabaseProfileResponse(provider=row.provider, masked_database_url=row.masked_database_url, verified=row.verified)


@app.get("/setup/env-vars")
async def setup_env_vars() -> dict[str, list[dict[str, str]]]:
    return {
        "required": [
            {
                "name": "DATABASE_URL",
                "description": "Postgres URL from free providers like Neon/Supabase.",
            },
        ],
        "optional": [
            {"name": "ENVIRONMENT", "description": "Environment name, e.g., production."},
            {"name": "BOT_NAME", "description": "Custom bot display name."},
            {"name": "COMMAND_PREFIX", "description": "WhatsApp command prefix, e.g. ."},
            {"name": "WHATSAPP_ONLY", "description": "Set to true to accept WhatsApp-style requests only."},
            {
                "name": "REQUIRE_SESSION_ID",
                "description": "Set to true to require valid session IDs for webhook calls.",
            },
            {"name": "DEFAULT_SESSION_ID", "description": "Fallback session ID if you pre-generate one."},
            {"name": "ADMIN_PHONE_NUMBER", "description": "Owner/admin phone number for operational alerts."},
            {"name": "WHATSAPP_API_URL", "description": "WhatsApp API endpoint if integrating external provider."},
            {"name": "WHATSAPP_ACCESS_TOKEN", "description": "Access token for WhatsApp API provider."},
            {"name": "WHATSAPP_PHONE_NUMBER_ID", "description": "Phone number ID in the WhatsApp provider."},
        ],
    }


@app.post("/whatsapp/connect", response_model=WhatsAppConnectResponse)
async def whatsapp_connect(
    payload: WhatsAppConnectRequest,
    user: UserAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> WhatsAppConnectResponse:
    phone_number = _normalize_phone_number(payload.phone_number)
    stmt = select(WhatsAppSession).where(WhatsAppSession.phone_number == phone_number, WhatsAppSession.user_id == user.id)

    try:
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            return WhatsAppConnectResponse(
                phone_number=existing.phone_number,
                session_id=existing.session_id,
                status=existing.status,
            )

        session_id = _generate_session_id()
        session = WhatsAppSession(
            user_id=user.id,
            phone_number=phone_number,
            session_id=session_id,
            status="connected",
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception("Failed to create WhatsApp session")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable") from exc

    return WhatsAppConnectResponse(
        phone_number=session.phone_number,
        session_id=session.session_id,
        status=session.status,
    )


@app.post("/webhook", response_model=BotResponse)
async def webhook(incoming_message: IncomingMessage, db: AsyncSession = Depends(get_db_session)) -> BotResponse:
    sender_phone: str | None = None
    owner_user_id: int | None = None
    if settings.whatsapp_only:
        try:
            sender_phone = _sender_to_phone(incoming_message.sender)
        except HTTPException as exc:
            raise HTTPException(status_code=400, detail="sender must be a WhatsApp phone number or JID") from exc

    enforce_session = settings.whatsapp_only or settings.require_session_id
    if enforce_session:
        provided = incoming_message.session_id
        if not provided:
            raise HTTPException(status_code=401, detail="session_id is required")

        try:
            session = (
                await db.execute(select(WhatsAppSession).where(WhatsAppSession.session_id == provided))
            ).scalar_one_or_none()
        except SQLAlchemyError as exc:
            await db.rollback()
            logger.exception("Failed to validate session id")
            raise HTTPException(status_code=503, detail="Database temporarily unavailable") from exc

        if not session:
            raise HTTPException(status_code=401, detail="Invalid session_id")
        owner_user_id = session.user_id
        if sender_phone:
            session_phone = _normalize_phone_for_compare(session.phone_number)
            sender_phone_normalized = _normalize_phone_for_compare(sender_phone)
            if session_phone != sender_phone_normalized:
                raise HTTPException(status_code=401, detail="session_id does not match sender phone")

    reply = generate_reply(
        incoming_message.message,
        sender=incoming_message.sender,
        prefix=settings.command_prefix,
        version=settings.levanter_version,
        plugins=settings.levanter_plugins,
    )

    try:
        db.add(
            MessageLog(
                user_id=owner_user_id,
                sender=incoming_message.sender,
                text=incoming_message.message,
                reply=reply,
            )
        )
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception("Failed to commit webhook message to database")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable") from exc

    return BotResponse(sender=incoming_message.sender, reply=reply)
