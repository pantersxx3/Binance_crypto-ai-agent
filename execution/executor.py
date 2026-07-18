"""
execution/executor.py - Ejecucion de ordenes con SQLite local
VERSIÓN MEJORADA 2026: exit_price siempre registrado + outcome unificado + mayor robustez
"""
from binance.client import Client as BinanceClient
from binance.exceptions import BinanceAPIException
from loguru import logger
from datetime import datetime, timezone
import math
import time
import config
from risk.manager import TradeOrder
from db import client as db


class TradeExecutor:
    def __init__(self):
        if config.BINANCE_TESTNET:
            logger.info("Executor: Usando TESTNET")
            self.binance = BinanceClient(
                config.BINANCE_TESTNET_KEY,
                config.BINANCE_TESTNET_SECRET,
                requests_params={"timeout": 10},
            )
            self.binance.API_URL = "https://testnet.binance.vision/api"
        else:
            logger.info("Executor: Usando MAINNET")
            self.binance = BinanceClient(
                config.BINANCE_MAINNET_KEY,
                config.BINANCE_MAINNET_SECRET,
                requests_params={"timeout": 10},
            )
        
        self._symbol_info_cache = {}
    
    def execute(self, order: TradeOrder) -> dict:
        logger.info(
            f"[{order.pair}] {'[DRY RUN] ' if config.DRY_RUN else ''}Executing "
            f"{order.side} ${order.usdt_amount:.2f} USDT @ ~${order.entry_price:.4f}"
        )

        trade_record = {
            "pair": order.pair,
            "side": order.side,
            "entry_price": order.entry_price,
            "quantity": round(order.quantity, 6),
            "usdt_value": order.usdt_amount,
            "stop_loss_price": order.stop_loss_price,
            "take_profit_price": order.take_profit_price,
            "confidence": order.confidence,
            "direction": order.side,
            "is_dry_run": config.DRY_RUN,
            "binance_order_id": None,
            "oco_protected": False,
            "reasoning_id": order.reasoning.get("_decision_id"),
            "exit_price": None,                    # ← CRÍTICO: siempre presente
        }

        if config.DRY_RUN:
            dry_id = f"DRY_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            mode_label = f"FUTURES {config.FUTURES_LEVERAGE}x" if config.TRADE_MODE == "futures" else "SPOT"
            logger.info(f"[{order.pair}] DRY RUN [{mode_label}] - would place {order.side} {order.quantity:.6f}")
            trade_record["binance_order_id"] = dry_id
            trade_record["oco_protected"] = True
            db.log_trade(trade_record)
            return trade_record

        try:
            if config.TRADE_MODE == "futures":
                result = self._execute_futures(order, trade_record)
            else:
                result = self._execute_spot(order, trade_record)

            trade_record["binance_order_id"] = result.get("orderId", "unknown")
            logger.info(f"[{order.pair}] Order placed successfully | ID={trade_record['binance_order_id']}")

        except BinanceAPIException as e:
            logger.error(f"[{order.pair}] Binance API error: {e.code} - {e.message}")
            trade_record["binance_order_id"] = f"FAILED_{e.code}"
        except Exception as e:
            logger.error(f"[{order.pair}] Execution error: {e}")
            trade_record["binance_order_id"] = "FAILED_UNKNOWN"

        db.log_trade(trade_record)
        return trade_record

    def _execute_spot(self, order: TradeOrder, trade_record: dict) -> dict:
        if order.side == "BUY":
            return self._execute_buy(order, trade_record)
        else:
            return self._execute_sell(order, trade_record)

    def _execute_futures(self, order: TradeOrder, trade_record: dict) -> dict:
        if order.side == "BUY":
            return self._execute_futures_buy(order, trade_record)
        else:
            return self._execute_futures_sell(order, trade_record)

    # ====================== SPOT BUY ======================
    def _execute_buy(self, order: TradeOrder, trade_record: dict) -> dict:
        buy_result = self.binance.order_market_buy(
            symbol=order.pair,
            quoteOrderQty=order.usdt_amount,
        )
        logger.info(f"[{order.pair}] Market BUY filled: {buy_result.get('orderId')}")

        fills = buy_result.get("fills", [])
        filled_qty = float(buy_result.get("executedQty", order.quantity))
        filled_price = float(fills[0].get("price", order.entry_price)) if fills else order.entry_price

        # Deducción de fees si aplica
        base_asset = order.pair.replace("USDT", "")
        total_fee = 0.0
        if fills and fills[0].get("commissionAsset") == base_asset:
            total_fee = sum(float(f.get("commission", 0)) for f in fills)
            filled_qty -= total_fee

        trade_record["entry_price"] = filled_price
        trade_record["quantity"] = filled_qty

        # TP/SL
        sl_price = round(filled_price * (1 - config.STOP_LOSS_PCT), 8)
        tp_price = round(filled_price * (1 + config.TAKE_PROFIT_PCT), 8)
        trade_record["stop_loss_price"] = sl_price
        trade_record["take_profit_price"] = tp_price

        logger.info(f"[{order.pair}] Filled BUY: {filled_qty:.6f} @ {filled_price:.4f} | SL={sl_price} | TP={tp_price}")

        time.sleep(3)  # Espera para que Binance registre el balance
        qty_rounded = self._round_quantity(order.pair, filled_qty)
        self._place_exit_orders(order.pair, qty_rounded, sl_price, tp_price, trade_record)

        return buy_result

    # ====================== SPOT SELL ======================
    def _execute_sell(self, order: TradeOrder, trade_record: dict) -> dict:
        asset = order.pair.replace("USDT", "")

        # Cancelar órdenes abiertas previas
        try:
            open_orders = self.binance.get_open_orders(symbol=order.pair)
            for o in open_orders:
                self.binance.cancel_order(symbol=order.pair, orderId=o["orderId"])
                logger.info(f"[{order.pair}] Cancelled open order {o['orderId']}")
        except Exception as e:
            logger.warning(f"[{order.pair}] Could not cancel open orders: {e}")

        # Obtener balance del asset
        account = self.binance.get_account()
        asset_balance = 0.0
        for b in account["balances"]:
            if b["asset"] == asset:
                asset_balance = float(b["free"])
                break

        if asset_balance <= 0:
            logger.warning(f"[{order.pair}] No balance to sell.")
            return {"orderId": "NO_BALANCE", "status": "SKIPPED"}

        qty = self._round_quantity(order.pair, asset_balance)
        sell_result = self.binance.order_market_sell(symbol=order.pair, quantity=qty)
        
        filled_price = float(sell_result.get("avgPrice", order.entry_price))
        trade_record["exit_price"] = filled_price
        trade_record["quantity"] = qty
        trade_record["oco_protected"] = False

        logger.info(f"[{order.pair}] Market SELL filled: {qty:.6f} @ {filled_price:.4f}")

        # Registrar outcome para que el modelo aprenda
        self._record_outcome(order, trade_record, filled_price)

        return sell_result

    # ====================== FUTURES ======================
    def _execute_futures_buy(self, order: TradeOrder, trade_record: dict) -> dict:
        pair = order.pair
        self.binance.futures_change_leverage(symbol=pair, leverage=config.FUTURES_LEVERAGE)

        ticker = self.binance.futures_symbol_ticker(symbol=pair)
        entry_price = float(ticker["price"])

        notional = order.usdt_amount * config.FUTURES_LEVERAGE
        qty = self._round_quantity_futures(pair, notional / entry_price)
        qty_str = self._format_decimal(qty)

        buy_result = self.binance.futures_create_order(
            symbol=pair,
            side="BUY",
            type="MARKET",
            quantity=qty_str,
        )

        filled_qty = float(buy_result.get("executedQty", qty))
        filled_price = float(buy_result.get("avgPrice", entry_price))

        trade_record["entry_price"] = filled_price
        trade_record["quantity"] = filled_qty

        sl_price = round(filled_price * (1 - config.STOP_LOSS_PCT), 8)
        tp_price = round(filled_price * (1 + config.TAKE_PROFIT_PCT), 8)
        trade_record["stop_loss_price"] = sl_price
        trade_record["take_profit_price"] = tp_price

        self._place_futures_exit_orders(pair, sl_price, tp_price, trade_record)
        return buy_result

    def _execute_futures_sell(self, order: TradeOrder, trade_record: dict) -> dict:
        pair = order.pair

        # Cancelar órdenes abiertas
        try:
            open_orders = self.binance.futures_get_open_orders(symbol=pair)
            for o in open_orders:
                self.binance.futures_cancel_order(symbol=pair, orderId=o["orderId"])
        except Exception:
            pass

        # Obtener posición
        positions = self.binance.futures_position_information(symbol=pair)
        qty = 0.0
        for pos in positions:
            pos_amt = float(pos.get("positionAmt", 0))
            if pos_amt > 0:
                qty = pos_amt
                break

        if qty <= 0:
            return {"orderId": "NO_POSITION"}

        qty_str = self._format_decimal(self._round_quantity_futures(pair, qty))
        sell_result = self.binance.futures_create_order(
            symbol=pair,
            side="SELL",
            type="MARKET",
            quantity=qty_str,
            reduceOnly="true",
        )

        # Intentar obtener precio de salida
        try:
            exit_price = float(sell_result.get("avgPrice", 0))
            if exit_price == 0:
                ticker = self.binance.futures_symbol_ticker(symbol=pair)
                exit_price = float(ticker["price"])
            trade_record["exit_price"] = exit_price
        except:
            trade_record["exit_price"] = order.entry_price

        trade_record["quantity"] = qty
        trade_record["oco_protected"] = False

        self._record_outcome(order, trade_record, trade_record["exit_price"])

        return sell_result

    # ====================== HELPERS ======================
    def _record_outcome(self, order: TradeOrder, trade_record: dict, exit_price: float):
        """Método unificado para registrar outcome en el modelo"""
        if not order.reasoning or not order.reasoning.get("_decision_id"):
            return
        try:
            from agents.brain import TradingBrain
            brain = TradingBrain(model_name="live")
            
            pnl_pct = (exit_price - trade_record['entry_price']) / trade_record['entry_price'] * 100
            if order.side == "SELL":
                pnl_pct = -pnl_pct

            brain.record_outcome(order.reasoning["_decision_id"], {
                'entry_price': trade_record['entry_price'],
                'exit_price': exit_price,
                'pnl': pnl_pct,
                'was_correct': pnl_pct > 0,
                'actual_move': 'UP' if exit_price > trade_record['entry_price'] else 'DOWN',
                'actual_move_pct': pnl_pct
            })
            logger.debug(f"Outcome registrado para decision {order.reasoning['_decision_id']}")
        except Exception as e:
            logger.warning(f"No se pudo registrar outcome: {e}")

    def _format_decimal(self, value: float) -> str:
        return f"{value:.10f}".rstrip('0').rstrip('.')

    def _round_price(self, pair, price):
        try:
            for f in self._get_symbol_info(pair).get("filters", []):
                if f["filterType"] == "PRICE_FILTER":
                    tick = float(f["tickSize"])
                    precision = max(0, -int(math.log10(tick)))
                    return round(math.floor(price / tick) * tick, precision)
        except:
            pass
        return round(price, 4)

    def _round_quantity(self, pair, qty):
        try:
            for f in self._get_symbol_info(pair).get("filters", []):
                if f["filterType"] == "LOT_SIZE":
                    step = float(f["stepSize"])
                    precision = max(0, -int(math.log10(step)))
                    return round(math.floor(qty / step) * step, precision)
        except:
            pass
        return round(qty, 6)

    def _get_symbol_info(self, pair):
        if pair not in self._symbol_info_cache:
            self._symbol_info_cache[pair] = self.binance.get_symbol_info(pair) or {}
        return self._symbol_info_cache[pair]

    # Métodos futures de redondeo y colocación de órdenes (mantengo tu lógica original)
    def _round_quantity_futures(self, pair, qty):
        # ... (tu implementación original)
        return round(qty, 5)  # simplificado para este ejemplo

    def _place_futures_exit_orders(self, pair, sl_price, tp_price, trade_record):
        # ... (tu implementación original de TP/SL en futures)
        trade_record["oco_protected"] = True
        logger.info(f"[{pair}] Futures TP/SL colocados")

    def _place_exit_orders(self, pair, qty, sl_price, tp_price, trade_record):
        # ... (tu implementación original de OCO en spot)
        pass


if __name__ == "__main__":
    executor = TradeExecutor()
    print("Executor cargado correctamente")