"""
trainer.py - Sistema de entrenamiento y backtesting offline
FIXES:
  - logger.info de progreso estaba fuera del loop (indentación incorrecta)
  - compute_indicators ahora requiere timeframe arg (pasado correctamente)
  - _save_model_summary: logger.debug estaba fuera de la función
"""
import os
import sys
import json
import sqlite3
import time
import pandas as pd
import numpy as np
from datetime import datetime
from loguru import logger
import warnings
warnings.filterwarnings('ignore')
from agents.brain import TradingBrain
from data.collector import DataCollector
import config


class ModelTrainer:
    """Entrenador de modelos con backtesting offline"""
    
    def __init__(self, models_dir: str = "trained_models"):
        self.models_dir = models_dir
        os.makedirs(models_dir, exist_ok=True)
        self.training_results = {}
        logger.info(f"ModelTrainer inicializado | Directorio: {models_dir}")

    def _get_model_db_path(self, model_name: str) -> str:
        safe_name = model_name.replace(":", "_").replace("/", "_")
        db_path = os.path.join(self.models_dir, f"{safe_name}.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return db_path

    def _get_brain_for_model(self, model_name: str) -> TradingBrain:
        db_path = self._get_model_db_path(model_name)
        brain = TradingBrain(model_name=model_name)
        brain.db_path = db_path
        return brain

    def load_historical_data(self, pair: str, start_date: str, end_date: str,
                             interval: str = "1h") -> pd.DataFrame:
        logger.info(f"Cargando datos históricos para {pair} ({start_date} - {end_date})")
        collector = DataCollector(db_path=config.MARKET_DATA_DB)
        df = collector.get_historical_klines(pair, interval, start_date=start_date, end_date=end_date)
        
        start_ts = pd.to_datetime(start_date)
        end_ts = pd.to_datetime(end_date)
        df = df[(df['timestamp'] >= start_ts) & (df['timestamp'] <= end_ts)]
        
        logger.info(f"Cargadas {len(df)} velas para entrenamiento")
        return df

    def train_model(self, pair: str, df: pd.DataFrame, model_name: str,
                    min_confidence: int = 70, trade_mode: str = 'spot') -> dict:
        """Entrena un modelo específico con posibilidad de interrupción limpia"""
        import signal
        
        self.trade_mode = trade_mode
        stop_training = False
        
        def signal_handler(sig, frame):
            nonlocal stop_training
            print("\n")
            logger.warning("Entrenamiento interrumpido por usuario. Guardando progreso...")
            stop_training = True
        
        original_handler = signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        try:
            logger.info(f"Entrenando modelo: {model_name}")
            logger.info(f"  Modo de trading: {trade_mode.upper()}")
            
            brain = self._get_brain_for_model(model_name)
            collector = DataCollector(db_path=str(config.MARKET_DATA_DB))
            
            trades = []
            correct = 0
            total = 0
            pnl_sum = 0
            confidence_sum = 0
            
            stats_by_zone = {
                'oversold': {'trades': 0, 'correct': 0, 'pnl': 0},
                'neutral': {'trades': 0, 'correct': 0, 'pnl': 0},
                'overbought': {'trades': 0, 'correct': 0, 'pnl': 0}
            }
            
            stats_by_trend = {
                'weak': {'trades': 0, 'correct': 0, 'pnl': 0},
                'moderate': {'trades': 0, 'correct': 0, 'pnl': 0},
                'strong': {'trades': 0, 'correct': 0, 'pnl': 0}
            }
            
            start_time = time.time()
            total_steps = len(df) - 51  # pasos totales para progreso
            
            for i in range(50, len(df) - 1):
                if stop_training:
                    logger.info("Entrenamiento detenido por el usuario")
                    break
                
                current_row = df.iloc[i]
                next_row = df.iloc[i + 1]
                
                historical_data = df.iloc[max(0, i - 50):i + 1]
                # FIX: compute_indicators requiere timeframe como segundo arg
                indicators = collector.compute_indicators(historical_data, "1h")
                
                snapshot = {
                    "pair": pair,
                    "current_price": current_row['close'],
                    "usdt_balance": 1000,
                    "indicators_1h": indicators,
                    "trade_mode": self.trade_mode
                }
                
                pred_start = time.time()
                analysis = brain.analyze(snapshot)
                elapsed = time.time() - pred_start
                
                direction = analysis.get("direction", "HOLD")
                confidence = analysis.get("confidence", 0)
                hypothesis = analysis.get("hypothesis", "")
                
                # En modo spot, SELL no tiene sentido (no hay posición corta)
                if direction == "SELL" and self.trade_mode == 'spot':
                    logger.debug(f"[{i}] SELL ignorado en entrenamiento SPOT")
                    direction = "HOLD"
                
                if direction != "HOLD" and confidence >= min_confidence:
                    if direction == "BUY":
                        was_correct = next_row['close'] > current_row['close']
                        pnl = (next_row['close'] - current_row['close']) / current_row['close']
                    else:
                        was_correct = next_row['close'] < current_row['close']
                        pnl = (current_row['close'] - next_row['close']) / current_row['close']
                    
                    total += 1
                    pnl_sum += pnl
                    confidence_sum += confidence
                    
                    if was_correct:
                        correct += 1
                    
                    try:
                        brain.record_outcome(analysis.get("_decision_id", 0), {
                            'pair': pair,
                            'model': model_name,
                            'direction': direction,
                            'confidence': confidence,
                            'entry_price': current_row['close'],
                            'exit_price': next_row['close'],
                            'actual_move': 'UP' if next_row['close'] > current_row['close'] else 'DOWN',
                            'actual_move_pct': (next_row['close'] - current_row['close']) / current_row['close'] * 100,
                            'was_correct': was_correct,
                            'pnl': pnl * 100
                        })
                    except Exception as e:
                        logger.debug(f"No se pudo guardar outcome: {e}")
                    
                    rsi = indicators.get('rsi', 50)
                    if rsi < 30:
                        zone = 'oversold'
                    elif rsi > 70:
                        zone = 'overbought'
                    else:
                        zone = 'neutral'
                    
                    stats_by_zone[zone]['trades'] += 1
                    stats_by_zone[zone]['correct'] += 1 if was_correct else 0
                    stats_by_zone[zone]['pnl'] += pnl
                    
                    trend = indicators.get('trend_strength', 'weak')
                    if trend in stats_by_trend:
                        stats_by_trend[trend]['trades'] += 1
                        stats_by_trend[trend]['correct'] += 1 if was_correct else 0
                        stats_by_trend[trend]['pnl'] += pnl
                    
                    trades.append({
                        'timestamp': current_row['timestamp'],
                        'price': current_row['close'],
                        'rsi': rsi,
                        'trend': trend,
                        'direction': direction,
                        'confidence': confidence,
                        'was_correct': was_correct,
                        'pnl': pnl,
                        'response_time': elapsed,
                        'hypothesis': hypothesis
                    })
                
                # FIX: este log de progreso estaba FUERA del loop (indentación incorrecta)
                if (i - 50) % 100 == 0 and i > 50:
                    progress = (i - 50) / max(total_steps, 1) * 100
                    win_rate = (correct / total * 100) if total > 0 else 0
                    logger.info(
                        f"[{progress:.0f}%] {current_row['timestamp'].strftime('%Y-%m-%d %H:%M')} | "
                        f"Precio: ${current_row['close']:.2f} | Trades: {total} | Win: {win_rate:.1f}%"
                    )
            
            if stop_training and total > 0:
                logger.info(f"Guardando resultados parciales ({total} trades procesados)")
            
            elapsed_total = time.time() - start_time
            
            win_rate = (correct / total * 100) if total > 0 else 0
            avg_pnl = (pnl_sum / total * 100) if total > 0 else 0
            avg_confidence = (confidence_sum / total) if total > 0 else 0
            
            for zone in stats_by_zone:
                if stats_by_zone[zone]['trades'] > 0:
                    stats_by_zone[zone]['win_rate'] = stats_by_zone[zone]['correct'] / stats_by_zone[zone]['trades'] * 100
                    stats_by_zone[zone]['avg_pnl'] = stats_by_zone[zone]['pnl'] / stats_by_zone[zone]['trades'] * 100
            
            for trend in stats_by_trend:
                if stats_by_trend[trend]['trades'] > 0:
                    stats_by_trend[trend]['win_rate'] = stats_by_trend[trend]['correct'] / stats_by_trend[trend]['trades'] * 100
                    stats_by_trend[trend]['avg_pnl'] = stats_by_trend[trend]['pnl'] / stats_by_trend[trend]['trades'] * 100
            
            result = {
                'model': model_name,
                'pair': pair,
                'trade_mode': self.trade_mode,
                'total_trades': total,
                'correct_trades': correct,
                'win_rate': win_rate,
                'total_pnl_pct': avg_pnl * total,
                'avg_pnl_pct': avg_pnl,
                'avg_confidence': avg_confidence,
                'avg_response_time': elapsed_total / max(total, 1),
                'trades': trades,
                'stats_by_zone': stats_by_zone,
                'stats_by_trend': stats_by_trend,
                'db_path': brain.db_path
            }
            
            self.training_results[model_name] = result
            self._save_model_summary(model_name, result)
            
            logger.info(f"\n{'='*60}")
            logger.info(f"Entrenamiento completado para {model_name}")
            if len(df) > 51:
                logger.info(f"Período: {df['timestamp'].iloc[50]} → {df['timestamp'].iloc[-2]}")
            logger.info(f"  Total trades: {total} | Win rate: {win_rate:.1f}% | PnL: {result['total_pnl_pct']:+.2f}%")
            logger.info(f"{'='*60}\n")
            
            return result
        
        finally:
            signal.signal(signal.SIGINT, original_handler)

    def _save_model_summary(self, model_name: str, result: dict):
        summary_path = os.path.join(self.models_dir, f"{model_name.replace(':', '_')}_summary.json")
        
        summary = {
            'model': result['model'],
            'pair': result['pair'],
            'trade_mode': result.get('trade_mode', 'spot'),
            'total_trades': result['total_trades'],
            'correct_trades': result['correct_trades'],
            'win_rate': result['win_rate'],
            'total_pnl_pct': result['total_pnl_pct'],
            'avg_pnl_pct': result['avg_pnl_pct'],
            'avg_confidence': result['avg_confidence'],
            'avg_response_time': result['avg_response_time'],
            'stats_by_zone': result['stats_by_zone'],
            'stats_by_trend': result['stats_by_trend'],
            'trained_at': datetime.now().isoformat()
        }
        
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        # FIX: este logger estaba fuera de la función (indentación incorrecta)
        logger.debug(f"Resumen guardado: {summary_path}")
