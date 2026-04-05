"""
risk/manager.py — Risk Awareness + Decision Gate.
CORREGIDO: Respeta AUTO_EXIT_ENABLED
"""
from loguru import logger
from dataclasses import dataclass, field
from typing import Optional
import config
from db import client as db

@dataclass
class TradeOrder:
    pair: str
    side: str
    usdt_amount: float
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    confidence: float
    reasoning: dict
    approved: bool = True
    reject_reason: str = ""
    close_position_qty: float = 0.0
    auto_exit_enabled: bool = False # NUEVO    
    @property
    def quantity(self) -> float:
        return self.usdt_amount / self.entry_price if self.entry_price > 0 else 0.0

class RiskManager:
    MIN_ORDER_USDT = 5.5

    def evaluate(
        self,
        direction: str,
        confidence: float,
        snapshot: dict,
        reasoning: dict,
    ) -> Optional[TradeOrder]:
        try:
            current_price = snapshot.get("current_price", 0)
            if current_price <= 0:
                logger.error("Precio inválido")
                return None
            
            usdt_amount = config.TRADE_AMOUNT_USDT
            pair = snapshot.get("pair", "")
            
            # === TP/SL SOLO SI AUTO_EXIT_ENABLED = FALSE ===
            use_tp_sl = config.USE_TP_SL and not config.AUTO_EXIT_ENABLED
            
            logger.info(f"  Monto: ${usdt_amount:.2f} | TP/SL: {'ON' if use_tp_sl else 'OFF (IA decide)'}")
            
            order = TradeOrder(
                pair=pair,
                side=direction,
                usdt_amount=usdt_amount,
                entry_price=current_price,
                confidence=confidence,
                reasoning=reasoning,
                auto_exit_enabled=config.AUTO_EXIT_ENABLED # NUEVO            
            )
            
            if use_tp_sl:
                if direction == "BUY":
                    order.take_profit_price = current_price * (1 + config.TAKE_PROFIT_PCT)
                    order.stop_loss_price = current_price * (1 - config.STOP_LOSS_PCT)
                else:
                    order.take_profit_price = current_price * (1 - config.TAKE_PROFIT_PCT)
                    order.stop_loss_price = current_price * (1 + config.STOP_LOSS_PCT)
                
                logger.info(f"  TP: ${order.take_profit_price:.4f} | SL: ${order.stop_loss_price:.4f}")
            else:
                order.take_profit_price = None
                order.stop_loss_price = None
            logger.info(f"Auto Exit: IA gestionará el cierre")            
            return order
        
        except Exception as e:
            logger.error(f"Error en risk evaluation: {e}")
            return None