"""
agents/validator.py - Valida predicciones del modelo cuando llega una nueva decisión
Analiza: BUY→SELL, SELL→BUY, HOLD→acción, y patrones de indicadores
"""
import sqlite3
from datetime import datetime
from loguru import logger
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config

class PredictionValidator:
    """Valida predicciones del modelo cuando llega una nueva decisión"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_table()  # Crear tabla si no existe
    
    def _init_table(self):
        """Crea la tabla de validaciones si no existe"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS prediction_validations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_id INTEGER,
                    validated_at TEXT,
                    previous_direction TEXT,
                    previous_confidence INTEGER,
                    price_change_pct REAL,
                    validation_result TEXT,
                    success BOOLEAN,
                    reason TEXT,
                    opportunity_cost REAL,
                    pattern_learned TEXT,
                    prev_rsi REAL,
                    prev_regime TEXT,
                    prev_trend TEXT,
                    current_rsi REAL,
                    current_regime TEXT,
                    current_trend TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.debug(f"Tabla prediction_validations verificada en {self.db_path}")
            
        except Exception as e:
            logger.error(f"Error creando tabla prediction_validations: {e}")
    
    def validate_previous_prediction(self, current_snapshot: dict, previous_decision: dict) -> dict:
        """
        Valida la predicción anterior basada en los datos actuales.
        
        Args:
            current_snapshot: Datos actuales del mercado
            previous_decision: Decisión anterior del modelo
        
        Returns:
            dict con validación y análisis
        """
        validation = {
            'previous_decision_id': previous_decision.get('id'),
            'previous_direction': previous_decision.get('direction'),
            'previous_confidence': previous_decision.get('confidence'),
            'previous_hypothesis': previous_decision.get('hypothesis'),
            'previous_indicators': {
                'rsi': previous_decision.get('rsi'),
                'regime': previous_decision.get('market_regime'),
                'trend': previous_decision.get('trend_strength')
            },
            'current_indicators': {
                'rsi': current_snapshot.get('indicators_1h', {}).get('rsi'),
                'regime': current_snapshot.get('indicators_1h', {}).get('market_regime'),
                'trend': current_snapshot.get('indicators_1h', {}).get('trend_strength')
            },
            'price_change_pct': 0,
            'validation_result': 'PENDING',
            'success': False,
            'reason': '',
            'opportunity_cost': 0,
            'pattern_learned': ''
        }
        
        # Calcular cambio de precio
        previous_price = previous_decision.get('price', 0)
        current_price = current_snapshot.get('current_price', 0)
        
        if previous_price > 0:
            validation['price_change_pct'] = round(
                (current_price - previous_price) / previous_price * 100, 2
            )
        
        # Validar según dirección anterior
        prev_direction = previous_decision.get('direction', 'HOLD')
        
        if prev_direction == 'BUY':
            validation = self._validate_buy(validation, current_snapshot)
        elif prev_direction == 'SELL':
            validation = self._validate_sell(validation, current_snapshot)
        elif prev_direction == 'HOLD':
            validation = self._validate_hold(validation, current_snapshot)
        
        # Identificar patrón aprendido
        validation['pattern_learned'] = self._identify_pattern(validation)
        
        return validation
    
    def _validate_buy(self, validation: dict, current_snapshot: dict) -> dict:
        """Valida predicción BUY anterior"""
        current_rsi = current_snapshot.get('indicators_1h', {}).get('rsi', 50)
        current_regime = current_snapshot.get('indicators_1h', {}).get('market_regime', 'neutral')
        price_change = validation['price_change_pct']
        
        # Si el precio subió >= 1%, la predicción fue correcta
        if price_change >= 1.0:
            validation['validation_result'] = 'CORRECT'
            validation['success'] = True
            validation['reason'] = f'Precio subió {price_change}%, BUY fue correcto'
        # Si el precio bajó >= 1%, la predicción fue incorrecta
        elif price_change <= -1.0:
            validation['validation_result'] = 'INCORRECT'
            validation['success'] = False
            validation['reason'] = f'Precio bajó {price_change}%, BUY fue incorrecto'
            
            # Analizar por qué falló
            prev_regime = validation['previous_indicators']['regime']
            if prev_regime == 'bearish':
                validation['reason'] += ' | Entró en régimen bajista'
            if validation['previous_indicators']['rsi'] and validation['previous_indicators']['rsi'] > 50:
                validation['reason'] += ' | RSI no estaba en sobreventa'
        # Si el precio se mantuvo lateral, HOLD hubiera sido mejor
        elif -1.0 < price_change < 1.0:
            validation['validation_result'] = 'SUBOPTIMAL'
            validation['success'] = False
            validation['reason'] = f'Precio lateral ({price_change}%), HOLD hubiera evitado comisiones'
            validation['opportunity_cost'] = abs(price_change) + 0.2  # Comisión estimada
        
        # Verificar si debería haber cerrado antes
        if current_rsi and current_rsi > 70:
            validation['reason'] += ' | RSI > 70: debería haber cerrado en sobrecompra'
        if current_regime == 'bearish':
            validation['reason'] += ' | Régime cambió a bajista: debería haber cerrado'
        
        return validation
    
    def _validate_sell(self, validation: dict, current_snapshot: dict) -> dict:
        """Valida predicción SELL anterior"""
        price_change = validation['price_change_pct']
        
        # En SPOT, SELL es para cerrar, no para abrir
        # Validamos si fue buen momento para cerrar
        if price_change >= 1.0:
            # El precio subió después de vender → vendió muy pronto
            validation['validation_result'] = 'PREMATURE'
            validation['success'] = False
            validation['reason'] = f'Precio subió {price_change}% después de vender, vendió muy pronto'
            validation['opportunity_cost'] = price_change
        elif price_change <= -1.0:
            # El precio bajó después de vender → buen timing
            validation['validation_result'] = 'CORRECT'
            validation['success'] = True
            validation['reason'] = f'Precio bajó {price_change}%, SELL fue correcto'
        else:
            validation['validation_result'] = 'ACCEPTABLE'
            validation['success'] = True
            validation['reason'] = f'Precio estable ({price_change}%), SELL aceptable'
        
        return validation
    
    def _validate_hold(self, validation: dict, current_snapshot: dict) -> dict:
        """Valida predicción HOLD anterior"""
        price_change = validation['price_change_pct']
        current_rsi = current_snapshot.get('indicators_1h', {}).get('rsi', 50)
        current_regime = current_snapshot.get('indicators_1h', {}).get('market_regime', 'neutral')
        
        # HOLD fue correcto si no había señal clara
        if abs(price_change) < 1.0:
            validation['validation_result'] = 'CORRECT'
            validation['success'] = True
            validation['reason'] = f'Precio lateral ({price_change}%), HOLD evitó operación innecesaria'
        # HOLD fue incorrecto si hubo movimiento claro
        elif price_change >= 2.0:
            validation['validation_result'] = 'MISSED_OPPORTUNITY'
            validation['success'] = False
            validation['reason'] = f'Precio subió {price_change}%, HOLD perdió oportunidad de BUY'
            validation['opportunity_cost'] = price_change - 0.2  # Comisión estimada
            
            # Analizar por qué no compró
            prev_rsi = validation['previous_indicators']['rsi']
            prev_regime = validation['previous_indicators']['regime']
            if prev_rsi and prev_rsi < 40 and prev_regime == 'bullish':
                validation['reason'] += ' | Tenía señal de BUY (RSI<40 + bullish)'
        elif price_change <= -2.0:
            validation['validation_result'] = 'CORRECT_AVOIDED_LOSS'
            validation['success'] = True
            validation['reason'] = f'Precio bajó {price_change}%, HOLD evitó pérdida (correcto)'
        else:
            validation['validation_result'] = 'ACCEPTABLE'
            validation['success'] = True
            validation['reason'] = f'Movimiento moderado ({price_change}%), HOLD aceptable'
        
        return validation
    
    def _identify_pattern(self, validation: dict) -> str:
        """Identifica patrón aprendido de esta validación"""
        prev_rsi = validation['previous_indicators']['rsi']
        prev_regime = validation['previous_indicators']['regime']
        prev_trend = validation['previous_indicators']['trend']
        success = validation['success']
        direction = validation['previous_direction']
        
        if success and direction == 'BUY':
            if prev_rsi and prev_rsi < 40 and prev_regime == 'bullish':
                return 'BUY_RSI<40_BULLISH = WIN'
            elif prev_trend == 'STRONG':
                return 'BUY_STRONG_TREND = WIN'
        elif not success and direction == 'BUY':
            if prev_regime == 'bearish':
                return 'BUY_BEARISH = LOSS (no operar contra tendencia)'
            elif prev_rsi and prev_rsi > 50:
                return 'BUY_RSI>50 = LOSS (RSI no en sobreventa)'
        elif success and direction == 'HOLD':
            if abs(validation['price_change_pct']) < 1.0:
                return 'HOLD_LATERAL = WIN (evita comisiones)'
        elif not success and direction == 'HOLD':
            if validation['price_change_pct'] and validation['price_change_pct'] > 2.0:
                return 'HOLD_BULLISH_STRONG = LOSS (oportunidad perdida)'
        
        rsi_str = f"{prev_rsi:.0f}" if prev_rsi else "NA"
        return f'{direction}_RSI{rsi_str}_{prev_regime} = {"WIN" if success else "LOSS"}'
    
    def save_validation(self, validation: dict):
        """Guarda la validación en la base de datos"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO prediction_validations (
                    decision_id, validated_at, previous_direction, previous_confidence,
                    price_change_pct, validation_result, success, reason, opportunity_cost,
                    pattern_learned, prev_rsi, prev_regime, prev_trend,
                    current_rsi, current_regime, current_trend
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                validation['previous_decision_id'],
                datetime.now().isoformat(),
                validation['previous_direction'],
                validation['previous_confidence'],
                validation['price_change_pct'],
                validation['validation_result'],
                1 if validation['success'] else 0,
                validation['reason'],
                validation['opportunity_cost'],
                validation['pattern_learned'],
                validation['previous_indicators']['rsi'],
                validation['previous_indicators']['regime'],
                validation['previous_indicators']['trend'],
                validation['current_indicators']['rsi'],
                validation['current_indicators']['regime'],
                validation['current_indicators']['trend']
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error guardando validación: {e}")
    
    def get_pattern_stats(self) -> dict:
        """Obtiene estadísticas de patrones aprendidos"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT pattern_learned, COUNT(*) as count,
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                       AVG(opportunity_cost) as avg_opportunity_cost
                FROM prediction_validations
                WHERE pattern_learned != ''
                GROUP BY pattern_learned
                ORDER BY count DESC
            ''')
            
            patterns = []
            for row in cursor.fetchall():
                patterns.append({
                    'pattern': row[0],
                    'count': row[1],
                    'successes': row[2],
                    'success_rate': round(row[2] / row[1] * 100, 1) if row[1] > 0 else 0,
                    'avg_opportunity_cost': round(row[3] or 0, 2)
                })
            
            conn.close()
            return {'patterns': patterns}
        except Exception as e:
            logger.error(f"Error obteniendo patrones: {e}")
            return {'patterns': []}


def validate_and_save(db_path: str, current_snapshot: dict, previous_decision: dict):
    """Función conveniente para validar y guardar"""
    validator = PredictionValidator(db_path)
    validation = validator.validate_previous_prediction(current_snapshot, previous_decision)
    validator.save_validation(validation)
    return validation