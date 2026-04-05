"""
config.py - Central configuration loader.
CORREGIDO: Credenciales duales Mainnet/Testnet, BACKTESTING_MODE automatico
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
MODELS_DIR = BASE_DIR / "trained_models"
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"

MODELS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

def load_config() -> dict:
    """Carga la configuracion desde config.json"""
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"No se encontro {CONFIG_FILE}\n"
            "   Copia config.example.json a config.json y configura tus claves."
        )
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Error en config.json: {e}")

CONFIG = load_config()

MARKET_DATA_DB = DATA_DIR / "market_data.db"

def get_model_db_path(model_name: str = "default") -> Path:
    safe_name = model_name.replace(":", "").replace("/", "")
    return MODELS_DIR / f"{safe_name}.db"

# Binance: Credenciales duales
BINANCE_MAINNET_KEY = CONFIG["binance"]["mainnet"]["api_key"]
BINANCE_MAINNET_SECRET = CONFIG["binance"]["mainnet"]["secret_key"]
BINANCE_TESTNET_KEY = CONFIG["binance"]["testnet"]["api_key"]
BINANCE_TESTNET_SECRET = CONFIG["binance"]["testnet"]["secret_key"]
BINANCE_USE_TESTNET = CONFIG["binance"].get("use_testnet", True)

# TRAIN_MODE activa backtesting, que requiere Mainnet para datos historicos
TRAIN_MODE = CONFIG["trading"].get("train", False)
BACKTESTING_MODE = TRAIN_MODE

# Seleccion automatica de credenciales
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

# LLM
LLM_API_KEY = CONFIG["llm"].get("api_key", "lm-studio")
LLM_MODEL = CONFIG["llm"].get("model", "deepseek-r1-distill-llama-8b-abliterated")
LLM_BASE_URL = CONFIG["llm"].get("base_url", "http://localhost:1234/v1")

USING_LOCAL_LLM = "localhost" in LLM_BASE_URL or LLM_API_KEY.lower() == "lm-studio"

# Trading Settings
TRADING_PAIRS = CONFIG["trading"].get("trading_pairs", ["BNBUSDT"])
CYCLE_INTERVAL = CONFIG["trading"].get("cycle_interval_seconds", 3600)
MIN_CONFIDENCE = CONFIG["trading"].get("min_confidence", 70)
DRY_RUN = CONFIG["trading"].get("dry_run", True)
TRADE_MODE = CONFIG["trading"].get("trade_mode", "spot").lower()
FUTURES_LEVERAGE = CONFIG["trading"].get("futures_leverage", 1)
LOG_LEVEL = CONFIG["trading"].get("log_level", "INFO")

TRAIN_START = CONFIG["trading"].get("train_start", "1 Jan 2024")
TRAIN_END = CONFIG["trading"].get("train_end", "1 Mar 2024")

SPOT_ORDER_TYPE = CONFIG["trading"].get("spot_order_type", "MARKET").upper()

# Position Management
TRADE_AMOUNT_USDT = CONFIG["position_management"].get("trade_amount_usdt", 100)
MAX_SLOTS = CONFIG["position_management"].get("max_slots", 1)
USE_TP_SL = CONFIG["position_management"].get("use_tp_sl", True)
STOP_LOSS_PCT = CONFIG["position_management"].get("stop_loss_pct", 1.0) / 100
TAKE_PROFIT_PCT = CONFIG["position_management"].get("take_profit_pct", 1.5) / 100
AUTO_EXIT_ENABLED = CONFIG["position_management"].get("auto_exit_enabled", False)

# Order Type
ORDER_TYPE = SPOT_ORDER_TYPE if TRADE_MODE == "spot" else CONFIG.get("order_type", "OCO").upper()

# Multi-Timeframe
PRIMARY_TF = CONFIG["multi_timeframe"].get("primary_tf", "1h").lower()
CONFIRMATION_TF = CONFIG["multi_timeframe"].get("confirmation_tf", "4h").lower()

# Backtesting
INITIAL_BALANCE = CONFIG["backtesting"].get("initial_balance", 100.0)
COMMISSION = CONFIG["backtesting"].get("commission", 0.001)

# Risk Management
MIN_BALANCE_USDT = CONFIG["risk_management"].get("min_balance_usdt", 100)
MAX_DAILY_LOSS_PCT = CONFIG["risk_management"].get("max_daily_loss_pct", -6.0)
MAX_POSITION_PCT = CONFIG["risk_management"].get("max_position_pct", 20) / 100

def validate():
    global TRADE_MODE, FUTURES_LEVERAGE, ORDER_TYPE, SPOT_ORDER_TYPE
    
    if TRADE_MODE not in ['spot', 'futures']:
        raise ValueError(f"TRADE_MODE invalido: {TRADE_MODE}")
    
    if TRADE_MODE == 'futures' and FUTURES_LEVERAGE < 1:
        raise ValueError(f"Leverage invalido para futures: {FUTURES_LEVERAGE}")
    
    if ORDER_TYPE not in ['OCO', 'MARKET', 'LIMIT']:
        raise ValueError(f"ORDER_TYPE invalido: {ORDER_TYPE}. Debe ser OCO, MARKET o LIMIT")
    
    if TRADE_MODE == "spot" and SPOT_ORDER_TYPE not in ['MARKET', 'LIMIT']:
        raise ValueError(f"SPOT_ORDER_TYPE invalido: {SPOT_ORDER_TYPE}. Debe ser MARKET o LIMIT")
    
    if not BINANCE_API_KEY or BINANCE_API_KEY == "":
        raise EnvironmentError("Missing config: binance.api_key")
    
    if not BINANCE_SECRET_KEY or BINANCE_SECRET_KEY == "":
        raise EnvironmentError("Missing config: binance.secret_key")
    
    if not TRADING_PAIRS:
        raise EnvironmentError("TRADING_PAIRS is empty")
    
    if MIN_CONFIDENCE < 50 or MIN_CONFIDENCE > 100:
        raise EnvironmentError(f"MIN_CONFIDENCE must be between 50 and 100, got {MIN_CONFIDENCE}")
    
    if TRADE_MODE == "futures" and (FUTURES_LEVERAGE < 1 or FUTURES_LEVERAGE > 20):
        raise EnvironmentError(f"FUTURES_LEVERAGE must be between 1 and 20, got {FUTURES_LEVERAGE}")
    
    if TRAIN_MODE:
        try:
            from datetime import datetime
            start = datetime.strptime(TRAIN_START, "%d %b %Y")
            end = datetime.strptime(TRAIN_END, "%d %b %Y")
            if start >= end:
                raise ValueError("train_start debe ser anterior a train_end")
        except ValueError as e:
            raise ValueError(f"Formato de fecha invalido. Usa: '1 Jan 2024'. Error: {e}")
    
    if USING_LOCAL_LLM:
        print(f"Using LOCAL server with model: {LLM_MODEL}")
    else:
        print(f"Using Groq cloud with {len(GROQ_API_KEYS)} keys")
    
    print(f"Config OK | Mode: {TRADE_MODE.upper()} | Dry run: {DRY_RUN}")
    print(f"TRADE_AMOUNT_USDT: ${TRADE_AMOUNT_USDT:.2f} | MAX_SLOTS: {MAX_SLOTS}")
    print(f"MIN_BALANCE_USDT: ${MIN_BALANCE_USDT:.2f}")
    print(f"ORDER_TYPE: {ORDER_TYPE} | Multi-TF: {PRIMARY_TF}+{CONFIRMATION_TF}")
    print(f"Train Mode: {TRAIN_MODE} | {TRAIN_START} -> {TRAIN_END}")
    print(f"Spot Order Type: {SPOT_ORDER_TYPE}")
    print(f"Binance: {'TESTNET' if BINANCE_TESTNET else 'MAINNET'} (Backtesting: {BACKTESTING_MODE})")

def save_config(config_dict: dict):
    """Guarda la configuracion actual a config.json"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config_dict, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    validate()