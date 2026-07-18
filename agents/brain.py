"""
agents/brain.py - Prompt completo con todos los indicadores
"""

import json
import re
import time
import sqlite3
import os
import sys
from datetime import datetime
from loguru import logger
import config
from agents.llm_adapter import LLMAdapter
from db.client import client as db

import argostranslate.package
import argostranslate.translate

from colorama import Fore, Style, init
init(autoreset=True)

from_code = "en"
to_code = "es"

# Descarga e instala el paquete de idioma (solo la primera vez)
argostranslate.package.update_package_index()
available_packages = argostranslate.package.get_available_packages()
package_to_install = next(
    filter(lambda x: x.from_code == from_code and x.to_code == to_code, available_packages)
)
argostranslate.package.install_from_path(package_to_install.download())

# Traducir
installed_languages = argostranslate.translate.get_installed_languages()
from_lang = list(filter(lambda x: x.code == from_code, installed_languages))[0]
to_lang = list(filter(lambda x: x.code == to_code, installed_languages))[0]
translation = from_lang.get_translation(to_lang)

class TradingBrain:
    def __init__(self, model_name: str = None):
        self.llm = LLMAdapter(model_name=model_name, use_ollamafree=False)
        self.model_name = self.llm.model_name
        self.db_path = config.get_model_db_path(self.model_name.replace(":", "_").replace("/", "_"))
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self._init_database()
        logger.info(f"Brain inicializado | Modelo: {self.model_name}")

    def _init_database(self):
        db.init_model_db(self.model_name)
        # conn = sqlite3.connect(str(self.db_path))
        # c = conn.cursor()
        # c.execute('''CREATE TABLE IF NOT EXISTS decisions (
            # id INTEGER PRIMARY KEY AUTOINCREMENT,
            # timestamp TEXT NOT NULL,
            # pair TEXT,
            # direction TEXT,
            # confidence INTEGER,
            # hypothesis TEXT,
            # source TEXT
        # )''')
        # c.execute('''CREATE TABLE IF NOT EXISTS trades (
            # id INTEGER PRIMARY KEY AUTOINCREMENT,
            # timestamp TEXT NOT NULL,
            # pair TEXT NOT NULL,
            # direction TEXT NOT NULL,
            # entry_price REAL,
            # exit_price REAL,
            # quantity REAL,
            # pnl_pct REAL,
            # confidence INTEGER,
            # outcome TEXT,
            # hypothesis TEXT,
            # session_id TEXT
        # )''')
        # conn.commit()
        # conn.close()

    def _build_prompt(self, snapshot: dict, ind: dict) -> str:
        pair = snapshot.get("pair", "Unknown")
        price = snapshot.get("current_price", 0)
        open_pos = snapshot.get("open_position")
        pnl_pct = snapshot.get("pnl_pct")
        #open_pnl = ind.get('open_position_pnl', 0)

        # === TODOS LOS INDICADORES ===
        rsi = ind.get('rsi', 50)
        macd_hist = ind.get('macd_histogram', 0)
        bb_pos = ind.get('bb_position_pct', 50)
        vol_ratio = ind.get('volume_ratio', 1.0)
        vol_trend = ind.get('volume_trend', 'NORMAL')
        atr_pct = ind.get('atr_pct', 1.0)
        regime = ind.get('market_regime', 'neutral')
        trend_str = ind.get('trend_strength', 'WEAK')
        ema50 = ind.get('ema50', 0)
        ema200 = ind.get('ema200', 0)
        price_vs_ema50 = ind.get('price_vs_ema50', 0)
        price_vs_ema200 = ind.get("price_vs_ema200", 0)
        dist_high = ind.get('distance_24h_high', 0)
        dist_low = ind.get('distance_24h_low', 0)
        obv_trend = ind.get('obv_trend', 'FLAT')
        adx = ind.get('adx', 20)
        trade_mode = getattr(config, 'TRADE_MODE', 'spot').lower()
        #open_sec = ""
        #for pos in open_pos[:]:
        
        #open_sec = f"\nPOSICIÓN ABIERTA → {open_pos.get('direction')} | PnL actual: {open_pos.get('pnl_pct')}%" if open_pos is not None else None
        
        open_sec = ""
        if open_pos is not None:
            open_sec = f"""
                POSICIÓN ABIERTA ACTUAL:
                - Dirección: {open_pos.get('direction')}
                - Precio de entrada: ${open_pos.get('entry_price', 0):.4f}
                - PnL actual: {open_pos.get('pnl_pct', 0):+.2f}%
                ¡Esta es información CRÍTICA!"""
        else:
            open_sec = "\n(No hay posición abierta actualmente)"

        prompt = f"""You are a disciplined and profitable crypto trader operating in **{trade_mode}**.

            CURRENT MARKET:
            Pair: {pair} | Current Price: ${price:,.4f}{open_sec}

            TECHNICAL INDICATORS:
            • RSI(14): {rsi:.1f}
            • MACD Histogram: {macd_hist:.4f}
            • Bollinger Bands Position: {bb_pos:.1f}%
            • Volume: {vol_ratio:.2f}x [{vol_trend}]
            • ATR: {atr_pct:.2f}%
            • ADX: {adx:.1f} ({trend_str})
            • Price vs EMA50: {price_vs_ema50:+.2f}%
            • 24h High/Low Distance: {dist_high:+.2f}% / {dist_low:+.2f}%
            • OBV Trend: {obv_trend}
            • Regime: {regime.upper()}

            
            CRITICAL RULES FOR OPEN POSITIONS:
            - If you have an open BUY: Prioritize closing (SELL) when you have profit or momentum is fading.
            - If you have an open SELL: Prioritize closing (BUY) when you have profit or conditions reverse.
            - Take profits regularly.
            - Use StopLoss and TakeProfit.
            - Only hold losing positions if there is strong reversal signal. Otherwise cut losses.
            - Be decisive with open positions.

            YOUR DECISION:
            - BUY = Open new long (only if no open position or you closed previous)
            - SELL = Open new short OR close current BUY
            - HOLD = Do nothing (default when no clear edge)
            
            CONTRADICTION AWARENESS:
            - If your hypothesis mentions "correction", "drop", "fall" → DO NOT recommend BUY
            - If your hypothesis mentions "rebound", "rally", "rise" → DO NOT recommend SELL
            - Ensure your direction matches your reasoning logic

            YOUR DECISION:
            - BUY = Open new long (only if no open position or you closed previous)
            - SELL = Open new short OR close current BUY
            - HOLD = Do nothing (default when no clear edge)

            **IMPORTANTE:**
            - Respond only in English.
            - Respond **ONLY** with valid JSON.
            - Never include "JSON Response Example:" in the output.
            - Do not add text before or after the JSON.
            - Do not use markdown, explanations, ```json tags, or output examples.
            - Output ONLY valid JSON: {{"direction": "BUY|SELL|HOLD", "confidence": 0-100, "hypothesis": "short explanation"}}
            - DO NOT include ticker, date, signal, decision objects in json responce. ONLY the 3 fields above.
            - Send only ONE decision, NOT multiple examples.
            Think step by step. Especially evaluate the open position first if it exists.
            **WARNING:** If you output multiple JSON examples instead of ONE decision, the system will fail.
            """
       
        return prompt

    # El resto del código (clean, analyze, record_outcome) se mantiene igual
    # def _clean_json_response(self, raw: str) -> str:
        # if not raw:
            # return '{"direction":"HOLD","confidence":50,"hypothesis":"Empty response"}'

        # # Eliminar todo lo que no sea JSON
        # raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL | re.IGNORECASE)
        # raw = re.sub(r'```json|```', '', raw, flags=re.IGNORECASE)
        # raw = re.sub(r'^\s*[\w\s:]+:\s*', '', raw, flags=re.MULTILINE)  # Quitar líneas como "Dirección:"

        # # Buscar el primer JSON válido
        # match = re.search(r'\{.*\}', raw, re.DOTALL)
        # if match:
            # cleaned = match.group(0)
            # # Limpiar comillas mal formadas
            # cleaned = re.sub(r'(\w+):', r'"\1":', cleaned)  # Asegurar comillas en keys
            # return cleaned.strip()

        # # Fallback seguro
        # return '{"direction":"HOLD","confidence":50,"hypothesis":"Parse error - invalid JSON"}'
        
    # def _clean_json_response(self, raw_text: str) -> str:
        # """
        # Limpia la respuesta de Ollama para extraer SOLO EL PRIMER JSON válido.
        # CORREGIDO: Maneja múltiples JSON, think tags, claves sin comillas, etc.
        # """
        # if not raw_text or not isinstance(raw_text, str):
            # return '{"direction":"HOLD","confidence":50,"hypothesis":"Empty response"}'
        
        # cleaned = raw_text
        
        # # ── 1. ELIMINAR TAGS DE RAZONAMIENTO ──
        # cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
        
        # # ── 2. ELIMINAR MARKDOWN CODE BLOCKS ──
        # cleaned = re.sub(r'```json\s*', '', cleaned, flags=re.IGNORECASE)
        # cleaned = re.sub(r'```\s*', '', cleaned, flags=re.IGNORECASE)
        
        # # ── 3. ELIMINAR PREFIJOS COMO "Dirección:", "Response:", etc. ──
        # cleaned = re.sub(r'^\s*[\w\sáéíóúñ:]+\s*:\s*', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
        
        # # ── 4. ENCONTRAR EL PRIMER JSON COMPLETO (depth counting) ──
        # json_objects = []
        # depth = 0
        # start_idx = None
        # in_string = False
        # escape_next = False
        
        # for i, char in enumerate(cleaned):
            # if escape_next:
                # escape_next = False
                # continue
            
            # if char == '\\' and in_string:
                # escape_next = True
                # continue
            
            # if char == '"' and not escape_next:
                # in_string = not in_string
                # continue
            
            # if not in_string:
                # if char == '{':
                    # if depth == 0:
                        # start_idx = i
                    # depth += 1
                # elif char == '}':
                    # depth -= 1
                    # if depth == 0 and start_idx is not None:
                        # json_objects.append(cleaned[start_idx:i+1])
                        # break  #Solo tomamos el PRIMERO
        
        # if json_objects:
            # cleaned = json_objects[0]
        # else:
            # # Fallback: regex simple
            # match = re.search(r'\{[^{}]*\}', cleaned, re.DOTALL)
            # if match:
                # cleaned = match.group(0)
            # else:
                # return '{"direction":"HOLD","confidence":50,"hypothesis":"Parse error - no JSON found"}'
        
        # # ── 5. CORREGIR CLAVES SIN COMILLAS ──
        # cleaned = re.sub(r'(?<=[{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'"\1":', cleaned)
        
        # # reemplazar ' por " solo en claves
        # cleaned = re.sub(r'(?<=: )\'([^\']*)\'', r'"\1"', cleaned)
        
        # # ── 6. CONVERTIR COMILLAS SIMPLES A DOBLES ──
        # cleaned = cleaned.replace("'", '"')
        
        # # ── 7. ELIMINAR CARACTERES NO IMPRIMIBLES ──
        # cleaned = ''.join(char for char in cleaned if ord(char) >= 32 or char in '\n\r\t')
        
        # # ── 8. BALANCEAR BRACES SI ES NECESARIO ──
        # open_braces = cleaned.count('{')
        # close_braces = cleaned.count('}')
        
        # if open_braces > close_braces:
            # cleaned += '}' * (open_braces - close_braces)
        # elif close_braces > open_braces:
            # cleaned = '{' * (close_braces - open_braces) + cleaned
        
        # # ── 9. VALIDAR QUE SEA JSON VÁLIDO ──
        # try:
            # json.loads(cleaned)  # Solo para validar
        # except json.JSONDecodeError as e:
            # logger.warning(f"JSON aún inválido después de limpieza: {e}")
            # logger.warning(f"   Cleaned text: {cleaned[:200]}")
            # return '{"direction":"HOLD","confidence":50,"hypothesis":"JSON parse error after cleanup"}'
        
        # return cleaned.strip()
        
    def _clean_json_response(self, raw_text: str) -> str:
        """
        Limpia la respuesta de Ollama para extraer JSON válido.
        CORREGIDO: Maneja apóstrofes en valores sin romper el JSON.
        """
        if not raw_text or not isinstance(raw_text, str):
            return '{"direction":"HOLD","confidence":50,"hypothesis":"Empty response"}'
        
        cleaned = raw_text.strip()
        
        # ── 1. ELIMINAR MARKDOWN Y TAGS ──
        cleaned = re.sub(r'```json\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'```\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\<think\>.*?\</think\>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
        
        # ── 2. ENCONTRAR PRIMER JSON CON DEPTH COUNTING ──
        depth = 0
        start_idx = None
        in_string = False
        escape_next = False
        
        for i, char in enumerate(cleaned):
            if escape_next:
                escape_next = False
                continue
            if char == '\\' and in_string:
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if not in_string:
                if char == '{':
                    if depth == 0:
                        start_idx = i
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0 and start_idx is not None:
                        cleaned = cleaned[start_idx:i+1]
                        break
        
        if not cleaned.startswith('{'):
            return '{"direction":"HOLD","confidence":50,"hypothesis":"Parse error"}'
        
        # ── 3. CORREGIR CLAVES SIN COMILLAS (SOLO CLAVES, NO VALORES) ──
        # Patrón: { o , seguido de palabra sin comillas seguida de :
        cleaned = re.sub(r'([{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', cleaned)
        
        # ── 4. ELIMINAR CARACTERES NO IMPRIMIBLES ──
        cleaned = ''.join(char for char in cleaned if ord(char) >= 32 or char in '\n\r\t')
        
        # ── 5. BALANCEAR BRACES ──
        open_b = cleaned.count('{')
        close_b = cleaned.count('}')
        if open_b > close_b:
            cleaned += '}' * (open_b - close_b)
        elif close_b > open_b:
            cleaned = '{' * (close_b - open_b) + cleaned
        
        # ── 6. NO CONVERTIR COMILLAS SIMPLES A DOBLES (rompe apóstrofes) ──
        # En su lugar, intentar parsear tal cual está
        
        # ── 7. VALIDAR Y RETORNAR ──
        try:
            json.loads(cleaned)  # Solo validar
            return cleaned.strip()
        except json.JSONDecodeError:
            # Fallback: retornar JSON seguro
            return '{"direction":"HOLD","confidence":50,"hypothesis":"JSON parse error - check hypothesis for apostrophes"}'
    
    def analyze(self, snapshot: dict, source: str = "backtest", show_responce: bool = False) -> dict:
        #try:
        COLOR = Fore.WHITE
        ind = snapshot.get("indicators_1h", {})
        prompt = self._build_prompt(snapshot, ind)

        raw_response = self.llm.chat_completion(
            # En LLMAdapter o donde se configura el modelo
        messages=[
            {"role": "system", "content": "You are a trading expert. Respond with ONE JSON object only. NO EXAMPLES. Respond ONLY in English."},
            {"role": "user", "content": prompt},
        ],
            temperature=0, #0.32,
            max_tokens=700
        )

        if show_responce: print(f'raw_response: {raw_response}')
        cleaned = self._clean_json_response(raw_response)
        if show_responce: print(f'cleaned: {cleaned}')
        reasoning = json.loads(cleaned)
        decision_id = self._save_decision(snapshot, reasoning, source)
        reasoning["_decision_id"] = decision_id
        print("direction=", reasoning['direction'], type(reasoning['direction']))
        if reasoning['direction'] == "BUY":
            COLOR = Fore.GREEN
        if reasoning['direction'] == "SELL":
            COLOR = Fore.YELLOW
        if reasoning['direction'] == "HOLD":
            COLOR = Fore.BLUE
        
        logger.info(f"Vela: {snapshot.get("vela_actual")} | Precio: ${snapshot.get("current_price")} | {COLOR}{reasoning.get('direction')} {Fore.CYAN}| Conf: {Fore.WHITE}{reasoning.get('confidence')}%{Fore.CYAN} | {translation.translate(reasoning.get('hypothesis'))}{Fore.RESET}")

        return reasoning

        #except Exception as e:
            #logger.error(f"Error en analyze: {e}")
            #return {"direction": "HOLD", "confidence": 50, "hypothesis": "Error", "_decision_id": None}

    def _save_decision(self, snapshot: dict, reasoning: dict, source: str, next_candle_change: float = None):
        try:
            ind = snapshot.get("indicators_1h", {})
            
            indicators_snapshot = {
                "rsi": ind.get('rsi'),
                "macd_histogram": ind.get('macd_histogram'),
                "bb_position_pct": ind.get('bb_position_pct'),
                "volume_ratio": ind.get('volume_ratio'),
                "volume_trend": ind.get('volume_trend'),
                "atr_pct": ind.get('atr_pct'),
                "adx": ind.get('adx'),
                "price_vs_ema50": ind.get('price_vs_ema50'),
                "distance_24h_high": ind.get('distance_24h_high'),
                "distance_24h_low": ind.get('distance_24h_low'),
                "obv_trend": ind.get('obv_trend'),
                "market_regime": ind.get('market_regime'),
                "current_price": snapshot.get("current_price")
            }

            indicators_json = json.dumps(indicators_snapshot, default=str)

            conn = sqlite3.connect(str(self.db_path))
            c = conn.cursor()
            c.execute('''INSERT INTO decisions 
                (timestamp, pair, direction, confidence, hypothesis, 
                 indicators_snapshot, next_candle_change, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (
                datetime.now().isoformat(),
                snapshot.get("pair"),
                reasoning.get("direction"),
                reasoning.get("confidence"),
                reasoning.get("hypothesis"),
                indicators_json,
                next_candle_change,
                source
            ))
            decision_id = c.lastrowid
            conn.commit()
            conn.close()
            return decision_id

        except Exception as e:
            logger.error(f"Error guardando decisión: {e}")
            return None
            
    def record_outcome(self, decision_id: int, outcome_data: dict):
        if not decision_id:
            logger.warning("record_outcome llamado sin decision_id")
            return
        try:
            conn = sqlite3.connect(str(self.db_path))
            c = conn.cursor()
            c.execute('''INSERT INTO trades 
                (timestamp, pair, direction, entry_price, exit_price, quantity, 
                 pnl_pct, confidence, outcome, hypothesis, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
                datetime.now().isoformat(),
                outcome_data.get('pair', 'BNBUSDT'),
                outcome_data.get('direction'),
                outcome_data.get('entry_price'),
                outcome_data.get('exit_price'),
                outcome_data.get('quantity'),
                outcome_data.get('pnl'),
                outcome_data.get('confidence'),
                "WIN" if outcome_data.get('pnl', 0) > 0 else "LOSS",
                outcome_data.get('hypothesis', ''),
                outcome_data.get('session_id')
            ))
            conn.commit()
            conn.close()
            logger.info(f"Trade guardado | PnL: {outcome_data.get('pnl',0):+.2f}%")
        except Exception as e:
            logger.error(f"Error guardando trade: {e}")


if __name__ == "__main__":
    brain = TradingBrain()
    print("Brain cargado con todos los indicadores en el prompt")