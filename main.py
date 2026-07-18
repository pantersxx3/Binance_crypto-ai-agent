"""
main.py - Versión Final con Resume funcional + Guardado de progreso
"""

import argparse
import time
import uuid
import signal
import sys
from datetime import datetime
from pathlib import Path
from loguru import logger

import config
from data.collector import DataCollector
from agents.brain import TradingBrain
from risk.manager import RiskManager
from execution.executor import TradeExecutor
from db.client import client as db

from colorama import Fore, Style, init
init(autoreset=True)

logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <cyan>{message}</cyan>",    level=config.LOG_LEVEL, colorize=True)
logger.add(config.LOGS_DIR / "trading_{time:YYYY-MM-DD}.log", level=config.LOG_LEVEL, rotation="1 day")

showresponce = True

class Position:
    def __init__(self, trade_id: str, direction: str, entry_price: float, quantity: float, confidence: int, decision_id: int, entry_time):
        self.trade_id = trade_id
        self.direction = direction
        self.entry_price = entry_price
        self.quantity = quantity
        self.confidence = confidence
        self.decision_id = decision_id
        self.entry_time = entry_time


class BacktestEngine:
    def __init__(self, pair: str, start_date: str, end_date: str, model_name: str = None):
        self.model_name = model_name or config.get_model_name_for_db()
        self.brain = TradingBrain(model_name=self.model_name)
        self.risk_manager = RiskManager()
        self.executor = TradeExecutor()
        self.collector = DataCollector()
        
        self.pair = pair
        self.start_date = start_date
        self.end_date = end_date
        self.session_id = f"BACKTEST_{uuid.uuid4().hex[:8]}"

        self.positions = []
        self.current_balance = config.INITIAL_BALANCE
        self.wins = 0
        self.losses = 0
        self.Buys = 0
        self.Sells = 0
        self.last_action_vela = 0
        self.current_vela = 50
        self.shutdown_flag = False
        self.usable_slots = config.MAX_SLOTS

        db.init_model_db(self.model_name)

        # Cargar progreso
        self._load_progress()

        logger.info(f"BacktestEngine listo | Modelo: {self.model_name} | Vela inicial: {self.current_vela}")

    def _load_progress(self):
        progress = db.get_progress(self.model_name, self.session_id)
        if progress:
            self.current_vela = progress.get('last_vela', 50)
            self.current_balance = progress.get('balance', config.INITIAL_BALANCE)
            self.wins = progress.get('wins', 0)
            self.losses = progress.get('losses', 0)
            logger.info(f"Reanudando desde vela {self.current_vela}")

    def run(self):
        count_hold = 0
        logger.info(f"Iniciando BACKTESTING | {self.start_date} → {self.end_date}")

        df = self.collector.get_historical_klines(self.pair, "1h", start_date=self.start_date, end_date=self.end_date)
        if df.empty:
            logger.error("No se cargaron datos")
            return

        logger.info(f"Cargadas {len(df)} velas | Iniciando desde vela {self.current_vela}\n")

        for i in range(self.current_vela, len(df) - 1):
            if self.shutdown_flag:
                logger.info(f"Pausado en vela {i}. Guardando progreso...")
                db.save_progress(self.model_name, self.session_id, i, self.current_balance, self.wins, self.losses)
                break

            current_row = df.iloc[i]
            #open_pos = self.positions[0] if self.positions else None
            #pos = self.positions[0] if self.positions else None
            exit_price = current_row['close']

            indicators = self.collector.compute_indicators(
                df.iloc[max(0, i-100):i+1], "1h" #, open_position=open_pos_dict
            )
            
            positions = []
            if not self.positions:
                dummy_pos = Position(
                    trade_id=0, 
                    direction=None, 
                    entry_price=0.0, 
                    quantity=0, 
                    confidence=0, 
                    decision_id=0, 
                    entry_time=None
                )
                positions.append(dummy_pos)
            else:
                positions = self.positions[:]
                
            for pos in positions:
                pnl_pct = round((((exit_price - pos.entry_price) / pos.entry_price) * 100), 2) if not pos.trade_id == 0 else 0
                open_pos_dict = {"direction": pos.direction, "entry_price": pos.entry_price, "pnl_pct": pnl_pct} if not pos.trade_id == 0 else None          
                snapshot = {
                    "pair": self.pair,
                    "current_price": current_row['close'],
                    "usdt_balance": self.current_balance,
                    "indicators_1h": indicators,
                    "open_position": open_pos_dict,
                    "vela_actual": i
                }

                analysis = self.brain.analyze(snapshot, source="backtest", show_responce=showresponce)
                direction = analysis.get("direction", "HOLD")
                confidence = analysis.get("confidence", 0)
                
                # === Calcular resultado a corto plazo (siguiente vela) ===
                next_candle_change = None
                if i + 1 < len(df):
                    next_price = df.iloc[i + 1]['close']
                    next_candle_change = (next_price - current_row['close']) / current_row['close'] * 100

                # Guardar decisión con resultado short-term
                decision_id = self.brain._save_decision(snapshot, analysis, "backtest", next_candle_change)
                analysis["_decision_id"] = decision_id
                # if i - self.last_action_vela < 6 and self.positions:
                    # self.current_vela = i + 1
                    # continue

                # === APERTURA ===
                #print(f"Debug if BUY?: {direction} {confidence} {config.MIN_CONFIDENCE} {self.usable_slots}")
                # if direction in "HOLD":
                    # count_hold += 1
                    # if count_hold == 50:
                        # print("El modelo es midioso y no quiere operar, saliendo...")
                        # sys.exit()
                if direction == "BUY" and confidence >= config.MIN_CONFIDENCE and self.usable_slots > 0:
                    self.usable_slots = self.usable_slots - 1 
                    qty = config.TRADE_AMOUNT_USDT / current_row['close']
                    trade_id = str(uuid.uuid4())
                    new_pos = Position(
                        trade_id=trade_id,
                        direction=direction,
                        entry_price=exit_price,
                        quantity=qty,
                        confidence=confidence,
                        decision_id=None,
                        entry_time=current_row['timestamp']
                    )
                    self.positions.append(new_pos)
                    
                    db.log_trade(self.model_name, {
                        "trade_id": trade_id,
                        'pair': self.pair,
                        'direction': direction,
                        'entry_price': exit_price,
                        'exit_price': 0,
                        'quantity': qty,
                        'pnl_pct': 0,
                        'confidence': confidence,
                        'outcome': "",
                        'session_id': self.session_id
                    })
                    
                    logger.info(f"{Fore.GREEN}Vela: [{i}] Comprando @ {confidence}%{Fore.RESET} | {Fore.GREEN}Precio: ${current_row['close']:.2f}{Fore.RESET}")
                    
                    self.last_action_vela = i
                    self.Buys += 1

                # === CIERRE ===
                for pos in self.positions[:]:
                    #print(pos.__dict__)
                #if self.positions:
                    #current_dir = self.positions[0].direction
                    #if direction in "SELL" and direction != current_dir and confidence >= config.MIN_CONFIDENCE:
                    #print(pos.__dict__) 
                    if pos.direction == "BUY" and direction == "SELL" and confidence >= config.MIN_CONFIDENCE:
                        #pnl_pct = -pnl_pct
                        #pnl_pct = (((exit_price - pos.entry_price) / pos.entry_price) * 100)
                        #logger.info(f"[VELA {i}] Cerrando {pos.direction} → IA recomienda {direction} | PnL: {pnl_pct:+.2f}%")
                        #trade = db.get_trade_by_id(self.model_name, trade_id="")
                        db.log_trade(self.model_name, {
                            'trade_id': pos.trade_id,
                            'pair': self.pair,
                            'direction': "SELL",
                            'entry_price': pos.entry_price,
                            'exit_price': exit_price,
                            'quantity': pos.quantity * exit_price,
                            'pnl_pct': pnl_pct,
                            'confidence': pos.confidence,
                            'outcome': "WIN" if pnl_pct > 0 else "LOSS",
                            'session_id': self.session_id
                        })

                        self.current_balance += config.TRADE_AMOUNT_USDT * (pnl_pct / 100)
                        if pnl_pct > 0:
                            self.wins += 1
                        else:
                            self.losses += 1

                        #self.positions.clear()
                        self.positions.remove(pos)
                        self.usable_slots += 1
                        self.last_action_vela = i
                        logger.info(f"{Fore.YELLOW}Vela: [{i}] Vendiendo @ {confidence}%{Fore.RESET} | {Fore.YELLOW}Precio: ${current_row['close']:.2f}{Fore.RESET} | {Fore.YELLOW}PnL: {pnl_pct:+.2f}%{Fore.RESET}")
                        self.Sells += 1
                        if self.current_balance < config.TRADE_AMOUNT_USDT:
                             logger.info(f"Monto insuficiente para una segunda operacion {self.current_balance} USDT, saliendo...")
                             sys.exit()
            self.current_vela = i + 1
            # Guardar progreso cada 30 velas
            if i % 30 == 0:
                db.save_progress(self.model_name, self.session_id, i, self.current_balance, self.wins, self.losses)
            #if i % 50 == 0:
                win_rate = (self.wins / (self.wins + self.losses) * 100) if (self.wins + self.losses) > 0 else 0
                logger.info("-"*100)
                logger.info(f"{Fore.WHITE}Progreso: {i}/{len(df)} velas | Balance: ${self.current_balance:.2f} | Win Rate: {win_rate:.1f}%{Fore.RESET}")
                #logger.info(f"{Fore.WHITE}{Fore.RESET}")
                logger.info("-"*100)
            logger.info(f"INFORME DEL BOOT: COMPRAS: {self.Buys} | VENTAS: {self.Sells} | OPERACIONES GANADORAS: {self.wins} | OPERACIONES PERDEDORAS: {self.losses} | BALANCE: {self.current_balance}")
        # Guardado final
        db.save_progress(self.model_name, self.session_id, self.current_vela, self.current_balance, self.wins, self.losses)

        logger.info("BACKTEST FINALIZADO")


def main():
    # logger.info("Iniciando BACKTESTING...")
    # engine = BacktestEngine(
        # pair=config.TRADING_PAIRS[0],
        # start_date=config.TRAIN_START,
        # end_date=config.TRAIN_END,
        # model_name=config.get_model_name_for_db()
    # )
    # engine.run()
    parser = argparse.ArgumentParser(description="Crypto AI Trading Bot")
    parser.add_argument("--mode", choices=["backtest", "live", "test"], default="backtest", help="Modo de ejecución")
    parser.add_argument("--pair", type=str, default=config.TRADING_PAIRS[0], help="Par a operar (ej: BNBUSDT)")
    parser.add_argument("--limit", type=int, default=0, help="Limitar número de velas para pruebas rápidas")
    parser.add_argument("--model", type=str, default=None, help="Modelo específico a usar")
    parser.add_argument("--min-confidence", type=int, default=None, help="Sobrescribir MIN_CONFIDENCE")
    parser.add_argument("--show-responce", action='store_true', default=False, help="Muestra las respuestas del modelo")
    args = parser.parse_args()

    logger.info(f"Iniciando en modo: {args.mode.upper()} | Par: {args.pair}")
    
    if args.show_responce: showresponce = args.show_responce

    if args.min_confidence:
        config.MIN_CONFIDENCE = args.min_confidence

    if args.mode == "backtest":
        engine = BacktestEngine(
            pair=args.pair,
            start_date=config.TRAIN_START,
            end_date=config.TRAIN_END,
            model_name=args.model
        )
        engine.run()
    else:
        logger.warning("Modo live/test aún no implementado completamente.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nPrograma interrumpido por el usuario.")
        sys.exit()