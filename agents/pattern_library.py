"""
agents/pattern_library.py - Almacena y recupera patrones de trading exitosos/fallidos
Permite que el bot "recuerde" qué funcionó en el pasado
"""
import sqlite3
import json
from datetime import datetime
from loguru import logger
from pathlib import Path
from typing import Optional, List, Dict

class PatternLibrary:
    """
    Biblioteca de patrones de trading
    Almacena combinaciones de indicadores que resultaron en wins/losses
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Crea tabla de patrones si no existe"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,          -- 'success' o 'failure'
                direction TEXT NOT NULL,             -- 'BUY' o 'SELL'
                rsi_range TEXT,                      -- "30-40", "40-60", etc.
                regime TEXT,                         -- 'bullish', 'bearish', 'neutral'
                volume_trend TEXT,                   -- 'HIGH', 'NORMAL', 'LOW'
                bb_position_range TEXT,              -- "0-20", "20-80", "80-100"
                atr_range TEXT,                      -- "0-1", "1-3", "3+"
                trend_strength TEXT,                 -- 'WEAK', 'MODERATE', 'STRONG'
                avg_confidence REAL,
                win_rate REAL,
                occurrences INTEGER DEFAULT 1,
                last_seen TEXT,
                created_at TEXT,
                notes TEXT,
                UNIQUE(pattern_type, direction, rsi_range, regime, volume_trend)
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_patterns_type 
            ON patterns(pattern_type, direction)
        ''')
        
        conn.commit()
        conn.close()
        logger.debug(f"✅ Pattern Library inicializada: {self.db_path}")
    
    def record_pattern(self, decision: dict, outcome: dict, pattern_type: str = None):
        """
        Registra un patrón basado en el resultado de una decisión
        
        Args:
            decision: Dict con datos de la decisión (direction, confidence, indicators, etc.)
            outcome: Dict con resultado (was_correct, pnl, etc.)
            pattern_type: 'success' o 'failure' (auto-detectado si None)
        """
        if pattern_type is None:
            pattern_type = 'success' if outcome.get('was_correct') else 'failure'
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Crear fingerprint del patrón
        pattern = {
            'direction': decision.get('direction', 'HOLD'),
            'rsi_range': self._categorize_rsi(decision.get('rsi', 50)),
            'regime': decision.get('market_regime', 'neutral'),
            'volume_trend': decision.get('volume_trend', 'NORMAL'),
            'bb_position_range': self._categorize_bb(decision.get('bb_position', 50)),
            'atr_range': self._categorize_atr(decision.get('atr_pct', 1.0)),
            'trend_strength': decision.get('trend_strength', 'WEAK')
        }
        
        # Verificar si el patrón ya existe
        cursor.execute('''
            SELECT id, occurrences, win_rate, avg_confidence FROM patterns 
            WHERE pattern_type = ? 
            AND direction = ?
            AND rsi_range = ?
            AND regime = ?
            AND volume_trend = ?
        ''', (
            pattern_type,
            pattern['direction'],
            pattern['rsi_range'],
            pattern['regime'],
            pattern['volume_trend']
        ))
        
        row = cursor.fetchone()
        
        now = datetime.now().isoformat()
        
        if row:
            # Actualizar patrón existente
            pattern_id, occurrences, win_rate, avg_conf = row
            new_occurrences = occurrences + 1
            
            # Recalcular win_rate y avg_confidence
            new_win_rate = ((win_rate * occurrences) + (100 if pattern_type == 'success' else 0)) / new_occurrences
            new_avg_conf = ((avg_conf * occurrences) + decision.get('confidence', 50)) / new_occurrences
            
            cursor.execute('''
                UPDATE patterns 
                SET occurrences = ?, win_rate = ?, avg_confidence = ?, last_seen = ?
                WHERE id = ?
            ''', (new_occurrences, new_win_rate, new_avg_conf, now, pattern_id))
            
            logger.debug(f"📚 Patrón actualizado: {pattern['direction']} {pattern_type} (#{pattern_id})")
        else:
            # Insertar nuevo patrón
            cursor.execute('''
                INSERT INTO patterns (
                    pattern_type, direction, rsi_range, regime, volume_trend,
                    bb_position_range, atr_range, trend_strength, avg_confidence,
                    win_rate, occurrences, last_seen, created_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            ''', (
                pattern_type,
                pattern['direction'],
                pattern['rsi_range'],
                pattern['regime'],
                pattern['volume_trend'],
                pattern['bb_position_range'],
                pattern['atr_range'],
                pattern['trend_strength'],
                decision.get('confidence', 50),
                100.0 if pattern_type == 'success' else 0.0,
                now,
                now,
                json.dumps(pattern, sort_keys=True)
            ))
            
            logger.debug(f"📚 Nuevo patrón registrado: {pattern['direction']} {pattern_type}")
        
        conn.commit()
        conn.close()
    
    def get_best_patterns(self, direction: str = None, pattern_type: str = 'success', 
                         min_occurrences: int = 3, limit: int = 5) -> list:
        """
        Obtiene los patrones con mayor win rate
        
        Args:
            direction: Filtrar por 'BUY' o 'SELL' (None = ambos)
            pattern_type: 'success' o 'failure'
            min_occurrences: Mínimo de ocurrencias para ser relevante
            limit: Número máximo de patrones a retornar
        
        Returns:
            Lista de patrones ordenados por win_rate DESC
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = '''
            SELECT * FROM patterns 
            WHERE pattern_type = ? AND occurrences >= ?
        '''
        params = [pattern_type, min_occurrences]
        
        if direction:
            query += ' AND direction = ?'
            params.append(direction)
        
        query += ' ORDER BY win_rate DESC, occurrences DESC LIMIT ?'
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        # Convertir a lista de dicts
        patterns = []
        for row in rows:
            patterns.append({
                'id': row[0],
                'pattern_type': row[1],
                'direction': row[2],
                'rsi_range': row[3],
                'regime': row[4],
                'volume_trend': row[5],
                'bb_position_range': row[6],
                'atr_range': row[7],
                'trend_strength': row[8],
                'avg_confidence': row[9],
                'win_rate': row[10],
                'occurrences': row[11],
                'last_seen': row[12],
                'created_at': row[13],
                'notes': row[14]
            })
        
        return patterns
    
    def get_similar_pattern(self, snapshot: dict) -> Optional[dict]:
        """
        Busca patrones similares a la situación actual
        
        Args:
            snapshot: Dict con indicadores actuales
        
        Returns:
            Patrón más similar o None si no hay coincidencias
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        rsi_range = self._categorize_rsi(snapshot.get('rsi', 50))
        regime = snapshot.get('market_regime', 'neutral')
        volume = snapshot.get('volume_trend', 'NORMAL')
        
        # Buscar patrones exitosos similares
        cursor.execute('''
            SELECT * FROM patterns 
            WHERE pattern_type = 'success'
            AND rsi_range = ?
            AND regime = ?
            AND occurrences >= 3
            ORDER BY win_rate DESC
            LIMIT 1
        ''', (rsi_range, regime, volume))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'direction': row[2],
                'rsi_range': row[3],
                'regime': row[4],
                'volume_trend': row[5],
                'win_rate': row[10],
                'occurrences': row[11],
                'recommendation': f"Patrón histórico: {row[10]:.1f}% win rate en {row[11]} ocasiones"
            }
        
        return None
    
    def get_pattern_stats(self) -> dict:
        """Obtiene estadísticas generales de la biblioteca de patrones"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total_patterns,
                SUM(CASE WHEN pattern_type = 'success' THEN 1 ELSE 0 END) as success_patterns,
                SUM(CASE WHEN pattern_type = 'failure' THEN 1 ELSE 0 END) as failure_patterns,
                SUM(occurrences) as total_occurrences,
                AVG(win_rate) as avg_win_rate
            FROM patterns
        ''')
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'total_patterns': row[0] or 0,
                'success_patterns': row[1] or 0,
                'failure_patterns': row[2] or 0,
                'total_occurrences': row[3] or 0,
                'avg_win_rate': round(row[4] or 0, 2)
            }
        
        return {}
    
    def export_patterns(self, output_file: str):
        """Exporta patrones a archivo JSON"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM patterns WHERE occurrences >= 3')
        rows = cursor.fetchall()
        conn.close()
        
        patterns = []
        for row in rows:
            patterns.append({
                'pattern_type': row[1],
                'direction': row[2],
                'rsi_range': row[3],
                'regime': row[4],
                'volume_trend': row[5],
                'bb_position_range': row[6],
                'atr_range': row[7],
                'trend_strength': row[8],
                'win_rate': row[10],
                'occurrences': row[11]
            })
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'exported_at': datetime.now().isoformat(),
                'total_patterns': len(patterns),
                'patterns': patterns
            }, f, indent=2, ensure_ascii=False)
        
        logger.info(f"📤 {len(patterns)} patrones exportados a {output_file}")
    
    def import_patterns(self, input_file: str):
        """Importa patrones desde archivo JSON"""
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        imported = 0
        for p in data.get('patterns', []):
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO patterns (
                        pattern_type, direction, rsi_range, regime, volume_trend,
                        bb_position_range, atr_range, trend_strength,
                        win_rate, occurrences, last_seen, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    p['pattern_type'],
                    p['direction'],
                    p['rsi_range'],
                    p['regime'],
                    p['volume_trend'],
                    p.get('bb_position_range', '20-80'),
                    p.get('atr_range', '1-3'),
                    p.get('trend_strength', 'MODERATE'),
                    p['win_rate'],
                    p['occurrences'],
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
                imported += 1
            except Exception as e:
                logger.debug(f"   Pattern skip: {e}")
        
        conn.commit()
        conn.close()
        logger.info(f"📥 {imported} patrones importados desde {input_file}")
    
    def _categorize_rsi(self, rsi: float) -> str:
        """Categoriza RSI en rangos"""
        if rsi < 30:
            return "0-30"
        elif rsi < 40:
            return "30-40"
        elif rsi < 50:
            return "40-50"
        elif rsi < 60:
            return "50-60"
        elif rsi < 70:
            return "60-70"
        else:
            return "70-100"
    
    def _categorize_bb(self, bb_pos: float) -> str:
        """Categoriza posición en Bandas de Bollinger"""
        if bb_pos < 20:
            return "0-20"
        elif bb_pos < 50:
            return "20-50"
        elif bb_pos < 80:
            return "50-80"
        else:
            return "80-100"
    
    def _categorize_atr(self, atr_pct: float) -> str:
        """Categoriza volatilidad ATR"""
        if atr_pct < 1.0:
            return "0-1"
        elif atr_pct < 3.0:
            return "1-3"
        else:
            return "3+"


# Función helper para usar desde brain.py
def record_pattern(db_path: str, decision: dict, outcome: dict):
    """Función conveniente para registrar patrón desde cualquier módulo"""
    library = PatternLibrary(db_path)
    library.record_pattern(decision, outcome)


if __name__ == "__main__":
    # Test rápido
    import config
    db_path = config.get_model_db_path("BNBUSDT_backtest")
    
    if db_path.exists():
        library = PatternLibrary(str(db_path))
        
        print("\n📊 ESTADÍSTICAS DE PATRONES:")
        stats = library.get_pattern_stats()
        print(f"   Total: {stats['total_patterns']}")
        print(f"   Success: {stats['success_patterns']}")
        print(f"   Failure: {stats['failure_patterns']}")
        print(f"   Avg Win Rate: {stats['avg_win_rate']}%")
        
        print("\n🏆 MEJORES PATRONES (BUY):")
        best = library.get_best_patterns(direction='BUY', limit=3)
        for p in best:
            print(f"   - {p['direction']} | RSI:{p['rsi_range']} | Regime:{p['regime']} | Win:{p['win_rate']:.1f}% ({p['occurrences']}x)")
    else:
        print(f"❌ DB no encontrada: {db_path}")