# """
# meta_analyzer.py - Análisis Conjetura por Conjetura (tu método)
# """
# import sys
# import json
# import sqlite3
# from pathlib import Path
# from datetime import datetime
# from agents.brain import TradingBrain

# class MetaAnalyzer:
    # def __init__(self, model_name: str):
        # self.model_name = model_name
        # self.brain = TradingBrain(model_name=model_name)
        # self.db_path = Path("trained_models") / f"{model_name.replace(':', '_').replace('/', '_')}.db"
    
    # def analyze_one_by_one(self, limit=100):
        # """Analiza conjetura por conjetura usando la siguiente como referencia"""
        # conn = sqlite3.connect(str(self.db_path))
        # conn.row_factory = sqlite3.Row
        # c = conn.cursor()
        
        # c.execute('''
            # SELECT id, timestamp, direction, confidence, hypothesis, 
                   # indicators_snapshot, next_candle_change
            # FROM decisions 
            # ORDER BY timestamp ASC 
            # LIMIT ?
        # ''', (limit,))
        
        # decisions = [dict(row) for row in c.fetchall()]
        # conn.close()

        # print(f"Analizando {len(decisions)} conjeturas una por una...\n")
        
        # for i in range(len(decisions) - 1):   # -1 porque necesitamos la siguiente
            # current = decisions[i]
            # next_one = decisions[i + 1]
            
            # try:
                # curr_ind = json.loads(current['indicators_snapshot'])
                # # rsi = curr_ind.get('rsi', 50)
                # # macd_hist = curr_ind.get('macd_histogram', 0)
                # # bb_pos = curr_ind.get('bb_position_pct', 50)
                # # vol_ratio = curr_ind.get('volume_ratio', 1.0)
                # # vol_trend = curr_ind.get('volume_trend', 'NORMAL')
                # # atr_pct = curr_ind.get('atr_pct', 1.0)
                # # adx = curr_ind.get('adx', 20)
                # # trend_str = curr_ind.get('trend_strength', 'WEAK')
                # # price_vs_ema50 = curr_ind.get('price_vs_ema50', 0)
                # # price_vs_ema200 = curr_ind.get('price_vs_ema200', 0)
                # # dist_high = curr_ind.get('distance_24h_high', 0)
                # # dist_low = curr_ind.get('distance_24h_low', 0)
                # # obv_trend = curr_ind.get('obv_trend', 'FLAT')
                # # regime = curr_ind.get('market_regime', 'neutral')
                # # indicadores_curr = f"""TECHNICAL INDICATORS:
                    # # RSI(14): {rsi:.1f}
                    # # MACD Histogram: {macd_hist:.4f}
                    # # BB Position: {bb_pos:.1f}%
                    # # Volume: {vol_ratio:.2f}x [{vol_trend}]
                    # # ATR: {atr_pct:.2f}%
                    # # ADX: {adx:.1f} ({trend_str})
                    # # Price vs EMA50: {price_vs_ema50:+.2f}%
                    # # Price vs EMA200: {price_vs_ema200:+.2f}%
                    # # 24h High/Low Distance: {dist_high:+.2f}% / {dist_low:+.2f}%
                    # # OBV Trend: {obv_trend}
                    # # Market Regime: {regime.upper()}"""
                    
                # next_ind = json.loads(next_one['indicators_snapshot'])
                # # rsi = next_ind.get('rsi', 50)
                # # macd_hist =  next_ind.get('macd_histogram', 0)
                # # bb_pos =  next_ind.get('bb_position_pct', 50)
                # # vol_ratio = next_ind.get('volume_ratio', 1.0)
                # # vol_trend = next_ind.get('volume_trend', 'NORMAL')
                # # atr_pct =  next_ind.get('atr_pct', 1.0)
                # # adx =  next_ind.get('adx', 20)
                # # trend_str =  next_ind.get('trend_strength', 'WEAK')
                # # price_vs_ema50 =  next_ind.get('price_vs_ema50', 0)
                # # price_vs_ema200 =  next_ind.get('price_vs_ema200', 0)
                # # dist_high =  next_ind.get('distance_24h_high', 0)
                # # dist_low =  next_ind.get('distance_24h_low', 0)
                # # obv_trend = curr_ind.get('obv_trend', 'FLAT')
                # # regime =  next_ind.get('market_regime', 'neutral')
                # # indicadores_next = f"""TECHNICAL INDICATORS:
                    # # RSI(14): {rsi:.1f}
                    # # MACD Histogram: {macd_hist:.4f}
                    # # BB Position: {bb_pos:.1f}%
                    # # Volume: {vol_ratio:.2f}x [{vol_trend}]
                    # # ATR: {atr_pct:.2f}%
                    # # ADX: {adx:.1f} ({trend_str})
                    # # Price vs EMA50: {price_vs_ema50:+.2f}%
                    # # Price vs EMA200: {price_vs_ema200:+.2f}%
                    # # 24h High/Low Distance: {dist_high:+.2f}% / {dist_low:+.2f}%
                    # # OBV Trend: {obv_trend}
                    # # Market Regime: {regime.upper()}"""
                
                # direction = current['direction']
                # price_curr = curr_ind.get("current_price")
                # price_next = next_ind.get("current_price")
                # change = ((price_next - price_curr) / price_curr) * 100 if price_curr else 0.0
                # #result = "↑ SUBIÓ" if change and change > 0 else "↓ BAJÓ" if change and change < 0 else "→ NEUTRO"
                
                
                
                # #print(f"Vela {current['timestamp'][11:16]} | {direction} (Conf {current['confidence']}) | Real: {result} {change:+.2f}%")
                # #print(f"Hypótesis original: {current['hypothesis']}...")
                
                # # prompt = f"""Analiza esta conjetura y mejórala usando la información de la siguiente vela:

                    # # **Vela Actual:**
                    # # - Dirección predicha: {direction}
                    # # - Confianza: {current['confidence']}%
                    # # - Hypothesis: {current['hypothesis']}
                    # # - Indicadores: {indicadores_curr}
                    
                    # # **Siguiente Vela (Resultado Real):**
                    # # indicadores: {indicadores_next}

                    # # ¿Fue correcta la conjetura? ¿Qué indicadores engañaron al modelo?
                    # # Genera una **nueva conjetura mejorada** más precisa para esta vela."""
                
                # # prompt = f"""Eres un entrenador crítico de trading IA. Tu tarea es mejorar o corregir la conjetura anterior.
                    # # **Vela Actual:**
                    # # - Dirección predicha: {direction}
                    # # - Confianza: {current['confidence']}%
                    # # - Hypothesis: {current['hypothesis']}
                    # # - Indicadores: {curr_ind}

                    # # **Siguiente Vela (Resultado Real):**
                    # # - Indicadores: {next_ind}
                    # # - Cambio real: {change:+.2f}%

                    # # **Instrucciones estrictas:**
                    # # - Si la conjetura fue mala, cámbiala (puede ser de BUY a HOLD o SELL).
                    # # - Sé brutalmente honesto con los errores.
                    # # - Explica claramente qué indicadores fueron mal interpretados.
                    # # - Genera una **nueva conjetura mejorada** mucho más precisa."""
                    
                # # prompt = f"""Eres un entrenador estricto y objetivo de trading IA. Tu tarea es analizar y corregir esta conjetura.

                    # # **Vela Actual:**
                    # # - Dirección predicha: {direction}
                    # # - Confianza: {current['confidence']}%
                    # # - Hypothesis original: {current['hypothesis']}

                    # # **Indicadores de la vela actual:**
                    # # {curr_ind}

                    # # **Siguiente Vela (Resultado Real):**
                    # # {next_ind}
                    # # Cambio real del precio: {change:+.2f}%

                    # # **Instrucciones estrictas:**
                    # # - Sé brutalmente honesto. Si la conjetura fue mala, dilo claramente.
                    # # - Indica si debería haber sido BUY, SELL o HOLD.
                    # # - Indica si debería cambiar el valor de confidence.
                    # # - Genera una **nueva conjetura mejorada** mucho más precisa y realista.
                    # # - No tengas miedo de bajar fuertemente la confianza o cambiar la dirección si fue un error o el confidence.

                    # # Nueva Conjetura Mejorada: DIRECCION, CONFIDENCE, HYPOTESIS"""
                # prompt = f"""Eres un entrenador estricto y brutalmente honesto de trading IA.
                    # **Vela Actual:**
                    # - Dirección predicha: {direction}
                    # - Confianza: {current['confidence']}%
                    # - Precio: {price_curr}
                    # - Hypothesis original: {current['hypothesis']}

                    # **Indicadores vela actual:**
                    # {curr_ind}

                    # **Siguiente Vela (Resultado Real):**
                    # -Precio Actual: {price_next}
                    # {next_ind}
                    # -Cambio real: {change:+.2f}%

                    # **Instrucciones estrictas:**
                    # - Sé brutalmente honesto. Si la conjetura fue mala, dilo claramente y corrígela.
                    # - Puedes cambiar completamente la dirección (BUY → HOLD, BUY → SELL, etc.).
                    # - Debes ajustar fuertemente la confianza si fue un error.
                    # - Genera una **nueva conjetura mejorada** mucho más precisa y realista a partir de los Resultados reales.

                    # **Formato obligatorio de respuesta en una sola linea debe contener:**
                    # ejemplo: DIRECCION, CONFIANZA%, NUEVA CONJETURA MEJORADA"""

                # improved = self.brain.llm.chat_completion(
                    # messages=[{"role": "user", "content": prompt}],
                    # temperature=0.22,
                    # max_tokens=1600
                # )
                # print(f"\n{'─' * 90}")
                # print(f'Original: {direction}, {current['confidence']}%, {current['hypothesis']}')
                # print(f"Respuesa: {improved.strip()}\n\n")

            # except Exception as e:
                # print(f"Error procesando vela: {e}")
                # exc_type, exc_obj, exc_tb = sys.exc_info()
                # print(f"Error on line {exc_tb.tb_lineno}: {e}")
                # continue

        # print(f"\nAnálisis granular completado ({len(decisions)-1} conjeturas procesadas).")
        
# if __name__ == "__main__":
    # analyzer = MetaAnalyzer("qwen2_5-7b-instruct-1m")
    # analyzer.analyze_one_by_one(limit=60)
    
"""
meta_analyzer.py - Análisis Conjetura por Conjetura + Guardado de Mejoras
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime
from agents.brain import TradingBrain


class MetaAnalyzer:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.brain = TradingBrain(model_name=model_name)
        self.db_path = Path("trained_models") / f"{model_name.replace(':', '_').replace('/', '_')}.db"

    def analyze_one_by_one(self, limit=100):
        updated_count = 0
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute('''
            SELECT id, timestamp, direction, confidence, hypothesis, 
                   indicators_snapshot, next_candle_change
            FROM decisions 
            ORDER BY timestamp ASC 
            LIMIT ?
        ''', (limit,))
        
        decisions = [dict(row) for row in c.fetchall()]
        conn.close()

        print(f"Analizando {len(decisions)} conjeturas una por una...\n")
        
        for i in range(len(decisions) - 1):
            current = decisions[i]
            next_one = decisions[i + 1]
            
            try:
                curr_ind = json.loads(current['indicators_snapshot'])
                next_ind = json.loads(next_one['indicators_snapshot'])
                
                price_curr = curr_ind.get("current_price")
                price_next = next_ind.get("current_price")
                change = ((price_next - price_curr) / price_curr * 100) if price_curr else 0.0

                direction = current['direction']

                prompt = f"""Eres un entrenador estricto y brutalmente honesto de trading IA.
                    **Vela Actual:**
                    - Dirección predicha: {direction}
                    - Confianza: {current['confidence']}%
                    - Precio: {price_curr}
                    - Hypothesis original: {current['hypothesis']}

                    **Indicadores vela actual:**
                    {curr_ind}

                    **Siguiente Vela (Resultado Real):**
                    -Precio Actual: {price_next}
                    {next_ind}
                    -Cambio real: {change:+.2f}%

                    **Instrucciones estrictas:**
                    - Sé brutalmente honesto. Si la conjetura fue mala, dilo claramente y corrígela.
                    - Puedes cambiar completamente la dirección (BUY → HOLD, BUY → SELL, etc.).
                    - Debes ajustar fuertemente la confianza si fue un error.
                    - Genera una **nueva conjetura mejorada** mucho más precisa y realista a partir de los Resultados reales.

                    **Formato obligatorio de respuesta en una sola linea debe contener:**
                    ejemplo: DIRECCION, CONFIANZA%, NUEVA CONJETURA MEJORADA"""

                improved = self.brain.llm.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.22,
                    max_tokens=1600
                )

                # Extraer la parte útil
                improved_text = improved.strip()

                print(f"\n{'─' * 190}")
                print(f"Original : {direction} {current['confidence']}% {current['hypothesis']}")
                print(f"Mejorada : {improved_text}")

                # === GUARDAR LA MEJORA ===
                self._replace_hypothesis(current['id'], improved_text)
                updated_count += 1

            except Exception as e:
                print(f"Error procesando: {e}")
                continue

        print(f"\nProceso terminado. Se actualizaron {updated_count} conjeturas.")

    def _replace_hypothesis(self, decision_id: int, new_hypothesis: str):
        """Reemplaza la hypothesis original por la mejorada"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            c = conn.cursor()
            c.execute("UPDATE decisions SET hypothesis = ?, improved_hypothesis = ? WHERE id = ?", 
                      (new_hypothesis, new_hypothesis, decision_id))
            conn.commit()
            conn.close()
            print(f"   → Actualizado ID {decision_id}")
        except Exception as e:
            print(f"   Error actualizando: {e}")

if __name__ == "__main__":
    analyzer = MetaAnalyzer("qwen2_5-7b-instruct-1m")
    analyzer.analyze_one_by_one(limit=80)