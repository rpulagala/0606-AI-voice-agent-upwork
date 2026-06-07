import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

from config import settings
from services.memory import ConversationMemory
from routes.health import router as health_router
from routes.voice import router as voice_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.memory = ConversationMemory(settings.REDIS_URL)
    yield
    await app.state.memory.close()


app = FastAPI(title="AI Voice Agent", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(voice_router)

# Serve frontend — API routes above take precedence; this catches everything else.
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
