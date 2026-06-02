"""
FastAPI сервер для Mini App
Эндпоинты: /webapp (HTML), /api/*
"""
import os
from fastapi import FastAPI, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from db import get_settings, save_settings, get_alerts

app = FastAPI()

# static & templates
BASE = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")

@app.get("/webapp", response_class=HTMLResponse)
async def webapp():
    path = os.path.join(BASE, "templates", "index.html")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/settings")
async def api_settings(chat_id: int = Query(...)):
    s = await get_settings(chat_id)
    return JSONResponse({
        "timeframe": s["timeframe"],
        "pump_threshold": s["pump_threshold"],
        "volume_min_usd": s["volume_min_usd"],
        "zone_pct": s["zone_pct"],
        "ob_mult": s["ob_mult"],
        "volume_delta_mult": s["volume_delta_mult"],
        "fvg_enabled": bool(s["fvg_enabled"]),
        "lot_threshold": s["lot_threshold"],
        "paused": bool(s["paused"]),
    })

@app.post("/api/settings")
async def api_save_settings(request: Request):
    body = await request.json()
    chat_id = body.pop("chat_id", None)
    if not chat_id:
        return JSONResponse({"ok": False, "error": "no chat_id"}, status_code=400)
    await save_settings(chat_id, body)
    return JSONResponse({"ok": True})

@app.get("/api/alerts")
async def api_alerts(chat_id: int = Query(...), limit: int = 10):
    rows = await get_alerts(chat_id, limit)
    return JSONResponse({"alerts": rows})

@app.get("/api/status")
async def api_status():
    return JSONResponse({"status": "ok"})
