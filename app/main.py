from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import generate_reply
from app.config import settings
from app.db import MessageLog, get_db_session, init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


class IncomingMessage(BaseModel):
    sender: str = Field(min_length=1, max_length=128)
    message: str = Field(default="", max_length=2048)


class BotResponse(BaseModel):
    sender: str
    reply: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


@app.post("/webhook", response_model=BotResponse)
async def webhook(incoming_message: IncomingMessage, db: AsyncSession = Depends(get_db_session)) -> BotResponse:
    reply = generate_reply(incoming_message.message)

    try:
        db.add(MessageLog(sender=incoming_message.sender, text=incoming_message.message, reply=reply))
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception("Failed to commit webhook message to database")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable") from exc

    return BotResponse(sender=incoming_message.sender, reply=reply)
