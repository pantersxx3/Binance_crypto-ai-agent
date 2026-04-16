"""
dashboard/app.py - Backend completo con todos los endpoints
"""
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path
from datetime import datetime
from loguru import logger
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

app = FastAPI(title="Crypto AI Trading Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / "logs"
DASHBOARD_DIR = Path(__file__).parent
MODELS_DIR = BASE_DIR / "trained_models"
DATA_DIR = BASE_DIR / "data"
TRADES_DB_PATH = DATA_DIR / "trades.db"

LOG_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

def _get_db_connection(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def _binance():
    from binance.client import Client as BinanceClient
    return BinanceClient(
        config.BINANCE_API_KEY,
        config.BINANCE_SECRET_KEY,
        requests_params={"timeout": 10},
        testnet=config.BINANCE_TESTNET
    )

# ============ ENDPOINTS PRINCIPALES ============

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = DASHBOARD_DIR / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding='utf-8'))
    return HTMLResponse(f"<h1>Dashboard not found</h1><p>{html_path}</p>", status_code=404)

@app.get("/api/status")
async def get_status():
    trade_amount = getattr(config, 'TRADE_AMOUNT_USDT', 100.0)
    max_slots = getattr(config, 'MAX_SLOTS', 1)
    initial_balance = trade_amount * max_slots
    
    c = _binance()
    balance_real = 0.0
    
    try:
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
    except Exception as e:
        logger.error(f"Error getting real balance: {e}")
    
    total_pnl_pct = 0.0
    if MODELS_DIR.exists():
        for db_file in MODELS_DIR.glob("*.db"):
            if '_summary' in db_file.name:
                continue
            try:
                conn = _get_db_connection(str(db_file))
                cursor = conn.cursor()
                cursor.execute('SELECT SUM(pnl) FROM outcomes WHERE pnl IS NOT NULL')
                row = cursor.fetchone()
                if row and row[0] is not None:
                    total_pnl_pct = float(row[0])
                conn.close()
                break
            except:
                pass
    
    final_balance = initial_balance + (initial_balance * total_pnl_pct / 100)
    
    return {
        "balance": round(final_balance, 2),
        "balance_initial": round(initial_balance, 2),
        "balance_pnl_pct": round(total_pnl_pct, 2),
        "trade_amount": round(trade_amount, 2),
        "max_slots": max_slots,
        "balance_real": round(balance_real, 2),
        "cfg": {
            "trade_mode": config.TRADE_MODE,
            "leverage": config.FUTURES_LEVERAGE,
            "dry_run": config.DRY_RUN,
            "pairs": config.TRADING_PAIRS,
            "min_confidence": config.MIN_CONFIDENCE,
            "cycle_interval": config.CYCLE_INTERVAL,
        }
    }

# ============ ENDPOINTS DE SESIONES ============

@app.get("/api/sessions")
async def get_sessions():
    """Obtiene todas las sesiones de trading"""
    try:
        if not TRADES_DB_PATH.exists():
            return {"sessions": []}
        
        conn = _get_db_connection(str(TRADES_DB_PATH))
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM trading_sessions ORDER BY created_at DESC')
        rows = cursor.fetchall()
        conn.close()
        return {"sessions": [dict(row) for row in rows]}
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        return {"sessions": [], "error": str(e)}

@app.get("/api/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """Obtiene detalle de una sesión con sus trades"""
    try:
        if not TRADES_DB_PATH.exists():
            return {"error": "Base de datos no encontrada"}
        
        conn = _get_db_connection(str(TRADES_DB_PATH))
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM trading_sessions WHERE session_id = ?', (session_id,))
        session_row = cursor.fetchone()
        
        if not session_row:
            conn.close()
            return {"error": "Sesión no encontrada"}
        
        cursor.execute('SELECT * FROM trade_history WHERE session_id = ? ORDER BY created_at DESC', (session_id,))
        trades = cursor.fetchall()
        conn.close()
        
        return {
            "session": dict(session_row),
            "trades": [dict(trade) for trade in trades]
        }
    except Exception as e:
        logger.error(f"Error getting session detail: {e}")
        return {"error": str(e)}

# ============ ENDPOINTS DE MODELOS ============

@app.get("/api/models")
async def list_models():
    """Lista todos los modelos entrenados"""
    models = []
    if MODELS_DIR.exists():
        for db_file in MODELS_DIR.glob("*.db"):
            if '_summary' in db_file.name:
                continue
            
            model_name = db_file.stem  # Nombre del archivo DB = nombre del modelo LLM
            stats = _get_model_stats_from_db(str(db_file))
            
            model_info = {
                "name": model_name,
                "db_path": str(db_file),
                "total_trades": stats['total_trades'],
                "win_rate": stats['win_rate'],
                "total_pnl": round(stats['total_pnl'], 2),
                "avg_confidence": stats.get('avg_confidence', 0),
                "total_decisions": stats.get('total_decisions', 0),
                "wins": stats['wins'],
                "losses": stats['losses']
            }
            models.append(model_info)
    
    models = sorted(models, key=lambda x: x.get("win_rate", 0), reverse=True)
    return {"models": models}

@app.get("/api/models/{model_name}/stats")
async def get_model_stats(model_name: str):
    """Obtiene estadísticas de un modelo específico"""
    import traceback
    try:
        safe_name = model_name.replace(":", "").replace("%3A", "")
        db_path = MODELS_DIR / f"{safe_name}.db"
        
        if not db_path.exists():
            return {"error": f"Modelo no encontrado: {db_path}"}
        
        conn = _get_db_connection(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        stats = {
            "summary": {
                "win_rate": 0,
                "total_trades": 0,
                "total_pnl_pct": 0,
                "avg_confidence": 0,
                "total_decisions": 0
            },
            "recent_decisions": [],
        }
        
        if 'decisions' in tables:
            cursor.execute("SELECT COUNT(*) FROM decisions")
            stats["summary"]["total_decisions"] = cursor.fetchone()[0] or 0
        
        if 'outcomes' in tables:
            cursor.execute('''
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) as correct,
                       AVG(d.confidence) as avg_conf,
                       SUM(o.pnl) as total_pnl
                FROM outcomes o
                INNER JOIN decisions d ON o.decision_id = d.id
            ''')
            row = cursor.fetchone()
            if row and row[0] > 0:
                total, correct = row[0], row[1] or 0
                stats["summary"] = {
                    "total_trades": total,
                    "correct_trades": correct,
                    "win_rate": round(correct / total * 100, 1) if total > 0 else 0,
                    "total_pnl_pct": round(row[3] or 0, 2),
                    "avg_confidence": round(row[2] or 0, 1),
                    "total_decisions": stats["summary"]["total_decisions"]
                }
        
        if 'decisions' in tables:
            cursor.execute('''
                SELECT d.timestamp, d.direction, d.confidence, d.hypothesis, 
                       d.rsi, d.trend_strength, o.was_correct, o.pnl, d.source
                FROM decisions d
                LEFT JOIN outcomes o ON d.id = o.decision_id
                ORDER BY d.timestamp DESC
                LIMIT 50
            ''')
            for row in cursor.fetchall():
                stats["recent_decisions"].append({
                    "timestamp": row[0],
                    "direction": row[1],
                    "confidence": row[2],
                    "hypothesis": row[3][:100] if row[3] else "",
                    "rsi": row[4],
                    "trend_strength": row[5],
                    "was_correct": row[6],
                    "pnl": row[7],
                    "source": row[8] if row[8] else "live"
                })
        
        conn.close()
        return stats
    except Exception as e:
        logger.error(f"Error en get_model_stats: {e}")
        return {"error": str(e), "trace": traceback.format_exc()}

@app.get("/api/models/{model_name}/sessions")
async def get_model_sessions(model_name: str):
    """Obtiene sesiones agrupadas por fecha para un modelo"""
    try:
        safe_name = model_name.replace(":", "").replace("%3A", "")
        db_path = MODELS_DIR / f"{safe_name}.db"
        
        if not db_path.exists():
            return {"error": f"Modelo no encontrado: {db_path}", "sessions": []}
        
        conn = _get_db_connection(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                DATE(historical_timestamp) as date,
                source,
                COUNT(*) as total_decisions,
                MIN(DATE(historical_timestamp)) as start_date,
                MAX(DATE(historical_timestamp)) as end_date
            FROM decisions
            WHERE historical_timestamp IS NOT NULL
            GROUP BY source, DATE(historical_timestamp)
            ORDER BY start_date DESC
        ''')
        rows = cursor.fetchall()
        
        sessions = []
        for row in rows:
            sessions.append({
                "date": row[0],
                "type": "Backtest" if row[1] == "backtest" else "Live",
                "total_decisions": row[2],
                "start_date": row[3],
                "end_date": row[4]
            })
        
        conn.close()
        return {"model": model_name, "sessions": sessions}
    except Exception as e:
        logger.error(f"Error en get_model_sessions: {e}")
        return {"error": str(e), "sessions": []}

@app.get("/api/models/{model_name}/trades")
async def get_model_trades(model_name: str, limit: int = 20, open_only: bool = False):
    """
    Obtiene trades de un modelo específico.
    
    open_only=True: Solo decisiones de LIVE sin cerrar (posiciones reales abiertas)
    open_only=False: Todas las decisiones (para historial)
    """
    try:
        safe_name = model_name.replace(":", "").replace("%3A", "")
        db_path = MODELS_DIR / f"{safe_name}.db"
        
        if not db_path.exists():
            return {"error": f"Modelo no encontrado: {db_path}", "trades": []}
        
        conn = _get_db_connection(str(db_path))
        cursor = conn.cursor()
        
        if open_only:
            # CORREGIDO: Solo decisiones de LIVE sin outcome = posiciones reales abiertas
            cursor.execute('''
                SELECT d.timestamp, d.pair, d.direction, d.confidence, 
                       d.price as entry_price, o.exit_price, o.pnl, o.was_correct,
                       d.source
                FROM decisions d
                LEFT JOIN outcomes o ON d.id = o.decision_id
                WHERE d.source = 'live' AND o.id IS NULL
                ORDER BY d.timestamp DESC
                LIMIT ?
            ''', (limit,))
        else:
            # Todas las decisiones con outcome registrado (para historial)
            cursor.execute('''
                SELECT d.timestamp, d.pair, d.direction, d.confidence, 
                       d.price as entry_price, o.exit_price, o.pnl, o.was_correct,
                       d.source
                FROM decisions d
                LEFT JOIN outcomes o ON d.id = o.decision_id
                WHERE o.id IS NOT NULL
                ORDER BY d.timestamp DESC
                LIMIT ?
            ''', (limit,))
        
        trades = []
        for row in cursor.fetchall():
            exit_price = row[5]
            was_correct = row[7]
            source = row[8]
            
            # Determinar estado
            if exit_price is None:
                status = 'OPEN' if source == 'live' else 'BACKTEST_NO_OUTCOME'
            else:
                status = 'WIN' if was_correct == 1 else 'LOSS'
            
            trades.append({
                "time": row[0],
                "pair": row[1],
                "side": row[2],
                "confidence": row[3],
                "entry_price": row[4],
                "exit_price": exit_price,
                "pnl": row[6],
                "status": status,
                "source": source,
                "stop_loss": None,
                "take_profit": None,
                "id": str(row[0]) if row[0] else "N/A"
            })
        
        conn.close()
        return {"model": model_name, "trades": trades, "count": len(trades)}
    except Exception as e:
        logger.error(f"Error en get_model_trades: {e}")
        return {"error": str(e), "trades": [], "count": 0}

@app.get("/api/models/{model_name}/decisions")
async def get_model_decisions(model_name: str, limit: int = 100):
    try:
        safe_name = model_name.replace(":", "").replace("%3A", "")
        db_path = MODELS_DIR / f"{safe_name}.db"
        
        if not db_path.exists():
            return {"error": f"Modelo no encontrado: {db_path}", "decisions": []}
        
        conn = _get_db_connection(str(db_path))
        cursor = conn.cursor()
        
        # CORREGIDO: Solo columnas que existen en la tabla decisions
        cursor.execute('''
            SELECT d.id, d.timestamp, d.pair, d.direction, d.confidence,
                   d.hypothesis, d.rsi, d.price, o.was_correct, o.pnl, o.exit_price
            FROM decisions d
            LEFT JOIN outcomes o ON d.id = o.decision_id
            ORDER BY d.timestamp DESC
            LIMIT ?
        ''', (limit,))
        
        decisions = []
        for row in cursor.fetchall():
            decisions.append({
                "id": row[0],
                "timestamp": row[1],
                "pair": row[2],
                "direction": row[3],
                "confidence": row[4],
                "hypothesis": row[5][:200] if row[5] else "",
                "rsi": row[6],
                "entry_price": row[7],
                "was_correct": row[8],
                "pnl": row[9],
                "exit_price": row[10]
            })
        
        conn.close()
        return {"model": model_name, "decisions": decisions, "count": len(decisions)}
    except Exception as e:
        logger.error(f"Error en get_model_decisions: {e}")
        return {"error": str(e), "decisions": []}

# ============ ENDPOINTS AUXILIARES ============

@app.get("/api/trades/recent")
async def get_recent_trades(pair: str = None, limit: int = 10):
    """Obtiene trades recientes desde trades.db"""
    from db import client as db_client
    
    trades = db_client.get_recent_trades(pair=pair, limit=limit)
    
    formatted = []
    for t in trades:
        formatted.append({
            'time': t.get('created_at', datetime.now().isoformat()),
            'pair': t.get('pair', 'UNKNOWN'),
            'type': t.get('side', 'HOLD'),
            'id': str(t.get('reasoning_id')) if t.get('reasoning_id') else (t.get('binance_order_id') or 'N/A'),
            'entry': f"${float(t.get('entry_price', 0)):.4f}" if t.get('entry_price') else '$0.0000',
            'exit': f"${float(t.get('exit_price', 0)):.4f}" if t.get('exit_price') else 'Open',
            'pnl': f"{float(t.get('pnl_pct', 0)):+.2f}%" if t.get('pnl_pct') is not None else 'Open',
            'status': 'WIN' if t.get('outcome') == 'WIN' else 'LOSS' if t.get('outcome') == 'LOSS' else 'OPEN'
        })
    
    return {"trades": formatted}

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    try:
        log_files = sorted(LOG_DIR.glob("agent_*.log"), reverse=True)
        if not log_files:
            await websocket.send_text("[No log file yet]")
            await asyncio.sleep(2)
            return
        
        with open(log_files[0], "r", encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines[-100:]:
                if line.strip():
                    await websocket.send_text(line.rstrip())
            
            while True:
                line = f.readline()
                if line:
                    await websocket.send_text(line.rstrip())
                else:
                    await asyncio.sleep(0.3)
    except WebSocketDisconnect:
        pass

@app.post("/api/close/{pair}")
async def close_position(pair: str):
    c = _binance()
    try:
        if config.TRADE_MODE == "futures":
            for o in c.futures_get_open_orders(symbol=pair):
                c.futures_cancel_order(symbol=pair, orderId=o["orderId"])
            for pos in c.futures_position_information(symbol=pair):
                if float(pos.get("positionAmt", 0)) > 0:
                    qty = float(pos["positionAmt"])
                    c.futures_create_order(symbol=pair, side="SELL", type="MARKET", quantity=qty, reduceOnly=True)
                    break
        else:
            for o in c.get_open_orders(symbol=pair):
                c.cancel_order(symbol=pair, orderId=o["orderId"])
            asset = pair.replace("USDT", "")
            for b in c.get_account()["balances"]:
                if b["asset"] == asset and float(b["free"]) > 0:
                    c.order_market_sell(symbol=pair, quantity=float(b["free"]))
                    break
        return {"success": True, "message": f"Position {pair} closed"}
    except Exception as e:
        return {"success": False, "message": str(e)}

# Agregar estos endpoints en dashboard/app.py

@app.get("/api/models/{model_name}/validations")
async def get_model_validations(model_name: str, limit: int = 50):
    """Obtiene validaciones de predicciones para un modelo"""
    try:
        safe_name = model_name.replace(":", "").replace("%3A", "")
        db_path = MODELS_DIR / f"{safe_name}.db"
        
        if not db_path.exists():
            return {"error": f"Modelo no encontrado: {db_path}", "validations": []}
        
        conn = _get_db_connection(str(db_path))
        cursor = conn.cursor()
        
        # Verificar si la tabla existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prediction_validations'")
        if not cursor.fetchone():
            conn.close()
            return {"validations": [], "count": 0, "message": "Tabla de validaciones no existe aún"}
        
        cursor.execute('''
            SELECT decision_id, validated_at, previous_direction, previous_confidence,
                   price_change_pct, validation_result, success, reason, opportunity_cost,
                   pattern_learned
            FROM prediction_validations
            ORDER BY validated_at DESC
            LIMIT ?
        ''', (limit,))
        
        validations = []
        for row in cursor.fetchall():
            validations.append({
                "decision_id": row[0],
                "validated_at": row[1],
                "previous_direction": row[2],
                "previous_confidence": row[3],
                "price_change_pct": row[4],
                "validation_result": row[5],
                "success": row[6] == 1,
                "reason": row[7][:200] if row[7] else "",
                "opportunity_cost": row[8],
                "pattern_learned": row[9]
            })
        
        conn.close()
        return {"model": model_name, "validations": validations, "count": len(validations)}
    except Exception as e:
        logger.error(f"Error en get_model_validations: {e}")
        return {"error": str(e), "validations": []}

@app.get("/api/models/{model_name}/patterns")
async def get_model_patterns(model_name: str):
    """Obtiene patrones aprendidos con sus estadísticas"""
    try:
        safe_name = model_name.replace(":", "").replace("%3A", "")
        db_path = MODELS_DIR / f"{safe_name}.db"
        
        if not db_path.exists():
            return {"error": f"Modelo no encontrado: {db_path}", "patterns": []}
        
        conn = _get_db_connection(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prediction_validations'")
        if not cursor.fetchone():
            conn.close()
            return {"patterns": [], "count": 0, "message": "Tabla de validaciones no existe aún"}
        
        cursor.execute('''
            SELECT pattern_learned, COUNT(*) as count,
                   SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                   AVG(opportunity_cost) as avg_opportunity_cost
            FROM prediction_validations
            WHERE pattern_learned != ''
            GROUP BY pattern_learned
            HAVING COUNT(*) >= 3
            ORDER BY count DESC
        ''')
        
        patterns = []
        for row in cursor.fetchall():
            patterns.append({
                "pattern": row[0],
                "count": row[1],
                "successes": row[2],
                "success_rate": round(row[2] / row[1] * 100, 1) if row[1] > 0 else 0,
                "avg_opportunity_cost": round(row[3] or 0, 2)
            })
        
        conn.close()
        return {"model": model_name, "patterns": patterns, "count": len(patterns)}
    except Exception as e:
        logger.error(f"Error en get_model_patterns: {e}")
        return {"error": str(e), "patterns": []}

@app.get("/api/models/{model_name}/validation-stats")
async def get_validation_stats(model_name: str):
    """Obtiene estadísticas generales de validaciones"""
    try:
        safe_name = model_name.replace(":", "").replace("%3A", "")
        db_path = MODELS_DIR / f"{safe_name}.db"
        
        if not db_path.exists():
            return {"error": f"Modelo no encontrado: {db_path}"}
        
        conn = _get_db_connection(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prediction_validations'")
        if not cursor.fetchone():
            conn.close()
            return {"total_validations": 0, "message": "Tabla de validaciones no existe aún"}
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as correct,
                SUM(CASE WHEN validation_result = 'CORRECT' THEN 1 ELSE 0 END) as correct_predictions,
                SUM(CASE WHEN validation_result = 'INCORRECT' THEN 1 ELSE 0 END) as incorrect_predictions,
                SUM(CASE WHEN validation_result = 'MISSED_OPPORTUNITY' THEN 1 ELSE 0 END) as missed_opportunities,
                SUM(CASE WHEN validation_result = 'SUBOPTIMAL' THEN 1 ELSE 0 END) as suboptimal,
                AVG(opportunity_cost) as avg_opportunity_cost,
                SUM(opportunity_cost) as total_opportunity_cost
            FROM prediction_validations
        ''')
        
        row = cursor.fetchone()
        conn.close()
        
        return {
            "total_validations": row[0] or 0,
            "correct_predictions": row[2] or 0,
            "incorrect_predictions": row[3] or 0,
            "missed_opportunities": row[4] or 0,
            "suboptimal": row[5] or 0,
            "validation_accuracy": round((row[2] or 0) / (row[0] or 1) * 100, 1),
            "avg_opportunity_cost": round(row[6] or 0, 2),
            "total_opportunity_cost": round(row[7] or 0, 2)
        }
    except Exception as e:
        logger.error(f"Error en get_validation_stats: {e}")
        return {"error": str(e)}
        
# ============ FUNCIONES AUXILIARES ============

def _get_model_stats_from_db(db_path: str) -> dict:
    """Función interna para obtener stats de un modelo"""
    if not os.path.exists(db_path):
        return {'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0, 'total_pnl': 0.0}
    
    try:
        conn = _get_db_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        stats = {'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0, 'total_pnl': 0.0}
        
        if 'outcomes' in tables:
            cursor.execute('''
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN was_correct = 0 THEN 1 ELSE 0 END) as losses,
                       SUM(pnl) as total_pnl
                FROM outcomes
            ''')
            row = cursor.fetchone()
            if row:
                stats['total_trades'] = row[0] or 0
                stats['wins'] = row[1] or 0
                stats['losses'] = row[2] or 0
                stats['total_pnl'] = row[3] or 0.0
                if stats['total_trades'] > 0:
                    stats['win_rate'] = round((stats['wins'] / stats['total_trades']) * 100, 1)
        
        if 'model_stats' in tables:
            cursor.execute('SELECT total_decisions, avg_confidence FROM model_stats WHERE id = 1')
            row = cursor.fetchone()
            if row:
                stats['total_decisions'] = row[0] or 0
                stats['avg_confidence'] = row[1] or 0.0
        
        conn.close()
        return stats
    except Exception as e:
        logger.error(f"Error getting stats from DB {db_path}: {e}")
        return {'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0, 'total_pnl': 0.0}

# ============ INICIO ============

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Dashboard iniciado en http://0.0.0.0:8000")
    uvicorn.run("dashboard.app:app", host="0.0.0.0", port=8000, reload=False)