"""
data/collector.py - Recolector de datos con SQLite local
ACTUALIZADO: Usa credenciales de Mainnet para backtesting automaticamente
"""
import pandas as pd
import numpy as np
import json
import time
from datetime import datetime, timedelta
from binance.client import Client as BinanceClient
from binance.exceptions import BinanceAPIException
import requests
from loguru import logger
import sys
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config

class DataCollector:
    """Recolector de datos de mercado con almacenamiento SQLite local"""
    
    def __init__(self, db_path: str = None):
        self.db_path = str(db_path or config.MARKET_DATA_DB)
        
        # Para BACKTESTING, usar Mainnet (tiene datos historicos completos)
        if config.BACKTESTING_MODE:
            logger.info("Connecting to Binance MAINNET for historical data")            
            self.binance = BinanceClient(
                config.BINANCE_MAINNET_KEY,
                config.BINANCE_MAINNET_SECRET,
                testnet=False
            )
        elif config.BINANCE_TESTNET:
            logger.info("Connecting to Binance TESTNET")            
            self.binance = BinanceClient(
                config.BINANCE_TESTNET_KEY,
                config.BINANCE_TESTNET_SECRET,
                testnet=True
            )
        else:
            logger.info("Connecting to Binance MAINNET")            
            self.binance = BinanceClient(
                config.BINANCE_MAINNET_KEY,
                config.BINANCE_MAINNET_SECRET
            )
        
        self._init_database()
        logger.info(f"DataCollector initialized with SQLite: {self.db_path}")
    
    def _init_database(self):
        """Crea tablas SQLite para almacenar datos de mercado"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ohlcv (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                interval TEXT,
                UNIQUE(pair, timestamp, interval)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS indicators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                interval TEXT NOT NULL,
                rsi REAL,
                macd_cross TEXT,
                market_regime TEXT,
                trend_strength TEXT,
                volume_trend TEXT,
                atr_pct REAL,
                bb_position REAL,
                UNIQUE(pair, timestamp, interval)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("SQLite tables created/verified")
    
    def get_historical_klines(self, pair: str, interval: str = "1h", 
                          start_date: str = None, end_date: str = None,
                          limit: int = None) -> pd.DataFrame:
        """Obtiene velas historicas de Binance"""
        try:
            logger.info(f"get_historical_klines | {pair} | {interval} | {start_date} -> {end_date}")
            
            start_str = str(start_date) if start_date else None
            end_str = str(end_date) if end_date else None

            klines = self.binance.get_historical_klines(
                symbol=pair,
                interval=interval,
                start_str=start_str,
                end_str=end_str
            )

            if not klines or len(klines) == 0:
                logger.warning(f"No se obtuvieron klines para {pair}")                
                return pd.DataFrame()

            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_av', 'trades', 'tb_base_av', 'tb_quote_av', 'ignore'
            ])

            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)

            df = df.sort_values('timestamp').drop_duplicates(subset=['timestamp']).reset_index(drop=True)

            logger.info(f"Obtenidas {len(df)} velas | Rango: {df['timestamp'].min()} -> {df['timestamp'].max()}")
            
            if start_date:
                df = df[df['timestamp'] >= pd.to_datetime(start_date)]
            if end_date:
                df = df[df['timestamp'] <= pd.to_datetime(end_date)]

            logger.info(f"   Despues de filtro: {len(df)} velas en el rango solicitado")

            self._save_ohlcv(pair, df, interval)
            return df

        except Exception as e:
            logger.error(f"Error en get_historical_klines: {type(e).__name__} - {e}")            
            import traceback
            logger.error(traceback.format_exc())
            return pd.DataFrame()

    def _save_ohlcv(self, pair: str, df: pd.DataFrame, interval: str):
        """Guarda datos OHLCV en SQLite"""
        conn = sqlite3.connect(self.db_path)
        
        for _, row in df.iterrows():
            try:
                conn.execute('''
                    INSERT OR REPLACE INTO ohlcv (
                        pair, timestamp, open, high, low, close, volume, interval
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    pair,
                    row['timestamp'].isoformat(),
                    row['open'],
                    row['high'],
                    row['low'],
                    row['close'],
                    row['volume'],
                    interval
                ))
            except Exception as e:
                logger.debug(f"Error saving OHLCV: {e}")
        
        conn.commit()
        conn.close()

    # En el método compute_indicators(), AGREGAR estos cálculos:

    def compute_indicators(self, df: pd.DataFrame, timeframe: str) -> dict:
        """Calcula indicadores técnicos con datos RAW para el LLM"""
        
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        # === RSI ===
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = round(rsi.iloc[-1], 2) if not np.isnan(rsi.iloc[-1]) else 50
        
        # === EMA para Market Regime ===
        ema9 = close.ewm(span=9, adjust=False).mean()
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema_cross = "BULLISH" if ema9.iloc[-1] > ema20.iloc[-1] else "BEARISH"
        
        # === MACD ===
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_histogram = macd_line - signal_line
        
        # === Bollinger Bands ===
        sma20 = close.rolling(window=20).mean()
        std20 = close.rolling(window=20).std()
        bb_upper = sma20 + (std20 * 2)
        bb_lower = sma20 - (std20 * 2)
        bb_width = (bb_upper - bb_lower) / sma20 * 100
        
        current_price = close.iloc[-1]
        bb_position = (current_price - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1]) * 100
        bb_position = round(bb_position, 1)
        
        # === Volumen ===
        volume_sma20 = volume.rolling(window=20).mean()
        volume_ratio = round(volume.iloc[-1] / volume_sma20.iloc[-1], 2) if volume_sma20.iloc[-1] > 0 else 1.0
        
        # === ATR (Volatilidad) ===
        tr = np.maximum(
            high - low,
            np.maximum(
                abs(high - close.shift(1)),
                abs(low - close.shift(1))
            )
        )
        atr14 = tr.rolling(window=14).mean()
        atr_pct = round(atr14.iloc[-1] / current_price * 100, 2) if current_price > 0 else 0
        
        # === Stochastic ===
        lowest_low = low.rolling(window=14).min()
        highest_high = high.rolling(window=14).max()
        stoch_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
        stoch_d = stoch_k.rolling(window=3).mean()
        current_stoch_k = round(stoch_k.iloc[-1], 2) if not np.isnan(stoch_k.iloc[-1]) else 50
        current_stoch_d = round(stoch_d.iloc[-1], 2) if not np.isnan(stoch_d.iloc[-1]) else 50
        
        # === Price Action ===
        price_change_1h = round((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100, 2)
        price_change_4h = round((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100, 2) if len(close) >= 5 else 0
        
        # === Retornar TODOS los indicadores RAW ===
        return {
            "rsi": current_rsi,
            "price": current_price,
            "macd_line": round(macd_line.iloc[-1], 4),
            "macd_signal": round(signal_line.iloc[-1], 4),
            "macd_histogram": round(macd_histogram.iloc[-1], 4),
            "bb_position_pct": bb_position,
            "bb_width_pct": round(bb_width.iloc[-1], 2),
            "volume_ratio": volume_ratio,
            "atr_pct": atr_pct,
            "stoch_k": current_stoch_k,
            "stoch_d": current_stoch_d,
            "price_change_1h": price_change_1h,
            "price_change_4h": price_change_4h,
            "market_regime": ema_cross.lower(),
            "trend_strength": "strong" if abs(price_change_4h) > 3 else "moderate" if abs(price_change_4h) > 1 else "weak",
            "macd_cross": "bullish" if macd_histogram.iloc[-1] > 0 else "bearish"
        }

    def _default_indicators(self) -> dict:
        return {
            "rsi": 50,
            "market_regime": "neutral",
            "trend_strength": "weak",
            "macd_cross": "none",
            "volume_trend": "NORMAL",
            "volume_ratio": 1.0,
            "atr_pct": 1.0,
            "bb_position": 50,
            "distance_to_support": 5.0,
            "distance_to_resistance": 5.0
        }

    def get_usdt_balance(self, use_config: bool = True) -> float:
        """Obtiene el balance de USDT"""
        if use_config:
            balance = float(config.TRADE_AMOUNT_USDT)
            logger.debug(f"Balance desde config: ${balance:.2f} USDT")            
            return balance
        
        try:
            if config.TRADE_MODE == "futures":
                account = self.binance.futures_account()
                balance = float(account['totalWalletBalance'])
            else:
                account = self.binance.get_account()
                balance = 0.0
                for asset in account['balances']:
                    if asset['asset'] == 'USDT':
                        balance = float(asset['free'])
                        break
            logger.debug(f"Balance desde Binance API: ${balance:.2f} USDT")            
            return balance
        except Exception as e:
            logger.error(f"Error getting balance from Binance: {e}")            
            logger.info("   Fallback a config.TRADE_AMOUNT_USDT")
            return float(config.TRADE_AMOUNT_USDT)

    def get_latest_price(self, pair: str) -> float:
        """Obtiene el precio mas reciente"""
        try:
            ticker = self.binance.get_symbol_ticker(symbol=pair)
            return float(ticker['price'])
        except Exception as e:
            logger.error(f"Error getting price for {pair}: {e}")            
            return 0.0