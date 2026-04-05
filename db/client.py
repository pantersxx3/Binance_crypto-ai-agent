"""
db/client.py - Gestión de base de datos SQLite para trades y sesiones
ACTUALIZADO: Soporte completo para sesiones de trading
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from loguru import logger
import config

# Ruta de la base de datos
DB_PATH = Path(__file__).parent.parent / "data" / "trades.db"

def _get_connection():
    """Obtiene conexión a la base de datos"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_tables():
    """Inicializa todas las tablas necesarias"""
    conn = _get_connection()
    cursor = conn.cursor()
    
    # Tabla de sesiones
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trading_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            session_type TEXT NOT NULL,
            model_name TEXT,
            start_time TEXT NOT NULL,
            end_time TEXT,
            status TEXT DEFAULT 'active',
            initial_balance REAL DEFAULT 0,
            final_balance REAL DEFAULT 0,
            total_trades INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0,
            total_pnl REAL DEFAULT 0,
            pair TEXT,
            config_snapshot TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabla de historial de trades
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            trade_id TEXT UNIQUE NOT NULL,
            pair TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL,
            exit_price REAL,
            quantity REAL,
            usdt_value REAL,
            stop_loss_price REAL,
            take_profit_price REAL,
            pnl_pct REAL,
            pnl_usdt REAL,
            outcome TEXT,
            prediction_correct BOOLEAN,
            confidence INTEGER,
            reasoning_id TEXT,
            binance_order_id TEXT,
            oco_protected BOOLEAN DEFAULT FALSE,
            is_dry_run BOOLEAN DEFAULT TRUE,
            created_at TEXT,
            closed_at TEXT,
            FOREIGN KEY (session_id) REFERENCES trading_sessions(session_id)
        )
    ''')
    
    # Índices para mejor rendimiento
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_session_id ON trade_history(session_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trade_id ON trade_history(trade_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON trade_history(created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_session_status ON trading_sessions(status)')
    
    conn.commit()
    conn.close()
    logger.debug(f"SQLite tables initialized: {DB_PATH}")

def create_session(session_id: str, session_type: str, model_name: str = None, 
                   initial_balance: float = 0, pair: str = None, config_snapshot: str = None) -> str:
    """Crea una nueva sesión de trading"""
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO trading_sessions (
            session_id, session_type, model_name, start_time, status,
            initial_balance, pair, config_snapshot
        ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
    ''', (
        session_id,
        session_type,
        model_name,
        datetime.now().isoformat(),
        initial_balance,
        pair,
        config_snapshot
    ))
    
    conn.commit()
    conn.close()
    logger.info(f"Sesión creada: {session_id} ({session_type})")
    return session_id

def close_session(session_id: str, final_balance: float = 0, total_trades: int = 0,
                  wins: int = 0, losses: int = 0, total_pnl: float = 0):
    """Cierra una sesión de trading"""
    conn = _get_connection()
    cursor = conn.cursor()
    
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    cursor.execute('''
        UPDATE trading_sessions
        SET end_time = ?,
            status = 'closed',
            final_balance = ?,
            total_trades = ?,
            wins = ?,
            losses = ?,
            win_rate = ?,
            total_pnl = ?
        WHERE session_id = ?
    ''', (
        datetime.now().isoformat(),
        final_balance,
        total_trades,
        wins,
        losses,
        win_rate,
        total_pnl,
        session_id
    ))
    
    conn.commit()
    conn.close()
    logger.info(f"Sesión cerrada: {session_id} | PnL: {total_pnl:+.2f}%")

def log_trade(trade_record: dict):
    """Registra un trade en la base de datos"""
    conn = _get_connection()
    cursor = conn.cursor()
    
    # Determinar session_id (usar 'default' si no se proporciona)
    session_id = trade_record.get('session_id', 'default')
    
    # Verificar si es apertura o cierre
    is_opening = trade_record.get('exit_price') is None or trade_record.get('exit_price') == 0
    is_closing = trade_record.get('exit_price') is not None and trade_record.get('exit_price') > 0
    
    try:
        if is_opening:
            # Nueva posición
            cursor.execute('''
                INSERT INTO trade_history (
                    session_id, trade_id, pair, side, entry_price, quantity,
                    usdt_value, stop_loss_price, take_profit_price, confidence,
                    reasoning_id, binance_order_id, oco_protected, is_dry_run,
                    created_at, pnl_pct, outcome
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_id,
                trade_record.get('trade_id') or f"TRADE_{datetime.now().timestamp()}",
                trade_record.get('pair', 'UNKNOWN'),
                trade_record.get('side', 'HOLD'),
                trade_record.get('entry_price', 0),
                trade_record.get('quantity', 0),
                trade_record.get('usdt_value', 0),
                trade_record.get('stop_loss_price', 0),
                trade_record.get('take_profit_price', 0),
                trade_record.get('confidence', 0),
                trade_record.get('reasoning_id'),
                trade_record.get('binance_order_id'),
                trade_record.get('oco_protected', False),
                trade_record.get('is_dry_run', True),
                trade_record.get('created_at') or datetime.now().isoformat(),
                0,
                'OPEN'
            ))
        else:
            # Actualizar posición existente (cierre)
            pnl_usdt = trade_record.get('usdt_value', 0) * (trade_record.get('pnl_pct', 0) / 100)
            
            cursor.execute('''
                UPDATE trade_history
                SET exit_price = ?,
                    pnl_pct = ?,
                    pnl_usdt = ?,
                    outcome = ?,
                    prediction_correct = ?,
                    closed_at = ?,
                    binance_order_id = ?
                WHERE trade_id = ? OR reasoning_id = ?
            ''', (
                trade_record.get('exit_price', 0),
                trade_record.get('pnl_pct', 0),
                pnl_usdt,
                trade_record.get('outcome', 'CLOSED'),
                trade_record.get('prediction_correct', False),
                trade_record.get('closed_at') or datetime.now().isoformat(),
                trade_record.get('binance_order_id'),
                trade_record.get('reasoning_id'),
                trade_record.get('reasoning_id')
            ))
        
        conn.commit()
        
    except Exception as e:
        logger.error(f"Error logging trade: {e}")
        conn.rollback()
    finally:
        conn.close()

def get_recent_trades(pair: str = None, limit: int = 20, session_id: str = None):
    """Obtiene trades recientes"""
    conn = _get_connection()
    cursor = conn.cursor()
    
    query = '''
        SELECT * FROM trade_history
        WHERE 1=1
    '''
    params = []
    
    if pair:
        query += ' AND pair = ?'
        params.append(pair)
    
    if session_id:
        query += ' AND session_id = ?'
        params.append(session_id)
    
    query += ' ORDER BY created_at DESC LIMIT ?'
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_open_positions(session_id: str = None):
    """Obtiene posiciones abiertas (sin cerrar)"""
    conn = _get_connection()
    cursor = conn.cursor()
    
    query = '''
        SELECT * FROM trade_history
        WHERE exit_price IS NULL OR exit_price = 0
    '''
    params = []
    
    if session_id:
        query += ' AND session_id = ?'
        params.append(session_id)
    
    query += ' ORDER BY created_at DESC'
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_closed_trades(session_id: str = None, limit: int = 50):
    """Obtiene trades cerrados"""
    conn = _get_connection()
    cursor = conn.cursor()
    
    query = '''
        SELECT * FROM trade_history
        WHERE exit_price IS NOT NULL AND exit_price > 0
    '''
    params = []
    
    if session_id:
        query += ' AND session_id = ?'
        params.append(session_id)
    
    query += ' ORDER BY created_at DESC LIMIT ?'
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_session_stats(session_id: str = None):
    """Obtiene estadísticas de una sesión o globales"""
    conn = _get_connection()
    cursor = conn.cursor()
    
    if session_id:
        cursor.execute('''
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
                AVG(pnl_pct) as avg_pnl,
                SUM(pnl_usdt) as total_pnl_usdt
            FROM trade_history
            WHERE session_id = ? AND outcome IN ('WIN', 'LOSS')
        ''', (session_id,))
    else:
        cursor.execute('''
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
                AVG(pnl_pct) as avg_pnl,
                SUM(pnl_usdt) as total_pnl_usdt
            FROM trade_history
            WHERE outcome IN ('WIN', 'LOSS')
        ''')
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        total = row[0] or 0
        wins = row[1] or 0
        losses = row[2] or 0
        return {
            'total_trades': total,
            'wins': wins,
            'losses': losses,
            'win_rate': round((wins / total * 100), 1) if total > 0 else 0,
            'avg_pnl': round(row[3] or 0, 2),
            'total_pnl_usdt': round(row[4] or 0, 2)
        }
    
    return {'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0, 'avg_pnl': 0, 'total_pnl_usdt': 0}

def get_all_sessions():
    """Obtiene todas las sesiones"""
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM trading_sessions
        ORDER BY created_at DESC
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_session_by_id(session_id: str):
    """Obtiene una sesión específica"""
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM trading_sessions
        WHERE session_id = ?
    ''', (session_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None

# Inicializar tablas al importar
init_tables()