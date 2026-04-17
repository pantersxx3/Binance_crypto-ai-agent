"""
main.py - Punto de entrada unificado para trading en vivo y backtesting
ACTUALIZADO: Soporte para --model, --backtest, --live y más argumentos
"""
import argparse
import pandas as pd
import numpy as np
import time
import uuid
import signal
import sys
import json
from datetime import datetime
from pathlib import Path
from loguru import logger
import config
from data.collector import DataCollector
from agents.brain import TradingBrain
from risk.manager import RiskManager, TradeOrder
from execution.executor import TradeExecutor
from db import client as db

# Configurar logger
#logger.remove()
logger.add(
    sys.stdout,
    format="{time:HH:mm:ss} | {level} | {message}",
    level=config.LOG_LEVEL,
    colorize=False
)
logger.add(
    config.LOGS_DIR / "trading_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level=config.LOG_LEVEL,
    rotation="1 day",
    retention="7 days"
)

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
        self.binance_order_id = None

    def close(self, exit_price: float, exit_time, pnl: float, result: str):
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.pnl = pnl
        self.result = result


class TradingBot:
    def __init__(self, model_name: str = None):
        self.collector = DataCollector(db_path=config.MARKET_DATA_DB)
        
        # Usar modelo desde argumento o desde config
        self.model_name = model_name or config.get_model_name_for_db()
        self.brain = TradingBrain(model_name=self.model_name)
        
        self.risk_manager = RiskManager()
        self.executor = TradeExecutor()
        
        self.positions = []
        self.max_slots = config.MAX_SLOTS
        self.total_capital = config.INITIAL_BALANCE
        self.current_balance = self.total_capital
        self.shutdown_flag = False
        
        self.previous_decision = None
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("Trading Bot inicializado")
        logger.info(f"Modelo LLM: {self.model_name}")
        logger.info(f"Mode: {config.TRADE_MODE.upper()} | Dry run: {config.DRY_RUN}")
        logger.info(f"TRADE_AMOUNT_USDT: ${config.TRADE_AMOUNT_USDT:.2f} | MAX_SLOTS: {self.max_slots}")
        logger.info(f"ORDER_TYPE: {config.ORDER_TYPE} | Multi-TF: {config.PRIMARY_TF}+{config.CONFIRMATION_TF}")
        logger.info(f"Cycle Interval: {config.CYCLE_INTERVAL}s | Timeframe: {config.PRIMARY_TF}")

    def _signal_handler(self, sig, frame):
        self.shutdown_flag = True
        logger.warning("Bot interrumpido por el usuario.")

    def get_market_snapshot(self, pair: str) -> dict:
        try:
            klines = self.collector.get_historical_klines(
                pair, 
                config.PRIMARY_TF,
                start_date=(datetime.now().strftime("%d %b %Y")),
                limit=300
            )
            
            if klines.empty or len(klines) < 50:
                logger.warning(f"No hay suficientes datos para {pair}")
                return None
            
            indicators = self.collector.compute_indicators(klines, config.PRIMARY_TF)
            current_price = self.collector.get_latest_price(pair)
            
            return {
                "pair": pair,
                "current_price": current_price,
                "usdt_balance": self.current_balance,
                "indicators_1h": indicators,
                "historical_timestamp": datetime.now(),
                "open_positions_count": len(self.positions),
                "max_slots": self.max_slots,
                "trade_mode": config.TRADE_MODE,
                "capital_per_slot": config.TRADE_AMOUNT_USDT
            }
        except Exception as e:
            logger.error(f"Error obteniendo snapshot: {e}")
            return None

    def should_close_position(self, position: Position, current_rsi: float, new_direction: str) -> tuple:
        should_close = False
        reason = ""
        
        if position.direction == "BUY" and new_direction == "SELL":
            should_close = True
            reason = "IA recomienda SELL"
        elif position.direction == "SELL" and new_direction == "BUY":
            should_close = True
            reason = "IA recomienda BUY"
        
        if not should_close and position.direction == "BUY" and current_rsi > 70:
            should_close = True
            reason = f"Take profit: RSI={current_rsi} > 70"
        elif not should_close and position.direction == "SELL" and current_rsi < 30:
            should_close = True
            reason = f"Take profit: RSI={current_rsi} < 30"
        
        return should_close, reason

    def run_live(self):
        logger.info("Iniciando trading en LIVE")
        pair = config.TRADING_PAIRS[0]
        
        while not self.shutdown_flag:
            try:
                snapshot = self.get_market_snapshot(pair)
                if not snapshot:
                    logger.warning("No hay datos de mercado, esperando...")
                    time.sleep(config.CYCLE_INTERVAL)
                    continue
                
                current_candle_time = snapshot["historical_timestamp"]
                if current_candle_time == self.previous_decision:
                    logger.debug("Misma vela, esperando nueva vela...")
                    time.sleep(min(300, config.CYCLE_INTERVAL))
                    continue
                
                self.previous_decision = current_candle_time
                current_rsi = snapshot["indicators_1h"].get("rsi", 50)
                
                positions_to_close = []
                for pos in self.positions[:]:
                    analysis = self.brain.analyze(snapshot, source="live")
                    new_direction = analysis.get("direction", "HOLD")
                    should_close, reason = self.should_close_position(pos, current_rsi, new_direction)
                    if should_close:
                        positions_to_close.append((pos, reason))
                
                for pos, reason in positions_to_close:
                    exit_price = self.collector.get_latest_price(pair)
                    pnl_pct = (exit_price - pos.entry_price) / pos.entry_price * 100
                    if pos.direction == "SELL":
                        pnl_pct = -pnl_pct
                    
                    pnl_dollars = config.TRADE_AMOUNT_USDT * (pnl_pct / 100)
                    self.current_balance += pnl_dollars
                    
                    result = "WIN" if pnl_pct > 0 else "LOSS"
                    
                    self.brain.record_outcome(pos.decision_id, {
                        "entry_price": pos.entry_price,
                        "exit_price": exit_price,
                        "pnl": pnl_pct,
                        "was_correct": pnl_pct > 0,
                        "actual_move": "UP" if exit_price > pos.entry_price else "DOWN",
                        "actual_move_pct": pnl_pct
                    })
                    
                    trade_record = {
                        "pair": pair,
                        "side": pos.direction,
                        "entry_price": pos.entry_price,
                        "exit_price": exit_price,
                        "quantity": pos.quantity,
                        "usdt_value": config.TRADE_AMOUNT_USDT,
                        "pnl_pct": pnl_pct,
                        "outcome": result,
                        "prediction_correct": pnl_pct > 0,
                        "confidence": pos.confidence,
                        "reasoning_id": pos.decision_id,
                        "binance_order_id": f"LIVE_{pos.id[:8]}",
                        "is_dry_run": config.DRY_RUN
                    }
                    db.log_trade(trade_record)
                    
                    pos.close(exit_price, datetime.now(), pnl_pct, result)
                    self.positions.remove(pos)
                    
                    logger.info(f"CERRAR {pos.direction} | Entry: ${pos.entry_price:.2f} → Exit: ${exit_price:.2f} | {result} | PnL: {pnl_pct:+.2f}%")
                
                available_slots = self.max_slots - len(self.positions)
                if available_slots > 0:
                    analysis = self.brain.analyze(snapshot, source="live")
                    direction = analysis.get("direction", "HOLD")
                    confidence = analysis.get("confidence", 0)
                    decision_id = analysis.get("_decision_id")
                    
                    if direction == "SELL" and config.TRADE_MODE == "spot":
                        logger.warning(f"SELL ignorado en modo SPOT")
                        direction = "HOLD"
                    
                    if direction in ("BUY", "SELL") and confidence >= config.MIN_CONFIDENCE:
                        order = self.risk_manager.evaluate(
                            direction=direction,
                            confidence=confidence,
                            snapshot=snapshot,
                            reasoning=analysis
                        )
                        
                        if order and order.approved:
                            if config.DRY_RUN:
                                quantity = config.TRADE_AMOUNT_USDT / snapshot["current_price"]
                                trade_id = str(uuid.uuid4())
                                
                                new_position = Position(
                                    trade_id=trade_id,
                                    direction=direction,
                                    entry_price=snapshot["current_price"],
                                    quantity=quantity,
                                    confidence=confidence,
                                    decision_id=decision_id,
                                    entry_time=datetime.now()
                                )
                                self.positions.append(new_position)
                                
                                logger.info(f"ABRIR {direction} @ {confidence}% | Precio: ${snapshot['current_price']:.2f}")
                            else:
                                result = self.executor.execute(order)
                                if result.get("binance_order_id") and not result.get("binance_order_id", "").startswith("FAILED"):
                                    trade_id = str(uuid.uuid4())
                                    new_position = Position(
                                        trade_id=trade_id,
                                        direction=direction,
                                        entry_price=result.get("entry_price", snapshot["current_price"]),
                                        quantity=result.get("quantity", 0),
                                        confidence=confidence,
                                        decision_id=decision_id,
                                        entry_time=datetime.now()
                                    )
                                    new_position.binance_order_id = result.get("binance_order_id")
                                    self.positions.append(new_position)
                                    
                                    logger.info(f"Orden ejecutada: {result.get('binance_order_id')}")
                
                logger.info(f"Balance: ${self.current_balance:.2f} | Posiciones: {len(self.positions)}/{self.max_slots}")
                
            except Exception as e:
                logger.error(f"Error en ciclo de trading: {e}")
            
            time.sleep(config.CYCLE_INTERVAL)
        
        logger.info("Bot detenido.")


class BacktestEngine:
    def __init__(self, pair: str, start_date: str, end_date: str,
                 lookback_period: int = 300, model_name: str = None,
                 trade_mode: str = 'spot'):
        self.pair = pair
        self.start_date = start_date
        self.end_date = end_date
        self.lookback_period = lookback_period
        
        # Usar modelo desde argumento o desde config
        self.model_name = model_name or config.get_model_name_for_db()
        self.trade_mode = trade_mode
        
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
                'trade_mode': trade_mode,
                'model': self.model_name
            })
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
        
        logger.info(f"Backtest Engine | Modelo: {self.model_name}")
        logger.info(f"Sesión: {self.session_id}")
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
            logger.info(f"Modelo: {self.model_name}")
            logger.info(f"Sesión: {self.session_id}")
            logger.info(f"Capital inicial: ${self.total_capital:.2f}")
            logger.info(f"Capital final: ${self.current_balance:.2f}")
            logger.info(f"Retorno: {total_return:+.2f}%")
            logger.info(f"Trades: {total_trades} | Wins: {self.wins} | Losses: {self.losses}")
            logger.info(f"Win Rate: {win_rate:.1f}%")
            logger.info("=" * 80)
            
            return {
                'session_id': self.session_id,
                'model': self.model_name,
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


def parse_arguments():
    """Parsea argumentos de línea de comandos"""
    parser = argparse.ArgumentParser(
        description='Crypto AI Trading Bot - Trading automatizado con IA',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python main.py                                              # Live trading (según config.json)
  python main.py --backtest                                   # Backtesting con fechas de config.json
  python main.py --backtest --start "1 Jan 2024" --end "1 Mar 2024"
  python main.py --backtest --model gemma-3-4b-it-abliterated # Backtesting con modelo específico
  python main.py --live --model qwen2.5-7b-instruct           # Live trading con modelo específico
  python main.py --backtest --pair ETHUSDT --start "1 Feb 2024" --end "1 Apr 2024"
  python main.py --live --dry-run                             # Live trading en modo simulación
  python main.py --list-models                                # Listar modelos disponibles
        """
    )
    
    parser.add_argument(
        '--backtest', '-b',
        action='store_true',
        help='Ejecutar backtesting en lugar de live trading'
    )
    
    parser.add_argument(
        '--live', '-l',
        action='store_true',
        help='Ejecutar live trading (por defecto)'
    )
    
    parser.add_argument(
        '--model', '-m',
        type=str,
        help='Nombre del modelo LLM a usar (ej: qwen2.5-7b-instruct, gemma-3-4b-it-abliterated)'
    )
    
    parser.add_argument(
        '--list-models',
        action='store_true',
        help='Listar todos los modelos disponibles en trained_models/'
    )
    
    parser.add_argument(
        '--start', '-s',
        type=str,
        help='Fecha de inicio para backtesting (ej: "1 Jan 2024")'
    )
    
    parser.add_argument(
        '--end', '-e',
        type=str,
        help='Fecha de fin para backtesting (ej: "1 Mar 2024")'
    )
    
    parser.add_argument(
        '--pair', '-p',
        type=str,
        help='Par de trading (ej: BNBUSDT, ETHUSDT)'
    )
    
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='Forzar modo dry run (simulación sin dinero real)'
    )
    
    parser.add_argument(
        '--config', '-c',
        type=str,
        default='config.json',
        help='Archivo de configuración (default: config.json)'
    )
    
    return parser.parse_args()


def list_available_models():
    """Lista todos los modelos disponibles en trained_models/"""
    logger.info("=" * 80)
    logger.info("MODELOS DISPONIBLES")
    logger.info("=" * 80)
    
    if not MODELS_DIR.exists():
        logger.info("No hay modelos entrenados aún")
        return
    
    models = []
    for db_file in MODELS_DIR.glob("*.db"):
        if '_summary' in db_file.name:
            continue
        
        model_name = db_file.stem
        db_size = db_file.stat().st_size / (1024 * 1024)  # MB
        
        # Obtener estadísticas básicas
        try:
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            stats = {}
            if 'outcomes' in tables:
                cursor.execute('SELECT COUNT(*) FROM outcomes')
                stats['trades'] = cursor.fetchone()[0]
            
            if 'model_stats' in tables:
                cursor.execute('SELECT win_rate, total_pnl FROM model_stats WHERE id = 1')
                row = cursor.fetchone()
                if row:
                    stats['win_rate'] = row[0]
                    stats['pnl'] = row[1]
            
            conn.close()
            
            models.append({
                'name': model_name,
                'size_mb': round(db_size, 2),
                'stats': stats
            })
        except Exception as e:
            logger.debug(f"Error leyendo {db_file}: {e}")
    
    if models:
        logger.info(f"{'Nombre del Modelo':<40} {'Tamaño':<10} {'Trades':<10} {'Win Rate':<10} {'PnL':<10}")
        logger.info("-" * 80)
        for model in sorted(models, key=lambda x: x['name']):
            stats = model['stats']
            trades = stats.get('trades', 0)
            win_rate = f"{stats.get('win_rate', 0):.1f}%" if 'win_rate' in stats else 'N/A'
            pnl = f"{stats.get('pnl', 0):+.2f}%" if 'pnl' in stats else 'N/A'
            logger.info(f"{model['name']:<40} {model['size_mb']:<10.2f}MB {trades:<10} {win_rate:<10} {pnl:<10}")
    else:
        logger.info("No hay modelos entrenados aún")
    
    logger.info("=" * 80)


def main():
    args = parse_arguments()
    
    # Listar modelos si se solicita
    if args.list_models:
        list_available_models()
        return
    
    # Validar configuración
    config.validate()
    
    # Determinar modelo a usar
    model_name = args.model if args.model else config.get_model_name_for_db()
    
    # Determinar modo de ejecución
    if args.backtest:
        logger.info(f"Iniciando backtesting")
        
        # Usar fechas de argumentos o de config
        start_date = args.start or config.TRAIN_START
        end_date = args.end or config.TRAIN_END
        pair = args.pair or config.TRADING_PAIRS[0]
        
        logger.info(f"Modelo: {model_name}")
        logger.info(f"Período: {start_date} → {end_date}")
        logger.info(f"Par: {pair}")
        
        engine = BacktestEngine(
            pair=pair,
            start_date=start_date,
            end_date=end_date,
            model_name=model_name,
            trade_mode=config.TRADE_MODE
        )
        results = engine.run()
        
        logger.info("Backtesting completado")
        logger.info(f"Retorno: {results.get('total_return', 0):+.2f}%")
        logger.info(f"Win Rate: {results.get('win_rate', 0):.1f}%")
        logger.info(f"Trades: {results.get('total_trades', 0)}")
    else:
        logger.info("Iniciando trading en LIVE")
        logger.info(f"Modelo: {model_name}")
        bot = TradingBot(model_name=model_name)
        bot.run_live()


if __name__ == "__main__":
    main()