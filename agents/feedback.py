"""
agents/feedback.py — Step 10: Feedback Loop.
VERSIÓN MEJORADA 2026: Outcome recording unificado + mejor soporte para futures y auto_exit
"""
from binance.client import Client as BinanceClient
from loguru import logger
import config
from db import client as db


class FeedbackLoop:
    def __init__(self, brain=None):
        """Inicializa con referencia al cerebro para registrar outcomes"""
        self.brain = brain
        self.binance = BinanceClient(
            config.BINANCE_API_KEY, 
            config.BINANCE_SECRET_KEY, 
            requests_params={"timeout": 10}
        )
        if config.BINANCE_TESTNET:
            self.binance.API_URL = "https://testnet.binance.vision/api"

    def set_brain(self, brain):
        """Permite establecer el cerebro después de la inicialización"""
        self.brain = brain

    def check_and_update_open_trades(self):
        """
        Revisa todas las posiciones abiertas y actualiza outcomes cuando se cierran.
        Compatible con AUTO_EXIT_ENABLED y nuevo RiskManager.
        """
        for pair in config.TRADING_PAIRS:
            open_trades = db.get_open_trades(pair)
            if not open_trades:
                continue

            for trade in open_trades:
                if trade.get("is_dry_run"):
                    self._check_dry_run_trade(trade)
                elif config.TRADE_MODE == "futures":
                    self._check_futures_trade(trade)
                else:
                    self._check_real_trade(trade)

    def _check_dry_run_trade(self, trade: dict):
        """Simula TP/SL en modo dry-run usando precio actual"""
        pair = trade.get("pair")
        try:
            ticker = self.binance.get_symbol_ticker(symbol=pair)
            current_price = float(ticker["price"])
            
            entry = float(trade.get("entry_price", 0))
            side = trade.get("side")
            pnl_pct = (current_price - entry) / entry * 100 if side == "BUY" else (entry - current_price) / entry * 100

            logger.info(f"[{pair}] DRY-RUN monitoring: Price=${current_price:,.4f} | PnL={pnl_pct:+.2f}%")

            self._evaluate_trade(trade, current_price)
        except Exception as e:
            logger.error(f"[{pair}] Dry-run price fetch failed: {e}")

    def _check_real_trade(self, trade: dict):
        """Verifica órdenes reales en spot"""
        pair = trade.get("pair")
        order_id = trade.get("binance_order_id")
        
        if not order_id or "FAILED" in str(order_id):
            return self._check_dry_run_trade(trade)

        try:
            open_orders = self.binance.get_open_orders(symbol=pair)
            if not open_orders:
                # Orden cerrada → buscar última operación
                trades = self.binance.get_my_trades(symbol=pair, limit=5)
                if trades:
                    last_trade = trades[0]
                    exit_price = float(last_trade["price"])
                    self._evaluate_trade(trade, exit_price)
                else:
                    self._check_dry_run_trade(trade)
            else:
                logger.debug(f"[{pair}] Trade aún tiene órdenes abiertas")
        except Exception as e:
            logger.error(f"[{pair}] Real trade check failed: {e}")
            self._check_dry_run_trade(trade)

    def _check_futures_trade(self, trade: dict):
        """Verifica posiciones en futures"""
        pair = trade.get("pair")
        try:
            positions = self.binance.futures_position_information(symbol=pair)
            for pos in positions:
                pos_amt = float(pos.get("positionAmt", 0))
                mark_price = float(pos.get("markPrice", 0))
                entry = float(trade.get("entry_price", 0))

                if abs(pos_amt) < 0.0001:  # Posición cerrada
                    exit_price = mark_price
                    # Intentar obtener precio real de trades recientes
                    try:
                        recent_trades = self.binance.futures_account_trades(symbol=pair, limit=10)
                        for t in sorted(recent_trades, key=lambda x: x.get("time", 0), reverse=True):
                            if float(t.get("realizedPnl", 0)) != 0:
                                exit_price = float(t["price"])
                                break
                    except:
                        pass
                    
                    self._evaluate_trade(trade, exit_price)
                else:
                    # Posición aún abierta - solo log
                    unrealized_pnl = float(pos.get("unRealizedProfit", 0))
                    logger.info(f"[{pair}] Futures OPEN | Mark=${mark_price:,.4f} | Unrealized PnL=${unrealized_pnl:+.2f}")
        except Exception as e:
            logger.error(f"[{pair}] Futures check failed: {e}")
            self._check_dry_run_trade(trade)

    def _evaluate_trade(self, trade: dict, current_price: float):
        """Evalúa si se alcanzó TP/SL o se cerró la posición y registra outcome"""
        side = trade.get("side")
        entry = float(trade.get("entry_price", 0))
        trade_id = trade.get("id")
        pair = trade.get("pair")
        reasoning_id = trade.get("reasoning_id")

        if not entry:
            return

        # Calcular PnL
        raw_pnl = (current_price - entry) / entry * 100 if side == "BUY" else (entry - current_price) / entry * 100
        lev = config.FUTURES_LEVERAGE if config.TRADE_MODE == "futures" else 1
        pnl_pct = raw_pnl * lev

        outcome = {
            "exit_price": current_price,
            "pnl_pct": round(pnl_pct, 4),
            "result": "WIN" if pnl_pct > 0 else "LOSS",
            "prediction_correct": pnl_pct > 0,
        }

        db.update_trade_outcome(trade_id, outcome)

        label = "TAKE PROFIT" if pnl_pct > 0 else "STOP LOSS"
        logger.info(f"[{pair}] {label} HIT | Entry={entry:.4f} → Exit={current_price:.4f} | PnL={pnl_pct:+.2f}%")

        # Registrar outcome en el modelo para aprendizaje continuo
        if reasoning_id and self.brain:
            try:
                self.brain.record_outcome(int(reasoning_id), {
                    'pair': pair,
                    'direction': side,
                    'confidence': trade.get("confidence", 0),
                    'entry_price': entry,
                    'exit_price': current_price,
                    'actual_move': 'UP' if current_price > entry else 'DOWN',
                    'actual_move_pct': (current_price - entry) / entry * 100,
                    'was_correct': pnl_pct > 0,
                    'pnl': pnl_pct
                })
                logger.debug(f"Outcome registrado en modelo para reasoning_id={reasoning_id}")
            except Exception as e:
                logger.warning(f"Error registrando outcome en modelo: {e}")

    def reconcile_stale_trades(self):
        """Reconciliar trades abiertos vs realidad en Binance al iniciar"""
        logger.info("Reconciliando trades stale...")
        stale_found = 0
        for pair in config.TRADING_PAIRS:
            open_trades = db.get_open_trades(pair)
            if not open_trades:
                continue

            try:
                if config.TRADE_MODE == "futures":
                    positions = self.binance.futures_position_information(symbol=pair)
                    live_qty = sum(abs(float(p.get("positionAmt", 0))) for p in positions)
                    if live_qty == 0:
                        for trade in open_trades:
                            if not trade.get("is_dry_run"):
                                logger.warning(f"[{pair}] Stale trade {trade['id']} - cerrando")
                                exit_price = self._get_last_exit_price(pair)
                                self._evaluate_trade(trade, exit_price)
                                stale_found += 1
            except Exception as e:
                logger.error(f"[{pair}] Reconcile failed: {e}")

        if stale_found:
            logger.info(f"Reconciliados {stale_found} trades stale")
        else:
            logger.info("No se encontraron trades stale")


    def _get_last_exit_price(self, pair: str) -> float:
        """Obtiene último precio de salida (fallback)"""
        try:
            ticker = self.binance.get_symbol_ticker(symbol=pair) if config.TRADE_MODE == "spot" else \
                     self.binance.futures_symbol_ticker(symbol=pair)
            return float(ticker["price"])
        except:
            return 0.0


# Función helper
def create_feedback_loop(brain=None):
    loop = FeedbackLoop(brain)
    return loop


if __name__ == "__main__":
    loop = create_feedback_loop()
    print("FeedbackLoop cargado correctamente - Versión mejorada")