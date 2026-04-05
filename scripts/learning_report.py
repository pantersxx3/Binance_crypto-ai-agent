"""
scripts/learning_report.py - Reporte de aprendizaje automatico
Uso: python scripts/learning_report.py <model_name>
Ejemplo: python scripts/learning_report.py BNBUSDT_backtest
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from agents.brain import TradingBrain

def main():
    if len(sys.argv) < 2:
        print("Uso: python scripts/learning_report.py <model_name>")
        print("Ejemplo: python scripts/learning_report.py BNBUSDT_backtest")
        return
    
    model_name = sys.argv[1]
    pair = model_name.replace('_backtest', '').replace('_live', '')
    
    brain = TradingBrain(model_name=model_name)
    
    print(f"\nREPORTE DE APRENDIZAJE - Modelo: {model_name}")
    print("=" * 80)
    
    print("\n1. PRECISION POR HORIZONTE TEMPORAL")
    print("-" * 80)
    precision = brain.evaluate_accuracy_by_horizon(pair=pair)
    
    for h in [1, 4, 24]:
        r = precision.get(h, {})
        if 'error' not in r:
            print(f"{h}h: {r.get('accuracy_pct', 0):.1f}% precision | "
                  f"PnL: {r.get('avg_pnl_pct', 0):+.2f}% | "
                  f"Muestras: {r.get('total_predictions', 0)}")
            if 'by_direction' in r:
                for direction in ['BUY', 'SELL']:
                    d = r['by_direction'][direction]
                    if d['total'] > 0:
                        print(f"   {direction}: {d.get('accuracy', 0):.1f}% | "
                              f"PnL: {d.get('avg_pnl', 0):+.2f}% | "
                              f"Muestras: {d['total']}")
    
    print("\n2. INSIGHTS DE APRENDIZAJE")
    print("-" * 80)
    insights = brain.generate_learning_insights(pair=pair, min_samples=10)
    
    print(f"Suficiencia de datos: {insights.get('data_sufficiency', 'unknown').upper()}")
    print(f"Precision general: {insights.get('overall_accuracy', 0):.1f}%")
    print(f"Total muestras analizadas: {insights.get('total_analyzed', 0)}")
    
    if insights.get('model_limitations'):
        print("\nLimitaciones del modelo:")
        for lim in insights['model_limitations']:
            print(f"  - {lim}")
    
    if insights.get('actionable_recommendations'):
        print("\nRecomendaciones:")
        for rec in insights['actionable_recommendations']:
            print(f"  - {rec}")
    
    if insights.get('data_gaps'):
        print("\nBrechas de datos:")
        for gap in insights['data_gaps']:
            print(f"  - {gap}")
    
    print("\n3. ANALISIS DE PATRONES")
    print("-" * 80)
    for p in insights.get('pattern_analysis', [])[:10]:
        print(f"{p['direction']:4} | regime:{p['regime']:8} | trend:{p['trend']:8} | "
              f"Acc:{p['accuracy']:5.1f}% | Conf:{p['avg_confidence']:5.1f} | "
              f"PnL:{p['avg_pnl']:+6.2f}% | N:{p['samples']}")
    
    print("\n" + "=" * 80)
    print("Para aplicar estos aprendizajes, ejecuta backtesting nuevamente.")
    print("El sistema ajustara automaticamente el prompt basado en estos insights.")
    print("=" * 80)
    
    output_path = config.LOGS_DIR / f"learning_report_{model_name}.txt"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"REPORTE DE APRENDIZAJE - Modelo: {model_name}\n")
        f.write("=" * 80 + "\n")
        for h in [1, 4, 24]:
            r = precision.get(h, {})
            if 'error' not in r:
                f.write(f"{h}h: {r.get('accuracy_pct', 0):.1f}% precision\n")
        f.write("\n" + "=" * 80 + "\n")
    
    print(f"\nReporte guardado en: {output_path}")

if __name__ == "__main__":
    main()