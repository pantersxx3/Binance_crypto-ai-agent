"""
db package - Gestión unificada de bases de datos por modelo
Todos los trades y sesiones se almacenan en la base de datos de cada modelo.
"""
from .client import (
    init_tables,
    create_session,
    close_session,
    log_trade,
    get_recent_trades,
    get_open_positions,
    get_closed_trades,
    get_session_stats,
    get_all_sessions,
    get_session_by_id,
    DEFAULT_DB_PATH
)

__all__ = [
    'init_tables',
    'create_session',
    'close_session',
    'log_trade',
    'get_recent_trades',
    'get_open_positions',
    'get_closed_trades',
    'get_session_stats',
    'get_all_sessions',
    'get_session_by_id',
    'DEFAULT_DB_PATH'
]
