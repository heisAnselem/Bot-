from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import generate_reply
from app.config import settings
from app.db import MessageLog, get_db_session, init_db

app = FastAPI(title=settings.app_name)


class IncomingMessage(BaseModel):
    sender: str = Field(min_length=1, max_length=128)
    message: str = Field(default="", max_length=2048)


class BotResponse(BaseModel):
    sender: str
    reply: str


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


@app.post("/webhook", response_model=BotResponse)
async def webhook(payload: IncomingMessage, db: AsyncSession = Depends(get_db_session)) -> BotResponse:
    reply = generate_reply(payload.message)

    db.add(MessageLog(sender=payload.sender, text=payload.message, reply=reply))
    await db.commit()

    return BotResponse(sender=payload.sender, reply=reply)
