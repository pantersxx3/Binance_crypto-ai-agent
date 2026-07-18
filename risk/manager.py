"""
risk/manager.py — Risk Awareness + Decision Gate
VERSIÓN MEJORADA 2026: Flexible según exit_strategy + sizing inteligente
"""
from loguru import logger
from dataclasses import dataclass
from typing import Optional
import config


@dataclass
class TradeOrder:
    """Orden de trading - Campos ordenados correctamente para dataclass"""
    pair: str
    side: str
    usdt_amount: float
    entry_price: float
    confidence: float                    # Obligatorio - sin valor por defecto
    reasoning: dict
    
    # Campos opcionales (con valores por defecto)
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    approved: bool = True
    reject_reason: str = ""
    auto_exit_enabled: bool = False

    @property
    def quantity(self) -> float:
        return self.usdt_amount / self.entry_price if self.entry_price > 0 else 0.0


class RiskManager:
    """Gestor de riesgo inteligente y flexible"""
    MIN_ORDER_USDT = 5.5

    def evaluate(
        self,
        direction: str,
        confidence: float,
        snapshot: dict,
        reasoning: dict,
    ) -> TradeOrder:
        try:
            current_price = snapshot.get("current_price", 0)
            if current_price <= 0:
                logger.error("Precio inválido en RiskManager")
                return None

            indicators = snapshot.get("indicators_1h", {})
            atr_pct = indicators.get("atr_pct", 1.0)
            pair = snapshot.get("pair", "")

            # === POSITION SIZING INTELIGENTE ===
            base_amount = config.TRADE_AMOUNT_USDT
            confidence_factor = max(0.65, confidence / 100.0)

            # Ajuste suave por volatilidad
            volatility_factor = 1.0
            if atr_pct > 4.0:
                volatility_factor = 0.72
                logger.info(f"[{pair}] Alta volatilidad (ATR {atr_pct:.1f}%) → tamaño reducido")
            elif atr_pct > 2.8:
                volatility_factor = 0.88

            size_factor = confidence_factor * volatility_factor
            usdt_amount = max(self.MIN_ORDER_USDT, round(base_amount * size_factor, 2))

            # === CREACIÓN DE LA ORDEN ===
            order = TradeOrder(
                pair=pair,
                side=direction,
                usdt_amount=usdt_amount,
                entry_price=current_price,
                confidence=confidence,
                reasoning=reasoning,
                auto_exit_enabled=config.AUTO_EXIT_ENABLED
            )

            # === LÓGICA DE EXIT STRATEGY ===
            exit_strategy = getattr(config, 'EXIT_STRATEGY', 'ia_decide').lower()

            if exit_strategy == "fixed_tp_sl":
                # Modo tradicional: TP y SL fijos
                if direction == "BUY":
                    order.take_profit_price = round(current_price * (1 + config.TAKE_PROFIT_PCT), 8)
                    order.stop_loss_price = round(current_price * (1 - config.STOP_LOSS_PCT), 8)
                else:
                    order.take_profit_price = round(current_price * (1 - config.TAKE_PROFIT_PCT), 8)
                    order.stop_loss_price = round(current_price * (1 + config.STOP_LOSS_PCT), 8)

            elif exit_strategy == "hybrid":
                # Modo híbrido: protección lejana + IA puede cerrar antes
                if direction == "BUY":
                    order.stop_loss_price = round(current_price * (1 - config.PROTECTION_SL_PCT), 8)
                    order.take_profit_price = round(current_price * (1 + config.PROTECTION_TP_PCT), 8)
                else:
                    order.stop_loss_price = round(current_price * (1 + config.PROTECTION_SL_PCT), 8)
                    order.take_profit_price = round(current_price * (1 - config.PROTECTION_TP_PCT), 8)

            # En modo "ia_decide" → NO se ponen TP/SL fijos (la IA decide todo)

            logger.info(
                f"RiskManager → {direction} ${usdt_amount:.2f} USDT "
                f"(conf={confidence:.0f}%, ATR={atr_pct:.1f}%, strategy={exit_strategy})"
            )

            return order

        except Exception as e:
            logger.error(f"Error en RiskManager.evaluate: {e}")
            return None


# Prueba rápida
if __name__ == "__main__":
    risk = RiskManager()
    print("RiskManager cargado correctamente - Versión flexible según exit_strategy")