"""
dashboard/app.py - Backend mejorado del Crypto AI Trading Dashboard
"""
import asyncio
import json
import os
import sys
from pathlib import Path
# Agregar la raíz del proyecto al path
BASE_DIR = Path(__file__).parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
from datetime import datetime
from loguru import logger
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

import config
from db import client as db

app = FastAPI(title="Crypto AI Trading Dashboard - Mejorado")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent.parent
DASHBOARD_DIR = Path(__file__).parent
MODELS_DIR = BASE_DIR / "trained_models"
#TRADES_DB_PATH = BASE_DIR / "data" / "trades.db"

# ==================== ENDPOINTS MEJORADOS ====================

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = DASHBOARD_DIR / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding='utf-8'))
    return HTMLResponse("<h1>Dashboard no encontrado</h1>", status_code=404)

@app.get("/api/status")
async def get_status():
    """Estado general mejorado"""
    try:
        initial_balance = config.TRADE_AMOUNT_USDT * config.MAX_SLOTS
        
        # Balance real desde Binance
        balance_real = 0.0
        try:
            from binance.client import Client
            c = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET_KEY, testnet=config.BINANCE_TESTNET)
            if config.TRADE_MODE == "futures":
                for b in c.futures_account_balance():
                    if b["asset"] == "USDT":
                        balance_real = float(b["availableBalance"])
                        break
            else:
                account = c.get_account()
                for a in account["balances"]:
                    if a["asset"] == "USDT":
                        balance_real = float(a["free"])
                        break
        except:
            pass

        return {
            "balance_initial": round(initial_balance, 2),
            "balance_real": round(balance_real, 2),
            "trade_mode": config.TRADE_MODE,
            "dry_run": config.DRY_RUN,
            "pairs": config.TRADING_PAIRS,
            "min_confidence": config.MIN_CONFIDENCE,
            "cycle_interval": config.CYCLE_INTERVAL,
            "max_slots": config.MAX_SLOTS,
            "trade_amount_usdt": config.TRADE_AMOUNT_USDT,
            "auto_exit_enabled": config.AUTO_EXIT_ENABLED,
            "use_tp_sl": config.USE_TP_SL,
            "primary_tf": config.PRIMARY_TF,
            "updated_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error en /api/status: {e}")
        return {"error": str(e)}

@app.get("/api/models")
async def list_models():
    """Lista modelos con más información"""
    models = []
    if MODELS_DIR.exists():
        for db_file in MODELS_DIR.glob("*.db"):
            if '_summary' in db_file.name:
                continue
            model_name = db_file.stem
            try:
                conn = sqlite3.connect(str(db_file))
                cursor = conn.cursor()
                cursor.execute("SELECT win_rate, total_pnl, total_trades FROM model_stats WHERE id=1")
                row = cursor.fetchone()
                win_rate = round(row[0], 1) if row and row[0] else 0
                total_pnl = round(row[1], 2) if row and row[1] else 0
                total_trades = row[2] if row and row[2] else 0
                conn.close()

                models.append({
                    "name": model_name,
                    "win_rate": win_rate,
                    "total_pnl": total_pnl,
                    "total_trades": total_trades,
                    "db_size_mb": round(db_file.stat().st_size / (1024*1024), 2)
                })
            except:
                models.append({"name": model_name, "win_rate": 0, "total_pnl": 0, "total_trades": 0})

    models.sort(key=lambda x: x.get("win_rate", 0), reverse=True)
    return {"models": models}

# Mantengo los demás endpoints existentes (sessions, validations, patterns, etc.)
# ... (puedes mantener el resto de tu app.py original)

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    try:
        log_files = sorted((BASE_DIR / "logs").glob("*.log"), reverse=True)
        if not log_files:
            await websocket.send_text("Esperando logs...")
            await asyncio.sleep(2)
            return

        with open(log_files[0], "r", encoding='utf-8') as f:
            lines = f.readlines()[-100:]
            for line in lines:
                if line.strip():
                    await websocket.send_text(line.rstrip())
            
            while True:
                line = f.readline()
                if line:
                    await websocket.send_text(line.rstrip())
                else:
                    await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


if __name__ == "__main__":
    import uvicorn
    logger.info("Dashboard iniciado en http://0.0.0.0:8000")
    uvicorn.run("dashboard.app:app", host="0.0.0.0", port=8000, reload=False)