"""
config.py — Central configuration loader.
VERSIÓN MEJORADA 2026: Soporte para exit_strategy flexible
"""
import json
from pathlib import Path
from loguru import logger

# Rutas base
BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
MODELS_DIR = BASE_DIR / "trained_models"
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"

# Crear directorios si no existen
MODELS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

def load_config() -> dict:
    """Carga la configuración desde config.json"""
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"No se encontró {CONFIG_FILE}\n"
            f"   Copia config.json.example a config.json y configura tus claves."
        )
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Error de formato en config.json: {e}")


CONFIG = load_config()

# ==================== RUTAS ====================
MARKET_DATA_DB = DATA_DIR / "market_data.db"
#TRADES_DB = DATA_DIR / "trades.db"

def get_model_db_path(model_name: str = "default") -> Path:
    safe_name = model_name.replace(":", "_").replace("/", "_").replace(" ", "_").replace(".", "_")
    return MODELS_DIR / f"{safe_name}.db"

def get_model_name_for_db() -> str:
    model_name = CONFIG["llm"].get("model", "default")
    return model_name.replace(":", "_").replace("/", "_").replace(" ", "_").replace(".", "_")

# ==================== BINANCE ====================
BINANCE_MAINNET_KEY = CONFIG["binance"]["mainnet"].get("api_key", "")
BINANCE_MAINNET_SECRET = CONFIG["binance"]["mainnet"].get("secret_key", "")
BINANCE_TESTNET_KEY = CONFIG["binance"]["testnet"].get("api_key", "")
BINANCE_TESTNET_SECRET = CONFIG["binance"]["testnet"].get("secret_key", "")
BINANCE_USE_TESTNET = CONFIG["binance"].get("use_testnet", True)

TRAIN_MODE = CONFIG["trading"].get("train", False)
BACKTESTING_MODE = TRAIN_MODE

if BACKTESTING_MODE:
    BINANCE_API_KEY = BINANCE_MAINNET_KEY
    BINANCE_SECRET_KEY = BINANCE_MAINNET_SECRET
    BINANCE_TESTNET = False
else:
    if BINANCE_USE_TESTNET:
        BINANCE_API_KEY = BINANCE_TESTNET_KEY
        BINANCE_SECRET_KEY = BINANCE_TESTNET_SECRET
        BINANCE_TESTNET = True
    else:
        BINANCE_API_KEY = BINANCE_MAINNET_KEY
        BINANCE_SECRET_KEY = BINANCE_MAINNET_SECRET
        BINANCE_TESTNET = False

# ==================== LLM ====================
LLM_API_KEY = CONFIG["llm"].get("api_key", "lm-studio")
LLM_MODEL = CONFIG["llm"].get("model", "qwen2.5-7b-instruct")
LLM_BASE_URL = CONFIG["llm"].get("base_url", "http://localhost:1234/v1")

LLM_PROVIDER_CONFIG = CONFIG.get("llm_provider", {})
USE_OLLAMAFREE = LLM_PROVIDER_CONFIG.get("use_ollama_free", True)
OLLAMAFREE_MODEL = LLM_PROVIDER_CONFIG.get("ollama_free_model", "deepseek-r1:latest")
OLLAMAFREE_FALLBACK = LLM_PROVIDER_CONFIG.get("fallback_to_local", True)
OLLAMAFREE_TIMEOUT = LLM_PROVIDER_CONFIG.get("timeout_seconds", 12000)

# ==================== TRADING SETTINGS ====================
TRADING_PAIRS = CONFIG["trading"].get("trading_pairs", ["BNBUSDT"])
CYCLE_INTERVAL = CONFIG["trading"].get("cycle_interval_seconds", 3600)
MIN_CONFIDENCE = CONFIG["trading"].get("min_confidence", 65)
DRY_RUN = CONFIG["trading"].get("dry_run", True)
TRADE_MODE = CONFIG["trading"].get("trade_mode", "spot").lower()
FUTURES_LEVERAGE = CONFIG["trading"].get("futures_leverage", 1)
LOG_LEVEL = CONFIG["trading"].get("log_level", "INFO")

TRAIN_START = CONFIG["trading"].get("train_start", "1 Jan 2026")
TRAIN_END = CONFIG["trading"].get("train_end", "31 Mar 2026")
SPOT_ORDER_TYPE = CONFIG["trading"].get("spot_order_type", "MARKET").upper()

# ==================== POSITION MANAGEMENT + EXIT STRATEGY ====================
TRADE_AMOUNT_USDT = CONFIG["position_management"].get("trade_amount_usdt", 100)
MAX_SLOTS = CONFIG["position_management"].get("max_slots", 1)

# NUEVA CONFIGURACIÓN FLEXIBLE
EXIT_STRATEGY = CONFIG["position_management"].get("exit_strategy", "ia_decide").lower()

# Para compatibilidad
USE_TP_SL = EXIT_STRATEGY in ["fixed_tp_sl", "hybrid"]
AUTO_EXIT_ENABLED = CONFIG["position_management"].get("auto_exit_enabled", True)

STOP_LOSS_PCT = CONFIG["position_management"].get("stop_loss_pct", 1.2) / 100
TAKE_PROFIT_PCT = CONFIG["position_management"].get("take_profit_pct", 2.5) / 100

# Protección lejana (solo en modo hybrid)
PROTECTION_SL_PCT = CONFIG["position_management"].get("protection_sl_pct", 3.0) / 100
PROTECTION_TP_PCT = CONFIG["position_management"].get("protection_tp_pct", 8.0) / 100

# ==================== ORDER TYPE ====================
ORDER_TYPE = SPOT_ORDER_TYPE if TRADE_MODE == "spot" else CONFIG.get("order_type", "MARKET").upper()

# ==================== MULTI-TIMEFRAME ====================
PRIMARY_TF = CONFIG["multi_timeframe"].get("primary_tf", "1h").lower()
CONFIRMATION_TF = CONFIG["multi_timeframe"].get("confirmation_tf", "4h").lower()

# ==================== BACKTESTING ====================
INITIAL_BALANCE = CONFIG["backtesting"].get("initial_balance", 100.0)
COMMISSION = CONFIG["backtesting"].get("commission", 0.001)

# ==================== RISK MANAGEMENT ====================
MIN_BALANCE_USDT = CONFIG["risk_management"].get("min_balance_usdt", 100)
MAX_DAILY_LOSS_PCT = CONFIG["risk_management"].get("max_daily_loss_pct", -6.0)
MAX_POSITION_PCT = CONFIG["risk_management"].get("max_position_pct", 20) / 100

# ==================== VALIDACIÓN ====================
def validate():
    """Validaciones mejoradas"""
    global TRADE_MODE, FUTURES_LEVERAGE, EXIT_STRATEGY

    if TRADE_MODE not in ['spot', 'futures']:
        raise ValueError(f"TRADE_MODE inválido: {TRADE_MODE}")

    if EXIT_STRATEGY not in ['fixed_tp_sl', 'ia_decide', 'hybrid']:
        logger.warning(f"EXIT_STRATEGY inválido: {EXIT_STRATEGY}. Usando 'ia_decide' por defecto.")
        EXIT_STRATEGY = 'ia_decide'

    if not BINANCE_API_KEY or BINANCE_API_KEY.strip() == "":
        raise EnvironmentError("Falta BINANCE_API_KEY en config.json")

    logger.info("Configuración validada correctamente")
    logger.info(f"   Modo: {TRADE_MODE.upper()} | Dry Run: {DRY_RUN} | Exit Strategy: {EXIT_STRATEGY.upper()}")
    logger.info(f"   Trade Amount: ${TRADE_AMOUNT_USDT:.2f} | Max Slots: {MAX_SLOTS} | Auto Exit: {AUTO_EXIT_ENABLED}")
    logger.info(f"   Modelo: {OLLAMAFREE_MODEL if USE_OLLAMAFREE else LLM_MODEL}")


def save_config(config_dict: dict):
    """Guarda cambios en config.json"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config_dict, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    validate()
    print("Configuración cargada y validada correctamente.")