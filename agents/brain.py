"""
agents/brain.py - Trading Brain con SQLite local unificado
CORREGIDO: Limpieza robusta de JSON, outcome recording para live trading
"""
import json
import re
import time
import sqlite3
import os
from datetime import datetime
from pathlib import Path
from openai import OpenAI
from loguru import logger
import config

class TradingBrain:
    def __init__(self, model_name: str = None):
        self.client = OpenAI(
            base_url=config.LLM_BASE_URL,
            api_key=config.LLM_API_KEY,
            timeout=600.0
        )
        self.model_name = model_name or "default"
        self.db_path = config.get_model_db_path(self.model_name)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.model = config.LLM_MODEL
        
        self._init_database()
        
        logger.info(f"Brain inicializado | Modelo: {self.model_name} | DB: {self.db_path}")
    
    def _init_database(self):
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    historical_timestamp TEXT,
                    source TEXT NOT NULL,
                    pair TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    confidence INTEGER NOT NULL,
                    hypothesis TEXT,
                    response_time REAL,
                    rsi REAL,
                    price REAL,
                    market_regime TEXT,
                    trend_strength TEXT,
                    macd_cross TEXT,
                    raw_response TEXT,
                    error TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    entry_price REAL,
                    exit_price REAL,
                    pnl REAL,
                    was_correct BOOLEAN,
                    actual_move TEXT,
                    actual_move_pct REAL,
                    FOREIGN KEY (decision_id) REFERENCES decisions (id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS model_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    updated_at TEXT NOT NULL,
                    total_decisions INTEGER DEFAULT 0,
                    total_trades INTEGER DEFAULT 0,
                    correct_trades INTEGER DEFAULT 0,
                    win_rate REAL DEFAULT 0,
                    total_pnl REAL DEFAULT 0,
                    avg_confidence REAL DEFAULT 0
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.debug(f"Base de datos inicializada: {self.db_path}")
            
        except Exception as e:
            logger.error(f"Error inicializando base de datos: {e}")
            raise

    def _clean_json_response(self, raw_text: str) -> str:
        """Limpia la respuesta del LLM para extraer JSON valido"""
        if not raw_text or not isinstance(raw_text, str):
            return "{}"
        
        cleaned = re.sub(r'```json\s*', '', raw_text, flags=re.IGNORECASE)
        cleaned = re.sub(r'```\s*', '', cleaned)
        
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(0)
        
        cleaned = ''.join(char for char in cleaned if ord(char) >= 32 or char in '\n\r\t')
        
        if cleaned.count('{') > cleaned.count('}'):
            cleaned += '}' * (cleaned.count('{') - cleaned.count('}'))
        
        cleaned = re.sub(r',\s*}', '}', cleaned)
        cleaned = re.sub(r',\s*]', ']', cleaned)
        
        try:
            json.loads(cleaned)
            return cleaned.strip()
        except json.JSONDecodeError as e:
            logger.warning(f"JSON invalido despues de limpiar: {e}")
            logger.debug(f"   JSON problematico: {cleaned[:500]}")
            
            fallback = self._extract_json_fields(cleaned)
            if fallback:
                logger.info("   Recuperado con fallback regex")
                return fallback
            return "{}"

    def _extract_json_fields(self, json_str: str) -> str:
        """Ultimo recurso: Extraer campos esenciales con regex"""
        fields = {}
        
        match = re.search(r'"direction"\s*:\s*"(BUY|SELL|HOLD)"', json_str, re.IGNORECASE)
        if match:
            fields['direction'] = match.group(1).upper()
        
        match = re.search(r'"confidence"\s*:\s*(\d+)', json_str)
        if match:
            fields['confidence'] = int(match.group(1))
        
        match = re.search(r'"market_regime"\s*:\s*"(bullish|bearish|neutral)"', json_str, re.IGNORECASE)
        if match:
            fields['market_regime'] = match.group(1).lower()
        
        match = re.search(r'"risk_level"\s*:\s*"(low|medium|high)"', json_str, re.IGNORECASE)
        if match:
            fields['risk_level'] = match.group(1).lower()
        
        match = re.search(r'"hypothesis"\s*:\s*"([^"]*(?:"[^",}][^"]*)*)"', json_str, re.DOTALL)
        if match:
            fields['hypothesis'] = match.group(1).replace('"', "'")
        else:
            match = re.search(r'"hypothesis"\s*:\s*"(.+?)(?="(?:\s*,\s*"[a-z_]+"|[\s}]))', json_str, re.DOTALL)
            if match:
                fields['hypothesis'] = match.group(1).replace('"', "'")[:500]
        
        match = re.search(r'"suggested_stop_loss_pct"\s*:\s*([\d.]+)', json_str)
        if match:
            fields['suggested_stop_loss_pct'] = float(match.group(1))
        
        match = re.search(r'"suggested_take_profit_pct"\s*:\s*([\d.]+)', json_str)
        if match:
            fields['suggested_take_profit_pct'] = float(match.group(1))
        
        if not fields:
            return None
        
        return json.dumps(fields, ensure_ascii=False)

    def _build_prompt(self, snapshot: dict) -> str:
        pair = snapshot.get("pair", "Unknown")
        price = snapshot.get("current_price", 0)
        ind_1h = snapshot.get("indicators_1h", {})
        
        trade_mode = snapshot.get("trade_mode", config.TRADE_MODE)
        capital_per_slot = snapshot.get("capital_per_slot", float(config.TRADE_AMOUNT_USDT))
        
        rsi = ind_1h.get('rsi', 50)
        regime = ind_1h.get('market_regime', 'neutral')
        trend_strength = ind_1h.get('trend_strength', 'weak')
        macd_cross = ind_1h.get('macd_cross', 'none')
        
        if rsi < 30:
            rsi_zone = "OVERSOLD"
        elif rsi > 70:
            rsi_zone = "OVERBOUGHT"
        else:
            rsi_zone = "NEUTRAL"
        
        prompt = f"""You are a crypto trader. Analyze and decide: BUY, SELL, or HOLD.

MARKET DATA
Pair: {pair}
Price: ${price:,.2f}
Trading Mode: {trade_mode.upper()}
Capital per Operation: ${capital_per_slot:.2f}

TECHNICAL ANALYSIS
RSI: {rsi} ({rsi_zone})
Market Regime: {regime}
Trend Strength: {trend_strength}
MACD Cross: {macd_cross}

RULES
1. BUY when: RSI < 40 and regime is bullish
2. SELL when: RSI > 60 and regime is bearish (FUTURES only)
3. HOLD otherwise
4. In SPOT mode: Only BUY to open, SELL to close
5. In FUTURES mode: Can BUY or SELL to open

CRITICAL JSON RULES
- Respond with valid JSON ONLY
- No markdown, no extra text
- All strings must use double quotes
- No trailing commas

OUTPUT FORMAT (JSON only):
{{"direction": "BUY/SELL/HOLD", "confidence": 0-100, "market_regime": "bullish/bearish/neutral", "risk_level": "low/medium/high", "hypothesis": "reason"}}
"""
        return prompt

    def _fallback_decision(self, snapshot: dict) -> dict:
        ind_1h = snapshot.get("indicators_1h", {})
        rsi = ind_1h.get('rsi', 50)
        regime = ind_1h.get('market_regime', 'neutral')
        trend_strength = ind_1h.get('trend_strength', 'weak')
        
        if rsi < 35 and regime == 'bullish':
            direction = "BUY"
            confidence = 55
            hypothesis = f"Fallback: RSI oversold ({rsi}) in bullish regime"
        elif rsi > 65 and regime == 'bearish':
            direction = "SELL"
            confidence = 55
            hypothesis = f"Fallback: RSI overbought ({rsi}) in bearish regime"
        elif rsi < 30:
            direction = "BUY"
            confidence = 50
            hypothesis = f"Fallback: RSI extremely oversold ({rsi})"
        elif rsi > 70:
            direction = "SELL"
            confidence = 50
            hypothesis = f"Fallback: RSI extremely overbought ({rsi})"
        else:
            direction = "HOLD"
            confidence = 40
            hypothesis = f"Fallback: Mixed signals (RSI={rsi}, regime={regime})"
        
        if trend_strength in ['strong', 'STRONG']:
            confidence = min(confidence + 10, 80)
        elif trend_strength in ['weak', 'WEAK']:
            confidence = max(confidence - 10, 30)
        
        return {
            "direction": direction,
            "confidence": confidence,
            "market_regime": regime,
            "risk_level": "medium",
            "hypothesis": hypothesis
        }

    def _log_decision(self, data: dict) -> int:
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO decisions (
                timestamp, historical_timestamp, source, pair, direction, confidence,
                hypothesis, response_time, rsi, price, market_regime, trend_strength,
                macd_cross, raw_response, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('timestamp', datetime.now().isoformat()),
            data.get('historical_timestamp'),
            data.get('source', 'live'),
            data.get('pair', ''),
            data.get('direction', ''),
            data.get('confidence', 0),
            data.get('hypothesis', '')[:2000],
            data.get('response_time', 0),
            data.get('rsi', 0),
            data.get('price', 0),
            data.get('market_regime', ''),
            data.get('trend_strength', ''),
            data.get('macd_cross', ''),
            data.get('raw_response', '')[:2000],
            data.get('error', '')[:2000]
        ))
        
        decision_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return decision_id

    def _log_outcome(self, decision_id: int, outcome: dict):
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO outcomes (
                decision_id, timestamp, entry_price, exit_price, pnl,
                was_correct, actual_move, actual_move_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            decision_id,
            datetime.now().isoformat(),
            outcome.get('entry_price', 0),
            outcome.get('exit_price', 0),
            outcome.get('pnl', 0),
            1 if outcome.get('was_correct') else 0,
            outcome.get('actual_move', ''),
            outcome.get('actual_move_pct', 0)
        ))
        
        conn.commit()
        conn.close()

    def _get_recent_decisions(self, pair: str, limit: int = 5) -> list:
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT direction, confidence, hypothesis, rsi, market_regime,
                   was_correct, pnl
            FROM decisions d
            LEFT JOIN outcomes o ON d.id = o.decision_id
            WHERE d.pair = ?
            ORDER BY d.timestamp DESC
            LIMIT ?
        ''', (pair, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return rows

    def analyze(self, snapshot: dict, source: str = "live") -> dict:
        pair = snapshot.get("pair", "Unknown")
        start_time = time.time()
        raw_response = ""
        
        try:
            rsi = snapshot.get("indicators_1h", {}).get('rsi', 50)
            price = snapshot.get("current_price", 0)
            regime = snapshot.get("indicators_1h", {}).get('market_regime', 'neutral')
            trend_strength = snapshot.get("indicators_1h", {}).get('trend_strength', 'weak')
            macd_cross = snapshot.get("indicators_1h", {}).get('macd_cross', 'none')
            
            recent = self._get_recent_decisions(pair, limit=3)
            feedback = ""
            if recent:
                feedback = "\n## Recent Learning:\n"
                for r in recent:
                    status = "WIN" if r[5] == 1 else "LOSS" if r[5] == 0 else "PENDING"
                    pnl_str = f"{r[6]:+.1f}%" if r[6] else "N/A"
                    feedback += f"- {r[0]} @ {r[1]}%: {status} | PnL: {pnl_str}\n"
            
            prompt = self._build_prompt(snapshot)
            if feedback:
                prompt += feedback
            
            historical_ts = snapshot.get("historical_timestamp")
            ts_display = historical_ts.strftime("%Y-%m-%d %H:%M") if historical_ts else datetime.now().strftime("%Y-%m-%d %H:%M")
            
            logger.info(f"[{pair}] Enviando a ({self.model})...")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a trading expert. Respond with valid JSON only. No markdown, no extra text."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=300,
            )
            
            raw_response = response.choices[0].message.content
            
            cleaned = self._clean_json_response(raw_response)
            
            if not cleaned or cleaned == "{}" or len(cleaned) < 10:
                logger.warning("JSON invalido, usando fallback")
                reasoning = self._fallback_decision(snapshot)
            else:
                try:
                    reasoning = json.loads(cleaned)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON decode error: {e}")
                    reasoning = self._fallback_decision(snapshot)
            
            reasoning.setdefault("direction", "HOLD")
            reasoning.setdefault("confidence", 0)
            reasoning.setdefault("market_regime", regime)
            reasoning.setdefault("risk_level", "medium")
            reasoning.setdefault("hypothesis", "No hypothesis")
            
            reasoning["confidence"] = max(0, min(100, int(reasoning.get("confidence", 0))))
            
            if reasoning["direction"] not in ["BUY", "SELL", "HOLD"]:
                reasoning["direction"] = "HOLD"
            
            elapsed = time.time() - start_time
            
            historical_ts = snapshot.get("historical_timestamp")
            if historical_ts is not None:
                if hasattr(historical_ts, 'isoformat'):
                    historical_ts_str = historical_ts.isoformat()
                else:
                    historical_ts_str = str(historical_ts)
            else:
                historical_ts_str = None
            
            decision_id = self._log_decision({
                'timestamp': datetime.now().isoformat(),
                'historical_timestamp': historical_ts_str,
                'source': source,
                'pair': pair,
                'direction': reasoning['direction'],
                'confidence': reasoning['confidence'],
                'hypothesis': reasoning['hypothesis'],
                'response_time': round(elapsed, 2),
                'rsi': rsi,
                'price': price,
                'market_regime': reasoning['market_regime'],
                'trend_strength': trend_strength,
                'macd_cross': macd_cross,
                'raw_response': raw_response,
                'error': ''
            })
            
            reasoning["_decision_id"] = decision_id
            
            logger.info(f"[{ts_display}] [{pair}] {reasoning['direction']} @ {reasoning['confidence']}% | {reasoning['hypothesis'][:200]}")
            
            return reasoning
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[{pair}] Error: {e}")
            
            fallback = self._fallback_decision(snapshot)
            
            historical_ts = snapshot.get("historical_timestamp")
            if historical_ts is not None:
                if hasattr(historical_ts, 'isoformat'):
                    historical_ts_str = historical_ts.isoformat()
                else:
                    historical_ts_str = str(historical_ts)
            else:
                historical_ts_str = None
            
            self._log_decision({
                'timestamp': datetime.now().isoformat(),
                'historical_timestamp': historical_ts_str,
                'source': source,
                'pair': pair,
                'direction': fallback['direction'],
                'confidence': fallback['confidence'],
                'hypothesis': fallback['hypothesis'],
                'response_time': round(elapsed, 2),
                'rsi': snapshot.get("indicators_1h", {}).get('rsi', 0),
                'price': snapshot.get("current_price", 0),
                'market_regime': fallback['market_regime'],
                'trend_strength': snapshot.get("indicators_1h", {}).get('trend_strength', ''),
                'macd_cross': snapshot.get("indicators_1h", {}).get('macd_cross', ''),
                'raw_response': raw_response,
                'error': str(e)[:1000]
            })
            
            return fallback

    def record_outcome(self, decision_id: int, outcome_data: dict):
        self._log_outcome(decision_id, outcome_data)
        self._update_model_stats()
        logger.info(f"Outcome registrado para decision {decision_id}")

    def _update_model_stats(self):
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total_decisions,
                COUNT(CASE WHEN o.id IS NOT NULL THEN 1 END) as total_trades,
                SUM(CASE WHEN o.was_correct = 1 THEN 1 ELSE 0 END) as correct,
                AVG(CASE WHEN o.was_correct = 1 THEN d.confidence ELSE NULL END) as avg_confidence_correct,
                AVG(CASE WHEN o.was_correct = 0 THEN d.confidence ELSE NULL END) as avg_confidence_wrong,
                SUM(o.pnl) as total_pnl
            FROM decisions d
            LEFT JOIN outcomes o ON d.id = o.decision_id
        ''')
        
        row = cursor.fetchone()
        total_decisions, total_trades, correct, avg_correct, avg_wrong, total_pnl = row
        
        win_rate = (correct / total_trades * 100) if total_trades > 0 else 0
        avg_confidence = ((avg_correct or 0) + (avg_wrong or 0)) / 2 if total_trades > 0 else 0
        
        cursor.execute('''
            INSERT OR REPLACE INTO model_stats (id, updated_at, total_decisions, total_trades,
                                                correct_trades, win_rate, total_pnl, avg_confidence)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), total_decisions, total_trades, correct, win_rate, total_pnl, avg_confidence))
        
        conn.commit()
        conn.close()

    def get_stats(self) -> dict:
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM model_stats WHERE id = 1')
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'total_decisions': row[2],
                'total_trades': row[3],
                'correct_trades': row[4],
                'win_rate': row[5],
                'total_pnl': row[6],
                'avg_confidence': row[7]
            }
        return {}