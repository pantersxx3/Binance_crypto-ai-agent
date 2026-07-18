"""
data/collector.py - Recolector de datos con SQLite local
VERSIÓN CORREGIDA: Agregados EMA50, EMA200, ADX, Distance 24h, OBV + fix NameError
"""
import pandas as pd
import numpy as np
from datetime import datetime
from binance.client import Client as BinanceClient
from loguru import logger
import sqlite3
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config


class DataCollector:
    """Recolector de datos de mercado con almacenamiento SQLite local"""

    def __init__(self, db_path: str = None):
        self.db_path = str(db_path or config.MARKET_DATA_DB)

        if config.BACKTESTING_MODE:
            logger.info("DataCollector: Usando MAINNET para datos históricos")
            self.binance = BinanceClient(
                config.BINANCE_MAINNET_KEY,
                config.BINANCE_MAINNET_SECRET,
                testnet=False
            )
        elif config.BINANCE_TESTNET:
            logger.info("DataCollector: Usando TESTNET")
            self.binance = BinanceClient(
                config.BINANCE_TESTNET_KEY,
                config.BINANCE_TESTNET_SECRET,
                testnet=True
            )
        else:
            logger.info("DataCollector: Usando MAINNET")
            self.binance = BinanceClient(
                config.BINANCE_MAINNET_KEY,
                config.BINANCE_MAINNET_SECRET
            )

        self._init_database()
        logger.info(f"DataCollector inicializado | DB: {self.db_path}")

    def _init_database(self):
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
        conn.commit()
        conn.close()

    def get_historical_klines(self, pair: str, interval: str = "1h",
                              start_date: str = None, end_date: str = None,
                              limit: int = None) -> pd.DataFrame:
        try:
            logger.info(f"Descargando klines | {pair} | {interval}")

            klines = self.binance.get_historical_klines(
                symbol=pair,
                interval=interval,
                start_str=start_date,
                end_str=end_date,
                limit=limit
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

            if start_date:
                df = df[df['timestamp'] >= pd.to_datetime(start_date)]
            if end_date:
                df = df[df['timestamp'] <= pd.to_datetime(end_date)]

            self._save_ohlcv(pair, df, interval)
            return df

        except Exception as e:
            logger.error(f"Error en get_historical_klines: {e}")
            return pd.DataFrame()

    def _save_ohlcv(self, pair: str, df: pd.DataFrame, interval: str):
        if df.empty:
            return
        conn = sqlite3.connect(self.db_path)
        for _, row in df.iterrows():
            try:
                conn.execute('''
                    INSERT OR REPLACE INTO ohlcv 
                    (pair, timestamp, open, high, low, close, volume, interval)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            except Exception:
                pass
        conn.commit()
        conn.close()

    def compute_indicators(self, df: pd.DataFrame, timeframe: str = "1h") -> dict: #, open_position: dict = None) -> dict:
        """
        Calcula indicadores técnicos mejorados.
        open_position: dict opcional con información de la posición actual
        """
        if len(df) < 30:
            return self._default_indicators()

        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']

        # === Indicadores básicos ===
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = round(rsi.iloc[-1], 2) if not np.isnan(rsi.iloc[-1]) else 50.0

        # EMA9 y EMA20 para regime
        ema9 = close.ewm(span=9, adjust=False).mean()
        ema20 = close.ewm(span=20, adjust=False).mean()
        market_regime = "bullish" if ema9.iloc[-1] > ema20.iloc[-1] else "bearish"

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_histogram = round((macd_line - signal_line).iloc[-1], 4)

        # Bollinger Bands
        sma20 = close.rolling(window=20).mean()
        std20 = close.rolling(window=20).std()
        bb_upper = sma20 + (std20 * 2)
        bb_lower = sma20 - (std20 * 2)
        bb_range = bb_upper.iloc[-1] - bb_lower.iloc[-1]
        bb_position = ((close.iloc[-1] - bb_lower.iloc[-1]) / bb_range * 100) if bb_range > 0 else 50.0
        bb_position = round(bb_position, 1)

        # Volume
        volume_sma20 = volume.rolling(window=20).mean()
        volume_ratio = round(volume.iloc[-1] / volume_sma20.iloc[-1], 2) if volume_sma20.iloc[-1] > 0 else 1.0
        volume_trend = "HIGH" if volume_ratio > 1.5 else "LOW" if volume_ratio < 0.8 else "NORMAL"

        # ATR
        tr = np.maximum(high - low, np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1))))
        atr14 = tr.rolling(window=14).mean()
        atr_pct = round(atr14.iloc[-1] / close.iloc[-1] * 100, 2) if close.iloc[-1] > 0 else 1.0

        # === NUEVOS INDICADORES ===
        ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
        ema200 = close.ewm(span=200, adjust=False).mean().iloc[-1]

        # Distance to 24h High / Low
        lookback = min(24, len(df))
        high_24h = high.iloc[-lookback:].max()
        low_24h = low.iloc[-lookback:].min()
        distance_24h_high = round((close.iloc[-1] - high_24h) / high_24h * 100, 2)
        distance_24h_low = round((close.iloc[-1] - low_24h) / low_24h * 100, 2)

        # OBV
        obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        obv_trend = "RISING" if obv.iloc[-1] > obv.iloc[-5] else "FALLING" if obv.iloc[-1] < obv.iloc[-5] else "FLAT"

        # ADX simplificado
        plus_dm = high.diff()
        minus_dm = low.diff()
        tr14 = tr.rolling(14).mean()
        plus_di = 100 * (plus_dm.rolling(14).mean() / tr14)
        minus_di = 100 * (minus_dm.rolling(14).mean() / tr14)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        #adx = round(dx.rolling(14).mean().iloc[-1], 1) if len(dx) > 14 else 20.0
        # === CÁLCULO CORRECTO DE ADX ===
        if len(high) > 20:  # Necesitamos más datos para estabilidad
            # True Range
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs()
            ], axis=1).max(axis=1)

            plus_dm = high.diff()
            minus_dm = low.diff()

            plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
            minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

            # Suavizado (Wilder’s smoothing)
            tr_smooth = tr.rolling(window=14, min_periods=14).mean()
            plus_di = 100 * (plus_dm.rolling(window=14, min_periods=14).mean() / tr_smooth)
            minus_di = 100 * (minus_dm.rolling(window=14, min_periods=14).mean() / tr_smooth)

            # DX
            dx = ((plus_di - minus_di).abs() / (plus_di + minus_di)) * 100

            # ADX final
            adx_series = dx.rolling(window=14, min_periods=14).mean()
            adx = round(adx_series.iloc[-1], 1) if not pd.isna(adx_series.iloc[-1]) else 20.0
            
        else:
            adx = 20.0

            # === FORZAR RANGO VÁLIDO ===
            #current_adx = max(0.0, min(100.0, current_adx))

        # Current position PnL %
        # open_position_pnl = 0.0
        # if open_position and open_position.get('entry_price'):
            # entry = open_position['entry_price']
            # side = open_position.get('direction', 'BUY')
            # pnl = (close.iloc[-1] - entry) / entry * 100
            # open_position_pnl = round(pnl if side == "BUY" else -pnl, 2)

        return {
            "rsi": current_rsi,
            "price": round(close.iloc[-1], 4),
            "macd_histogram": macd_histogram,
            "bb_position_pct": bb_position,
            "volume_ratio": volume_ratio,
            "volume_trend": volume_trend,
            "atr_pct": atr_pct,
            "market_regime": market_regime,
            "trend_strength": "STRONG" if adx > 25 else "MODERATE" if adx > 20 else "WEAK",
            "ema50": round(ema50, 4),
            "ema200": round(ema200, 4),
            "price_vs_ema50": round((close.iloc[-1] / ema50 - 1) * 100, 2),
            "price_vs_ema200": round((close.iloc[-1] / ema200 - 1) * 100, 2),
            "distance_24h_high": distance_24h_high,
            "distance_24h_low": distance_24h_low,
            "obv_trend": obv_trend,
            "adx": adx
            #"open_position_pnl": open_position_pnl
        }

    def _default_indicators(self) -> dict:
        return {
            "rsi": 50.0, "price": 0.0, "macd_histogram": 0.0, "bb_position_pct": 50.0,
            "volume_ratio": 1.0, "volume_trend": "NORMAL", "atr_pct": 1.0,
            "market_regime": "neutral", "trend_strength": "WEAK",
            "ema50": 0.0, "ema200": 0.0, "price_vs_ema50": 0.0,
            "distance_24h_high": 0.0, "distance_24h_low": 0.0,
            "obv_trend": "FLAT", "adx": 20.0 #, "open_position_pnl": 0.0
        }

    def get_latest_price(self, pair: str) -> float:
        try:
            if config.TRADE_MODE == "futures":
                ticker = self.binance.futures_symbol_ticker(symbol=pair)
            else:
                ticker = self.binance.get_symbol_ticker(symbol=pair)
            return float(ticker['price'])
        except Exception as e:
            logger.error(f"Error obteniendo precio de {pair}: {e}")
            return 0.0


if __name__ == "__main__":
    collector = DataCollector()
    print("DataCollector corregido y cargado correctamente")