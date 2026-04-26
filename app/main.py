from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


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
            {"name": "ENVIRONMENT", "description": "Environment name, e.g. production."},
            {"name": "BOT_NAME", "description": "Custom bot display name."},
            {"name": "REQUIRE_SESSION_ID", "description": "Set true to require valid session IDs for webhook calls."},
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

        session_id = f"wa_{uuid4().hex}"
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
    if settings.require_session_id:
        provided = incoming_message.session_id or settings.default_session_id
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

    reply = generate_reply(incoming_message.message)

    try:
        db.add(MessageLog(sender=incoming_message.sender, text=incoming_message.message, reply=reply))
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception("Failed to commit webhook message to database")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable") from exc

    return BotResponse(sender=incoming_message.sender, reply=reply)
