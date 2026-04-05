"""
agents/meta_analyzer.py - Analiza POR QUÉ fallaron/acertaron las predicciones
Identifica patrones de error y genera recomendaciones automáticas
"""
import sqlite3
from datetime import datetime
from loguru import logger
from pathlib import Path
import json

class MetaAnalyzer:
    """Analiza decisiones de trading para identificar patrones de éxito/fracaso"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def analyze_failures(self, pair: str = None, limit: int = 50) -> dict:
        """
        Analiza los últimos N trades para identificar patrones de error
        
        Args:
            pair: Par de trading específico (None = todos)
            limit: Número máximo de trades a analizar
        
        Returns:
            dict con análisis de patrones y recomendaciones
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Obtener decisiones con sus outcomes
        if pair:
            cursor.execute('''
                SELECT d.direction, d.confidence, d.rsi, d.market_regime, 
                       d.volume_trend, d.bb_position, d.atr_pct, d.trend_strength,
                       o.was_correct, o.pnl, o.actual_move, d.hypothesis, d.timestamp
                FROM decisions d
                JOIN outcomes o ON d.id = o.decision_id
                WHERE d.pair = ? AND o.was_correct IS NOT NULL
                ORDER BY d.timestamp DESC
                LIMIT ?
            ''', (pair, limit))
        else:
            cursor.execute('''
                SELECT d.direction, d.confidence, d.rsi, d.market_regime, 
                       d.volume_trend, d.bb_position, d.atr_pct, d.trend_strength,
                       o.was_correct, o.pnl, o.actual_move, d.hypothesis, d.timestamp
                FROM decisions d
                JOIN outcomes o ON d.id = o.decision_id
                WHERE o.was_correct IS NOT NULL
                ORDER BY d.timestamp DESC
                LIMIT ?
            ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return {'error': 'No hay datos para analizar'}
        
        # Separar wins y losses
        failures = [r for r in rows if r[8] == 0]  # was_correct = 0
        wins = [r for r in rows if r[8] == 1]
        
        analysis = {
            'total_trades': len(rows),
            'wins': len(wins),
            'losses': len(failures),
            'win_rate': round(len(wins) / len(rows) * 100, 2) if len(rows) > 0 else 0,
            'avg_pnl': round(sum(r[9] for r in rows) / len(rows), 2) if rows else 0,
            'failure_patterns': self._identify_failure_patterns(failures),
            'success_patterns': self._identify_success_patterns(wins),
            'recommendations': [],
            'analyzed_at': datetime.now().isoformat()
        }
        
        # Generar recomendaciones automáticas
        analysis['recommendations'] = self._generate_recommendations(analysis)
        
        # Log resumen
        logger.info(f"📊 Meta-Análisis completado | Trades: {len(rows)} | Win Rate: {analysis['win_rate']}%")
        if analysis['recommendations']:
            logger.info(f"   {len(analysis['recommendations'])} recomendaciones generadas")
        
        return analysis
    
    def _identify_failure_patterns(self, failures: list) -> dict:
        """Identifica patrones comunes en trades perdedores"""
        if not failures:
            return {}
        
        patterns = {
            'rsi_misleading': 0,           # RSI dio señal falsa
            'volume_ignored': 0,           # No hubo confirmación de volumen
            'trend_wrong': 0,              # Régimen de mercado incorrecto
            'volatility_surprise': 0,      # ATR subestimado
            'bb_extreme': 0,               # Precio en bandas extremas
            'confidence_too_high': 0,      # Confianza >80% pero perdió
            'against_trend': 0,            # Operó contra tendencia fuerte
            'low_confidence_win': 0        # Baja confianza pero ganó (raro)
        }
        
        for f in failures:
            direction, confidence, rsi, regime, volume, bb_pos, atr, trend, correct, pnl, actual_move, hypothesis, timestamp = f
            
            # RSI engañoso (compró con RSI alto o vendió con RSI bajo)
            if direction == 'BUY' and rsi > 60:
                patterns['rsi_misleading'] += 1
            elif direction == 'SELL' and rsi < 40:
                patterns['rsi_misleading'] += 1
            
            # Volumen ignorado (operó con volumen bajo)
            if volume and volume == 'LOW':
                patterns['volume_ignored'] += 1
            
            # Régimen incorrecto (compró en bearish o vendió en bullish)
            if direction == 'BUY' and regime == 'bearish':
                patterns['trend_wrong'] += 1
            elif direction == 'SELL' and regime == 'bullish':
                patterns['trend_wrong'] += 1
            
            # Volatilidad subestimada (ATR alto sin ajustar SL)
            if atr and atr > 3.0:
                patterns['volatility_surprise'] += 1
            
            # Bandas extremas (precio cerca de bandas de Bollinger)
            if bb_pos and (bb_pos < 10 or bb_pos > 90):
                patterns['bb_extreme'] += 1
            
            # Confianza excesiva
            if confidence > 80:
                patterns['confidence_too_high'] += 1
            
            # Contra tendencia fuerte
            if trend and trend == 'STRONG':
                if direction == 'BUY' and regime == 'bearish':
                    patterns['against_trend'] += 1
                elif direction == 'SELL' and regime == 'bullish':
                    patterns['against_trend'] += 1
        
        return patterns
    
    def _identify_success_patterns(self, wins: list) -> dict:
        """Identifica patrones comunes en trades ganadores"""
        if not wins:
            return {}
        
        patterns = {
            'rsi_confirmed': 0,            # RSI en zona óptima
            'volume_confirmed': 0,         # Volumen alto confirmó
            'with_trend': 0,               # Operó a favor de tendencia
            'moderate_volatility': 0,      # ATR en rango normal
            'bb_middle': 0,                # Precio en zona media de BB
            'confidence justified': 0      # Alta confianza y acertó
        }
        
        for w in wins:
            direction, confidence, rsi, regime, volume, bb_pos, atr, trend, correct, pnl, actual_move, hypothesis, timestamp = w
            
            # RSI en zona óptima
            if 30 <= rsi <= 60:
                patterns['rsi_confirmed'] += 1
            
            # Volumen confirmó
            if volume and volume == 'HIGH':
                patterns['volume_confirmed'] += 1
            
            # A favor de tendencia
            if direction == 'BUY' and regime == 'bullish':
                patterns['with_trend'] += 1
            elif direction == 'SELL' and regime == 'bearish':
                patterns['with_trend'] += 1
            
            # Volatilidad normal
            if atr and 1.0 <= atr <= 3.0:
                patterns['moderate_volatility'] += 1
            
            # Bandas en zona media
            if bb_pos and 20 <= bb_pos <= 80:
                patterns['bb_middle'] += 1
            
            # Confianza justificada
            if confidence >= 70:
                patterns['confidence_justified'] += 1
        
        return patterns
    
    def _generate_recommendations(self, analysis: dict) -> list:
        """Genera recomendaciones basadas en patrones de error"""
        recommendations = []
        patterns = analysis.get('failure_patterns', {})
        success = analysis.get('success_patterns', {})
        win_rate = analysis.get('win_rate', 0)
        
        # Umbral: patrón aparece en >20% de losses
        threshold = max(3, int(analysis.get('losses', 0) * 0.2))
        
        if patterns.get('rsi_misleading', 0) > threshold:
            recommendations.append({
                'priority': 'HIGH',
                'category': 'RSI',
                'issue': f"RSI engañoso en {patterns['rsi_misleading']} pérdidas",
                'action': "Considera usar RSI + Stochastic juntos. RSI solo da falsas señales en tendencias fuertes.",
                'config_change': {'MIN_CONFIDENCE': 75}
            })
        
        if patterns.get('volume_ignored', 0) > threshold:
            recommendations.append({
                'priority': 'HIGH',
                'category': 'VOLUMEN',
                'issue': f"{patterns['volume_ignored']} pérdidas sin confirmación de volumen",
                'action': "Requiere volume_trend = HIGH para entries. Sin volumen, las rupturas son falsas.",
                'config_change': None
            })
        
        if patterns.get('trend_wrong', 0) > threshold:
            recommendations.append({
                'priority': 'CRITICAL',
                'category': 'TENDENCIA',
                'issue': f"{patterns['trend_wrong']} pérdidas operando contra la tendencia",
                'action': "Solo BUY en regime bullish, solo SELL en bearish. Never fight the trend.",
                'config_change': {'MIN_CONFIDENCE': 80}
            })
        
        if patterns.get('confidence_too_high', 0) > 2:
            recommendations.append({
                'priority': 'MEDIUM',
                'category': 'CONFIANZA',
                'issue': f"{patterns['confidence_too_high']} pérdidas con confianza >80%",
                'action': "La alta confianza no garantiza wins. Revisa el prompt del LLM.",
                'config_change': {'MIN_CONFIDENCE': 65}
            })
        
        if patterns.get('volatility_surprise', 0) > threshold:
            recommendations.append({
                'priority': 'MEDIUM',
                'category': 'VOLATILIDAD',
                'issue': f"{patterns['volatility_surprise']} pérdidas por volatilidad alta (ATR >3%)",
                'action': "Usar SL más amplio cuando ATR > 3%. Considerar no operar en alta volatilidad.",
                'config_change': {'STOP_LOSS_PCT': 2.0}
            })
        
        if patterns.get('against_trend', 0) > threshold:
            recommendations.append({
                'priority': 'CRITICAL',
                'category': 'TREND',
                'issue': f"{patterns['against_trend']} pérdidas contra tendencia fuerte",
                'action': "Agregar filtro: no operar contra trend_strength = STRONG",
                'config_change': None
            })
        
        # Recomendaciones positivas basadas en éxitos
        if success.get('with_trend', 0) > threshold:
            recommendations.append({
                'priority': 'INFO',
                'category': 'SUCCESS',
                'issue': f"{success['with_trend']} wins operando CON la tendencia",
                'action': "✅ Confirmado: Operar con la tendencia es la estrategia más efectiva",
                'config_change': None
            })
        
        if success.get('volume_confirmed', 0) > threshold:
            recommendations.append({
                'priority': 'INFO',
                'category': 'SUCCESS',
                'issue': f"{success['volume_confirmed']} wins con volumen alto",
                'action': "✅ Confirmado: Volumen alto aumenta probabilidad de éxito",
                'config_change': None
            })
        
        # Si win rate es muy bajo
        if win_rate < 45:
            recommendations.append({
                'priority': 'CRITICAL',
                'category': 'GENERAL',
                'issue': f"Win rate muy bajo: {win_rate}%",
                'action': "Considera ajustar MIN_CONFIDENCE, revisar prompt del LLM, o cambiar modelo",
                'config_change': {'MIN_CONFIDENCE': 75}
            })
        elif win_rate > 65:
            recommendations.append({
                'priority': 'INFO',
                'category': 'GENERAL',
                'issue': f"Win rate excelente: {win_rate}%",
                'action': "✅ Estrategia funcionando bien. Considera aumentar capital por operación",
                'config_change': None
            })
        
        return recommendations
    
    def get_summary_report(self, pair: str = None) -> str:
        """Genera reporte en texto para mostrar al usuario"""
        analysis = self.analyze_failures(pair=pair)
        
        if 'error' in analysis:
            return f"❌ {analysis['error']}"
        
        report = []
        report.append("=" * 60)
        report.append("📊 META-ANÁLISIS DE TRADING")
        report.append("=" * 60)
        report.append(f"Total Trades: {analysis['total_trades']}")
        report.append(f"Wins: {analysis['wins']} | Losses: {analysis['losses']}")
        report.append(f"Win Rate: {analysis['win_rate']}%")
        report.append(f"Avg PnL: {analysis['avg_pnl']}%")
        report.append("")
        
        if analysis['recommendations']:
            report.append("🎯 RECOMENDACIONES:")
            report.append("-" * 60)
            for i, rec in enumerate(analysis['recommendations'], 1):
                priority_icon = "🔴" if rec['priority'] == 'CRITICAL' else "🟠" if rec['priority'] == 'HIGH' else "🟡"
                report.append(f"{i}. {priority_icon} [{rec['category']}] {rec['issue']}")
                report.append(f"   → {rec['action']}")
                if rec.get('config_change'):
                    report.append(f"   → Config sugerido: {rec['config_change']}")
                report.append("")
        else:
            report.append("✅ No se identificaron patrones de error críticos")
        
        report.append("=" * 60)
        
        return "\n".join(report)


# Función helper para usar desde brain.py
def get_meta_analysis(db_path: str, pair: str = None, limit: int = 50) -> dict:
    """Función conveniente para obtener análisis desde cualquier módulo"""
    analyzer = MetaAnalyzer(db_path)
    return analyzer.analyze_failures(pair=pair, limit=limit)


if __name__ == "__main__":
    # Test rápido
    import config
    db_path = config.get_model_db_path("BNBUSDT_backtest")
    
    if db_path.exists():
        analyzer = MetaAnalyzer(str(db_path))
        report = analyzer.get_summary_report(pair="BNBUSDT")
        print(report)
    else:
        print(f"❌ DB no encontrada: {db_path}")