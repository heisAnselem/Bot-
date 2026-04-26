from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import html
import logging
import secrets

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import generate_reply
from app.config import settings
from app.db import MessageLog, WhatsAppSession, get_db_session, init_db

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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


@app.get("/", response_class=HTMLResponse)
async def dashboard(db: AsyncSession = Depends(get_db_session)) -> HTMLResponse:
    db_status = "online"
    total_sessions = 0
    connected_sessions = 0
    total_messages = 0
    latest_phone = "none"
    latest_session_id = "none"

    try:
        total_sessions = int((await db.execute(select(func.count(WhatsAppSession.id)))).scalar_one() or 0)
        connected_sessions = int(
            (
                await db.execute(
                    select(func.count(WhatsAppSession.id)).where(WhatsAppSession.status == "connected")
                )
            ).scalar_one()
            or 0
        )
        total_messages = int((await db.execute(select(func.count(MessageLog.id)))).scalar_one() or 0)
        latest = (
            await db.execute(select(WhatsAppSession).order_by(WhatsAppSession.created_at.desc()).limit(1))
        ).scalar_one_or_none()
        if latest:
            latest_phone = latest.phone_number
            latest_session_id = latest.session_id
    except SQLAlchemyError:
        db_status = "offline"

    escaped_prefix = html.escape(settings.command_prefix)
    escaped_bot_name = html.escape(settings.bot_name)
    escaped_latest_phone = html.escape(latest_phone)
    escaped_latest_session = html.escape(latest_session_id)
    whatsapp_mode = "enabled" if settings.whatsapp_only else "disabled"
    require_session = "enabled" if settings.require_session_id else "disabled"
    bridge_hint = "configured" if settings.whatsapp_api_url else "not configured"

    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escaped_bot_name} Control Panel</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, system-ui, Arial, sans-serif; }}
    body {{ margin: 0; background: #0d1117; color: #e6edf3; }}
    .wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin-top: 0; }}
    .grid {{ display: grid; grid-template-columns: 2fr 1fr; gap: 16px; }}
    .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 16px; }}
    .cards {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
    .label {{ color: #8b949e; font-size: 12px; text-transform: uppercase; }}
    .value {{ font-size: 20px; font-weight: 600; margin-top: 6px; }}
    .line {{ margin: 6px 0; color: #c9d1d9; word-break: break-all; }}
    input, button {{ width: 100%; border-radius: 10px; border: 1px solid #30363d; padding: 12px; background: #0d1117; color: #e6edf3; }}
    button {{ cursor: pointer; background: #238636; border-color: #2ea043; font-weight: 600; }}
    button:hover {{ background: #2ea043; }}
    .out {{ margin-top: 12px; background: #0d1117; border: 1px dashed #30363d; border-radius: 10px; padding: 12px; min-height: 44px; }}
    @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} .cards {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>{escaped_bot_name} Interface</h1>
    <p>WhatsApp-only mode for normal WhatsApp users. Use this page to monitor runtime state and generate session IDs.</p>
    <div class="cards">
      <div class="card"><div class="label">Database</div><div class="value">{db_status}</div></div>
      <div class="card"><div class="label">WhatsApp sessions</div><div class="value">{total_sessions}</div></div>
      <div class="card"><div class="label">Connected sessions</div><div class="value">{connected_sessions}</div></div>
    </div>
    <div class="grid" style="margin-top:16px;">
      <div class="card">
        <h3>System status</h3>
        <div class="line"><b>Bot Name:</b> {escaped_bot_name}</div>
        <div class="line"><b>Prefix:</b> {escaped_prefix}</div>
        <div class="line"><b>WhatsApp only:</b> {whatsapp_mode}</div>
        <div class="line"><b>Session required:</b> {require_session}</div>
        <div class="line"><b>Total logged messages:</b> {total_messages}</div>
        <div class="line"><b>Latest connected phone:</b> {escaped_latest_phone}</div>
        <div class="line"><b>Latest session id:</b> {escaped_latest_session}</div>
        <div class="line"><b>Bridge status:</b> {bridge_hint}</div>
      </div>
      <div class="card">
        <h3>Generate session ID</h3>
        <form id="connect-form">
          <input id="phone_number" name="phone_number" placeholder="+2348012345678" required />
          <div style="height: 10px;"></div>
          <button type="submit">Connect WhatsApp</button>
        </form>
        <div class="out" id="output">Waiting for input…</div>
      </div>
    </div>
  </div>
  <script>
    const form = document.getElementById('connect-form');
    const out = document.getElementById('output');
    form.addEventListener('submit', async (e) => {{
      e.preventDefault();
      const phone_number = document.getElementById('phone_number').value.trim();
      out.textContent = 'Generating session…';
      try {{
        const res = await fetch('/whatsapp/connect', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ phone_number }})
        }});
        const data = await res.json();
        if (!res.ok) {{
          out.textContent = data.detail || 'Failed to connect phone number.';
          return;
        }}
        out.textContent = `Phone: ${'{'}data.phone_number{'}'}\\nSession ID: ${'{'}data.session_id{'}'}\\nStatus: ${'{'}data.status{'}'}`;
      }} catch (err) {{
        out.textContent = 'Network error while connecting phone number.';
      }}
    }});
  </script>
</body>
</html>"""

    return HTMLResponse(content=page)


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
    payload: WhatsAppConnectRequest, db: AsyncSession = Depends(get_db_session)
) -> WhatsAppConnectResponse:
    phone_number = _normalize_phone_number(payload.phone_number)
    stmt = select(WhatsAppSession).where(WhatsAppSession.phone_number == phone_number)

    try:
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            return WhatsAppConnectResponse(
                phone_number=existing.phone_number,
                session_id=existing.session_id,
                status=existing.status,
            )

        session_id = _generate_session_id()
        session = WhatsAppSession(phone_number=phone_number, session_id=session_id, status="connected")
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
        db.add(MessageLog(sender=incoming_message.sender, text=incoming_message.message, reply=reply))
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception("Failed to commit webhook message to database")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable") from exc

    return BotResponse(sender=incoming_message.sender, reply=reply)
