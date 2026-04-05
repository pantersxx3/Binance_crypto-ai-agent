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

    def compute_indicators(self, df: pd.DataFrame, interval: str = "1h") -> dict:
        """Calcula indicadores tecnicos para la vela mas reciente"""
        if df.empty or len(df) < 50:
            return self._default_indicators()
        
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = round(rsi.iloc[-1], 2) if not np.isnan(rsi.iloc[-1]) else 50
        
        ema9 = close.ewm(span=9, adjust=False).mean()
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema_cross = "BULLISH" if ema9.iloc[-1] > ema20.iloc[-1] else "BEARISH"
        
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_cross = "BULLISH" if macd_line.iloc[-1] > signal_line.iloc[-1] else "BEARISH"
        
        volume_sma = volume.rolling(20).mean()
        volume_ratio = round(volume.iloc[-1] / volume_sma.iloc[-1], 2) if volume_sma.iloc[-1] > 0 else 1.0
        volume_trend = "HIGH" if volume_ratio > 1.5 else "LOW" if volume_ratio < 0.5 else "NORMAL"
        
        high_low = high - low
        high_close = np.abs(high - close.shift())
        low_close = np.abs(low - close.shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(14).mean().iloc[-1]
        atr_pct = round((atr / close.iloc[-1]) * 100, 2)
        
        bb_middle = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = bb_middle + (bb_std * 2)
        bb_lower = bb_middle - (bb_std * 2)
        bb_position = round(
            (close.iloc[-1] - bb_lower.iloc[-1]) / 
            (bb_upper.iloc[-1] - bb_lower.iloc[-1]) * 100, 1
        ) if bb_upper.iloc[-1] != bb_lower.iloc[-1] else 50
        
        recent_high = high.rolling(50).max().iloc[-1]
        recent_low = low.rolling(50).min().iloc[-1]
        distance_to_high = round((recent_high - close.iloc[-1]) / close.iloc[-1] * 100, 2)
        distance_to_low = round((close.iloc[-1] - recent_low) / close.iloc[-1] * 100, 2)
        
        price_change_20 = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20] * 100 if len(close) >= 20 else 0
        if abs(price_change_20) > 3:
            trend_strength = "STRONG"
        elif abs(price_change_20) > 1:
            trend_strength = "MODERATE"
        else:
            trend_strength = "WEAK"
        
        return {
            "rsi": current_rsi,
            "market_regime": ema_cross.lower(),
            "trend_strength": trend_strength.lower(),
            "macd_cross": macd_cross.lower(),
            "volume_trend": volume_trend,
            "volume_ratio": volume_ratio,
            "atr_pct": atr_pct,
            "bb_position": bb_position,
            "distance_to_support": distance_to_low,
            "distance_to_resistance": distance_to_high
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