"""
scripts/accuracy_report.py - Reporte de precision por confianza
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from agents.brain import TradingBrain

def main():
    model_name = sys.argv[1] if len(sys.argv) > 1 else "BNBUSDT_backtest"
    
    brain = TradingBrain(model_name=model_name)
    
    print(f"\nReporte de precision - Modelo: {model_name}")
    print("=" * 70)
    
    report = brain.get_accuracy_report(pair="BNBUSDT")
    print(report)
    
    # Guardar reporte en archivo
    output_path = config.LOGS_DIR / f"accuracy_report_{model_name}.txt"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\nReporte guardado en: {output_path}")


if __name__ == "__main__":
    main()