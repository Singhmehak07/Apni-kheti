"""Apni Kheti API — FastAPI app serving /api/v1 and the built web app."""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import get_settings
from integrations import http
from routers import insights, interview, meta, ml, voice

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await http.close()


app = FastAPI(title="Apni Kheti API", version="0.1.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
for r in (interview.router, insights.router, voice.router, meta.router, ml.router):
    app.include_router(r, prefix="/api/v1")

dist = get_settings().frontend_dist
if (dist / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str, request: Request):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        f = dist / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})
