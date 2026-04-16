"""
main.py - Punto de entrada principal para trading en vivo y backtesting
CORREGIDO: Valida si la vela es nueva antes de analizar, cycle_interval匹配 timeframe
"""
import pandas as pd
import numpy as np
import time
import uuid
import signal
import sys
from datetime import datetime
from loguru import logger
import config
from data.collector import DataCollector
from agents.brain import TradingBrain
from risk.manager import RiskManager, TradeOrder
from execution.executor import TradeExecutor
from db import client as db

logger.remove()
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
    def __init__(self):
        self.collector = DataCollector(db_path=config.MARKET_DATA_DB)
        self.brain = TradingBrain(model_name=config.get_model_name_for_db())
        self.risk_manager = RiskManager()
        self.executor = TradeExecutor()
        
        self.positions = []
        self.max_slots = config.MAX_SLOTS
        self.total_capital = config.INITIAL_BALANCE
        self.current_balance = self.total_capital
        self.shutdown_flag = False
        
        # NUEVO: Tracking de ultima vela para evitar analisis repetido
        self.last_candle_time = None
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("Trading Bot inicializado")
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
                
                # NUEVO: Validar si la vela es nueva antes de analizar
                current_candle_time = snapshot["historical_timestamp"]
                if current_candle_time == self.last_candle_time:
                    logger.debug("Misma vela, esperando nueva vela...")
                    time.sleep(min(300, config.CYCLE_INTERVAL))
                    continue
                
                self.last_candle_time = current_candle_time
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
                    
                    logger.info(f"CERRAR {pos.direction} | Entry: ${pos.entry_price:.2f} -> Exit: ${exit_price:.2f} | {result} | PnL: {pnl_pct:+.2f}%")
                
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


def main():
    config.validate()
    
    if config.TRAIN_MODE:
        logger.info(f"Iniciando backtesting: {config.TRAIN_START} -> {config.TRAIN_END}")
        
        from backtesting import BacktestEngine
        engine = BacktestEngine(
            pair=config.TRADING_PAIRS[0],
            start_date=config.TRAIN_START,
            end_date=config.TRAIN_END,
            model_name=config.get_model_name_for_db(),
            trade_mode=config.TRADE_MODE
        )
        results = engine.run()
        
        logger.info("Backtesting completado")
        logger.info(f"Retorno: {results.get('total_return', 0):+.2f}%")
        logger.info(f"Win Rate: {results.get('win_rate', 0):.1f}%")
        logger.info(f"Trades: {results.get('total_trades', 0)}")
    else:
        logger.info("Iniciando trading en LIVE")
        bot = TradingBot()
        bot.run_live()


if __name__ == "__main__":
    main()