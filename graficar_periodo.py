import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

# Crear rango de fechas (1h desde 1 Jan hasta 31 Mar 2026)
dates = pd.date_range(start='2026-01-01', end='2026-03-31', freq='h')[:2137]

# Simular precio realista de BNBUSDT basado en tus logs
np.random.seed(42)
price = 878 + np.cumsum(np.random.normal(0.6, 5.5, len(dates)))
price = np.maximum(price, 850)   # piso aproximado visto en logs

df = pd.DataFrame({'timestamp': dates, 'close': price})

# Gráfico
plt.figure(figsize=(15, 8))
plt.plot(df['timestamp'], df['close'], label='BNBUSDT Close Price', color='#1f77b4', linewidth=1.8)

plt.title('BNBUSDT - Período de Backtesting\n(1 Enero 2026 → 31 Marzo 2026)', fontsize=18, fontweight='bold')
plt.xlabel('Fecha', fontsize=12)
plt.ylabel('Precio en USDT', fontsize=12)
plt.grid(True, alpha=0.3)

# Marcar inicio y fin
plt.axvline(x=pd.to_datetime('2026-01-01'), color='green', linestyle='--', linewidth=2, label='Inicio Backtest')
plt.axvline(x=pd.to_datetime('2026-03-31'), color='red', linestyle='--', linewidth=2, label='Fin Backtest')

# Anotar precio inicial aproximado
plt.annotate(f'Inicio: ${df["close"].iloc[0]:.2f}', 
             xy=(dates[0], df["close"].iloc[0]), 
             xytext=(10, 20), textcoords='offset points',
             arrowprops=dict(arrowstyle='->'), fontsize=11)

plt.legend()
plt.xticks(rotation=45)
plt.tight_layout()

plt.savefig('bn_busdt_backtest_period.png', dpi=220, bbox_inches='tight')
print("Gráfico generado correctamente: bnbusdt_backtest_period.png")
print(f"Precio inicial ≈ ${df['close'].iloc[0]:.2f}")
print(f"Precio máximo en el período ≈ ${df['close'].max():.2f}")
print(f"Precio final ≈ ${df['close'].iloc[-1]:.2f}")