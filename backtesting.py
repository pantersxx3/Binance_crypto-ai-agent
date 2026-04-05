"""
backtesting.py - Backtesting con sistema de sesiones
"""
import pandas as pd
import numpy as np
import time
import uuid
import signal
import json
from datetime import datetime
from loguru import logger
import config
from data.collector import DataCollector
from agents.brain import TradingBrain
from db import client as db

class Position:
    def __init__(self, trade_id: str, direction: str, entry_price: float,
                 quantity: float, confidence: int, decision_id: int, entry_time):
        self.id = trade_id
        self.direction = direction
        self.entry_price = entry_price
        self.quantity = quantity
        self.confidence = confidence
        self.decision_id = decision_id
        self.entry_time = entry_time
        self.exit_price = None
        self.exit_time = None
        self.pnl = None
        self.result = None

    def close(self, exit_price: float, exit_time, pnl: float, result: str):
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.pnl = pnl
        self.result = result

class BacktestEngine:
    def __init__(self, pair: str, start_date: str, end_date: str,
                 lookback_period: int = 300, model_name: str = None,
                 trade_mode: str = 'spot'):
        self.pair = pair
        self.start_date = start_date
        self.end_date = end_date
        self.lookback_period = lookback_period
        self.model_name = model_name or f"{pair}_backtest"
        self.trade_mode = trade_mode
        
        # Obtener la ruta de la base de datos del modelo
        self.db_path = config.get_model_db_path(self.model_name)
        
        self.session_id = f"BACKTEST_{uuid.uuid4().hex[:8]}"
        db.create_session(
            session_id=self.session_id,
            session_type='backtest',
            model_name=self.model_name,
            initial_balance=config.INITIAL_BALANCE,
            pair=pair,
            config_snapshot=json.dumps({
                'start_date': start_date,
                'end_date': end_date,
                'trade_mode': trade_mode
            }),
            db_path=self.db_path
        )
        
        self.collector = DataCollector(db_path=config.MARKET_DATA_DB)
        self.brain = TradingBrain(model_name=self.model_name)
        
        self.max_slots = config.MAX_SLOTS
        self.total_capital = config.INITIAL_BALANCE
        
        if hasattr(config, 'TRADE_AMOUNT_USDT') and config.TRADE_AMOUNT_USDT > 0:
            self.capital_per_slot = float(config.TRADE_AMOUNT_USDT)
        else:
            self.capital_per_slot = self.total_capital / max(self.max_slots, 1)
        
        self.positions = []
        self.closed_trades = []
        self.wins = 0
        self.losses = 0
        self.current_balance = self.total_capital
        self.shutdown_flag = False
        
        logger.info(f"Backtest Engine | Sesión: {self.session_id}")
        logger.info(f"Periodo: {start_date} → {end_date}")

    def load_data(self) -> pd.DataFrame:
        logger.info(f"Cargando datos para {self.pair}...")
        
        start_date_obj = pd.to_datetime(self.start_date)
        end_date_obj = pd.to_datetime(self.end_date)
        buffer_start = start_date_obj - pd.Timedelta(hours=self.lookback_period + 50)
        
        df = self.collector.get_historical_klines(
            self.pair, "1h",
            start_date=buffer_start,
            end_date=end_date_obj,
            limit=int((end_date_obj - buffer_start).total_seconds() / 3600) + 100
        )

        df = df[(df['timestamp'] >= pd.to_datetime(self.start_date)) & 
                (df['timestamp'] <= pd.to_datetime(self.end_date))].copy()
        
        logger.info(f"Cargadas {len(df)} velas totales")
        return df

    def calculate_indicators_with_window(self, df_window: pd.DataFrame) -> dict:
        if len(df_window) < 50:
            return self._default_indicators()
        
        close = df_window['close']
        
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
        
        price_change_20 = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20] * 100 if len(close) >= 20 else 0
        trend_strength = "STRONG" if abs(price_change_20) > 3 else "MODERATE" if abs(price_change_20) > 1 else "WEAK"
        
        return {
            "rsi": current_rsi,
            "market_regime": ema_cross.lower(),
            "trend_strength": trend_strength.lower(),
            "macd_cross": macd_cross.lower()
        }

    def _default_indicators(self) -> dict:
        return {"rsi": 50, "market_regime": "neutral", "trend_strength": "weak", "macd_cross": "none"}

    def simulate_trade(self, direction: str, entry_price: float, exit_price: float) -> dict:
        if direction == "BUY":
            price_change = (exit_price - entry_price) / entry_price
            hit = exit_price > entry_price
        elif direction == "SELL":
            price_change = (entry_price - exit_price) / entry_price
            hit = exit_price < entry_price
        else:
            return {"executed": False, "pnl": 0, "hit": None}
        
        pnl = price_change - config.COMMISSION
        return {"executed": True, "pnl": pnl, "hit": hit}

    def run(self) -> dict:
        original_handler = signal.signal(signal.SIGINT, self._signal_handler)
        
        try:
            df = self.load_data()
            start_idx = self.lookback_period
            total_velas = len(df) - start_idx - 1
            
            logger.info(f"Simulando {total_velas} velas...")
            start_time = time.time()
            
            for i in range(start_idx, len(df) - 1):
                if self.shutdown_flag:
                    break
                
                window_start = i - self.lookback_period
                df_window = df.iloc[window_start:i+1]
                current_row = df.iloc[i]
                
                indicators = self.calculate_indicators_with_window(df_window)
                current_rsi = indicators.get('rsi', 50)
                
                snapshot = {
                    "pair": self.pair,
                    "current_price": current_row['close'],
                    "usdt_balance": self.current_balance,
                    "indicators_1h": indicators,
                    "historical_timestamp": current_row['timestamp'],
                    "open_positions_count": len(self.positions),
                    "max_slots": self.max_slots,
                    "trade_mode": self.trade_mode,
                    "capital_per_slot": self.capital_per_slot
                }
                
                positions_to_close = []
                for pos in self.positions[:]:
                    analysis = self.brain.analyze(snapshot, source="backtest")
                    new_direction = analysis.get("direction", "HOLD")
                    if (pos.direction == "BUY" and new_direction == "SELL") or \
                       (pos.direction == "SELL" and new_direction == "BUY") or \
                       (pos.direction == "BUY" and current_rsi > 70) or \
                       (pos.direction == "SELL" and current_rsi < 30):
                        positions_to_close.append(pos)
                
                for pos in positions_to_close:
                    exit_price = current_row['close']
                    trade_result = self.simulate_trade(pos.direction, pos.entry_price, exit_price)
                    
                    if trade_result["executed"]:
                        pnl_dollars = self.capital_per_slot * trade_result["pnl"]
                        self.current_balance += pnl_dollars
                        
                        result = "WIN" if trade_result["hit"] else "LOSS"
                        if trade_result["hit"]:
                            self.wins += 1
                        else:
                            self.losses += 1
                        
                        self.brain.record_outcome(pos.decision_id, {
                            'entry_price': pos.entry_price,
                            'exit_price': exit_price,
                            'pnl': trade_result['pnl'] * 100,
                            'was_correct': trade_result["hit"],
                            'actual_move': 'UP' if exit_price > pos.entry_price else 'DOWN',
                            'actual_move_pct': (exit_price - pos.entry_price) / pos.entry_price * 100
                        })
                        
                        db.log_trade({
                            "session_id": self.session_id,
                            "trade_id": pos.id,
                            "pair": self.pair,
                            "side": pos.direction,
                            "entry_price": pos.entry_price,
                            "exit_price": exit_price,
                            "quantity": pos.quantity,
                            "usdt_value": self.capital_per_slot,
                            "pnl_pct": trade_result['pnl'] * 100,
                            "outcome": result,
                            "prediction_correct": trade_result["hit"],
                            "confidence": pos.confidence,
                            "reasoning_id": pos.decision_id,
                            "binance_order_id": f"BACKTEST_{pos.id[:8]}",
                            "is_dry_run": True,
                            "created_at": pos.entry_time.isoformat() if hasattr(pos.entry_time, 'isoformat') else datetime.now().isoformat(),
                            "closed_at": current_row['timestamp'].isoformat() if hasattr(current_row['timestamp'], 'isoformat') else datetime.now().isoformat()
                        })
                        
                        pos.close(exit_price, current_row['timestamp'], trade_result['pnl'] * 100, result)
                        self.closed_trades.append(pos)
                        self.positions.remove(pos)
                        
                        logger.info(f"[{i}] CERRAR {pos.direction} | Entry: ${pos.entry_price:.2f} → Exit: ${exit_price:.2f} | {result} | PnL: {trade_result['pnl']*100:+.2f}%")
                
                available_slots = self.max_slots - len(self.positions)
                if available_slots > 0:
                    analysis = self.brain.analyze(snapshot, source="backtest")
                    direction = analysis.get("direction", "HOLD")
                    confidence = analysis.get("confidence", 0)
                    decision_id = analysis.get("_decision_id")
                    
                    if direction == "SELL" and self.trade_mode == 'spot':
                        direction = "HOLD"
                    
                    if direction in ("BUY", "SELL") and confidence >= config.MIN_CONFIDENCE:
                        quantity = self.capital_per_slot / current_row['close']
                        quantity = round(quantity, 3)
                        trade_id = str(uuid.uuid4())
                        
                        logger.info(f"[{i}] ABRIR {direction} @ {confidence}% | ID: {trade_id[:8]} | Precio: ${current_row['close']:.2f}")
                        
                        db.log_trade({
                            "session_id": self.session_id,
                            "trade_id": trade_id,
                            "pair": self.pair,
                            "side": direction,
                            "entry_price": current_row['close'],
                            "quantity": quantity,
                            "usdt_value": self.capital_per_slot,
                            "confidence": confidence,
                            "reasoning_id": decision_id,
                            "binance_order_id": f"BACKTEST_{trade_id[:8]}",
                            "is_dry_run": True,
                            "created_at": current_row['timestamp'].isoformat() if hasattr(current_row['timestamp'], 'isoformat') else datetime.now().isoformat()
                        })
                        
                        new_position = Position(
                            trade_id=trade_id,
                            direction=direction,
                            entry_price=current_row['close'],
                            quantity=quantity,
                            confidence=confidence,
                            decision_id=decision_id,
                            entry_time=current_row['timestamp']
                        )
                        self.positions.append(new_position)
                
                if (i - start_idx) % 50 == 0:
                    logger.info(f"[{(i - start_idx) / total_velas * 100:.0f}%] Balance: ${self.current_balance:.2f}")
            
            if self.positions:
                last_price = df.iloc[-1]['close']
                logger.info(f"Cerrando {len(self.positions)} posicion(es) final(es) a ${last_price:.2f}")
                
                for pos in self.positions[:]:
                    trade_result = self.simulate_trade(pos.direction, pos.entry_price, last_price)
                    if trade_result["executed"]:
                        pnl_dollars = self.capital_per_slot * trade_result["pnl"]
                        self.current_balance += pnl_dollars
                        
                        result = "WIN" if trade_result["hit"] else "LOSS"
                        if trade_result["hit"]:
                            self.wins += 1
                        else:
                            self.losses += 1
                        
                        db.log_trade({
                            "session_id": self.session_id,
                            "trade_id": pos.id,
                            "pair": self.pair,
                            "side": pos.direction,
                            "entry_price": pos.entry_price,
                            "exit_price": last_price,
                            "quantity": pos.quantity,
                            "usdt_value": self.capital_per_slot,
                            "pnl_pct": trade_result['pnl'] * 100,
                            "outcome": result,
                            "prediction_correct": trade_result["hit"],
                            "confidence": pos.confidence,
                            "reasoning_id": pos.decision_id,
                            "is_dry_run": True,
                            "created_at": pos.entry_time.isoformat() if hasattr(pos.entry_time, 'isoformat') else datetime.now().isoformat(),
                            "closed_at": df.iloc[-1]['timestamp'].isoformat() if hasattr(df.iloc[-1]['timestamp'], 'isoformat') else datetime.now().isoformat()
                        })
                        
                        pos.close(last_price, df.iloc[-1]['timestamp'], trade_result['pnl'] * 100, result)
                        self.closed_trades.append(pos)
                
                self.positions = []
            
            elapsed = time.time() - start_time
            total_trades = self.wins + self.losses
            win_rate = (self.wins / total_trades * 100) if total_trades > 0 else 0
            total_return = (self.current_balance - self.total_capital) / self.total_capital * 100
            
            db.close_session(
                session_id=self.session_id,
                final_balance=self.current_balance,
                total_trades=total_trades,
                wins=self.wins,
                losses=self.losses,
                total_pnl=total_return
            )
            
            logger.info("\n" + "=" * 80)
            logger.info("RESULTADOS DEL BACKTESTING")
            logger.info("=" * 80)
            logger.info(f"Sesión: {self.session_id}")
            logger.info(f"Capital inicial: ${self.total_capital:.2f}")
            logger.info(f"Capital final: ${self.current_balance:.2f}")
            logger.info(f"Retorno: {total_return:+.2f}%")
            logger.info(f"Trades: {total_trades} | Wins: {self.wins} | Losses: {self.losses}")
            logger.info(f"Win Rate: {win_rate:.1f}%")
            logger.info("=" * 80)
            
            return {
                'session_id': self.session_id,
                'capital_initial': self.total_capital,
                'capital_final': self.current_balance,
                'total_return': total_return,
                'total_trades': total_trades,
                'wins': self.wins,
                'losses': self.losses,
                'win_rate': win_rate
            }
            
        finally:
            signal.signal(signal.SIGINT, original_handler)

    def _signal_handler(self, sig, frame):
        self.shutdown_flag = True
        logger.warning("Backtesting interrumpido por el usuario.")

if __name__ == "__main__":
    engine = BacktestEngine(
        pair="BNBUSDT",
        start_date="1 Jan 2024",
        end_date="1 Mar 2024",
        model_name="llama3.2:3b-instruct-q4_K_M",
        trade_mode='spot'
    )
    engine.run()