"""
db/client.py - Cliente SQLite por modelo (Nueva arquitectura)
Ya no usamos trades.db global. Todo se guarda por modelo.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from loguru import logger


class DBClient:
    """Cliente que trabaja por modelo (cada modelo tiene su propia DB)"""

    def get_model_db(self, model_name: str):
        """Retorna la ruta de la base de datos del modelo"""
        safe_name = model_name.replace(":", "_").replace("/", "_").replace(" ", "_").replace(".", "_")
        db_path = Path("trained_models") / f"{safe_name}.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return db_path

    def init_model_db(self, model_name: str):
        """Inicializa las tablas en la DB del modelo"""
        db_path = self.get_model_db(model_name)
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                pair TEXT,
                direction TEXT,
                confidence INTEGER,
                hypothesis TEXT,
                indicators_snapshot TEXT,      -- JSON con todos los indicadores
                next_candle_change REAL,       -- Cambio % en la siguiente vela
                source TEXT,
                improved_hypothesis TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )''')

        c.execute('''CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            trade_id TEXT,
            pair TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL,
            exit_price REAL,
            quantity REAL,
            pnl_pct REAL,
            confidence INTEGER,
            outcome TEXT,
            hypothesis TEXT,
            session_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS progress (
            session_id TEXT PRIMARY KEY,
            last_vela INTEGER,
            balance REAL,
            wins INTEGER,
            losses INTEGER,
            updated_at TEXT
        )''')

        conn.commit()
        conn.close()
        logger.info(f"DB del modelo inicializada: {db_path.name}")

    # def log_decision(self, model_name: str, decision_data: dict):
        # """Guarda una decisión de la IA"""
        # db_path = self.get_model_db(model_name)
        # conn = sqlite3.connect(str(db_path))
        # c = conn.cursor()
        # c.execute('''INSERT INTO decisions 
            # (timestamp, pair, direction, confidence, hypothesis, source)
            # VALUES (?, ?, ?, ?, ?, ?)''', (
            # datetime.now().isoformat(),
            # decision_data.get('pair'),
            # decision_data.get('direction'),
            # decision_data.get('confidence'),
            # decision_data.get('hypothesis'),
            # decision_data.get('source', 'backtest')
        # ))
        # decision_id = c.lastrowid
        # conn.commit()
        # conn.close()
        # return decision_id

    def log_trade(self, model_name: str, trade_data: dict):
        """Guarda una operación real (compra o venta)"""
        db_path = self.get_model_db(model_name)
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute('''INSERT INTO trades 
            (timestamp, trade_id, pair, direction, entry_price, exit_price, quantity, 
             pnl_pct, confidence, outcome, hypothesis, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
            datetime.now().isoformat(),
            trade_data.get('trade_id'),
            trade_data.get('pair'),
            trade_data.get('direction'),
            trade_data.get('entry_price'),
            trade_data.get('exit_price'),
            trade_data.get('quantity'),
            trade_data.get('pnl_pct'),
            trade_data.get('confidence'),
            trade_data.get('outcome'),
            trade_data.get('hypothesis'),
            trade_data.get('session_id')
        ))
        conn.commit()
        conn.close()
    
    def get_trade_by_id(self, model_name: str, trade_id: str):
        """Obtiene los datos completos de un trade específico por su trade_id"""
        try:
            db_path = self.get_model_db(model_name)
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row  # Para poder acceder por nombre de columna
            c = conn.cursor()

            c.execute('''
                SELECT 
                    id,
                    timestamp,
                    trade_id,
                    pair,
                    direction,
                    entry_price,
                    exit_price,
                    quantity,
                    pnl_pct,
                    confidence,
                    outcome,
                    hypothesis,
                    session_id
                FROM trades 
                WHERE trade_id = ?
            ''', (trade_id,))

            row = c.fetchone()
            conn.close()

            if row:
                return dict(row)
            else:
                return None

        except Exception as e:
            logger.error(f"Error obteniendo trade por ID {trade_id}: {e}")
            return None
            
    def save_progress(self, model_name: str, session_id: str, last_vela: int, 
                  balance: float, wins: int, losses: int):
        try:
            db_path = self.get_model_db(model_name)
            conn = sqlite3.connect(str(db_path))
            c = conn.cursor()

            c.execute('''CREATE TABLE IF NOT EXISTS progress (
                session_id TEXT PRIMARY KEY,
                last_vela INTEGER,
                balance REAL,
                wins INTEGER,
                losses INTEGER,
                updated_at TEXT
            )''')

            c.execute('''INSERT OR REPLACE INTO progress 
                (session_id, last_vela, balance, wins, losses, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)''', 
                (session_id, last_vela, balance, wins, losses, datetime.now().isoformat()))

            conn.commit()
            conn.close()
            
            logger.info(f"Progreso guardado | Vela: {last_vela} | Balance: ${balance:.2f} | Session: {session_id[:12]}...")
            
        except Exception as e:
            logger.error(f"Error guardando progreso: {e}")

    def get_progress(self, model_name: str, session_id: str):
        try:
            db_path = self.get_model_db(model_name)
            conn = sqlite3.connect(str(db_path))
            c = conn.cursor()
            c.execute("SELECT * FROM progress WHERE session_id = ?", (session_id,))
            row = c.fetchone()
            conn.close()

            if row:
                logger.info(f"Progreso cargado | Última vela: {row[1]}")
                return {
                    'last_vela': row[1],
                    'balance': row[2],
                    'wins': row[3],
                    'losses': row[4]
                }
            else:
                logger.debug(f"No se encontró progreso previo para session {session_id[:12]}...")
                return None

        except Exception as e:
            logger.error(f"Error leyendo progreso: {e}")
            return None


# Instancia global
client = DBClient()