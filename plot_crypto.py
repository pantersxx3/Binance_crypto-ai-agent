"""
scripts/plot_crypto.py - Genera grafico de BNBUSDT
CORREGIDO: Eliminado parametro alpha invalido en tick_params
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import config
from data.collector import DataCollector
import sqlite3

plt.style.use('seaborn-v0_8-darkgrid')
fig, ax = plt.subplots(figsize=(14, 7))

collector = DataCollector(db_path=config.MARKET_DATA_DB)

start_date = "01 Jan 2024"
end_date = "01 Mar 2024"

print(f"Buscando datos para BNBUSDT: {start_date} -> {end_date}")

df = collector.get_historical_klines(
    "BNBUSDT",
    "1h",
    start_date=start_date,
    end_date=end_date
)

if df.empty:
    print("No se obtuvieron datos de Binance. Intentando cargar desde SQLite local...")
    
    conn = sqlite3.connect(str(config.MARKET_DATA_DB))
    
    query = """
        SELECT timestamp, open, high, low, close, volume
        FROM ohlcv 
        WHERE pair = 'BNBUSDT' 
        AND interval = '1h'
        AND timestamp >= ?
        AND timestamp <= ?
        ORDER BY timestamp ASC
    """
    
    df = pd.read_sql_query(
        query, 
        conn, 
        params=[
            pd.to_datetime("2026-01-01").isoformat(),
            pd.to_datetime("2026-03-01").isoformat()
        ]
    )
    conn.close()
    
    if not df.empty:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        print(f"Cargadas {len(df)} velas desde SQLite local")

if df.empty:
    print("No hay datos disponibles en Binance ni en la base de datos local.")
    print("Sugerencia: Ejecuta primero el backtesting para poblar la base de datos:")
    print("  python backtesting.py --train-start '1 Jan 2026' --train-end '1 Mar 2026'")
else:
    # Grafico de precios
    ax.plot(df['timestamp'], df['close'], label='Close Price', linewidth=1, color='#2E86AB')
    
    # Volumen como barras en eje secundario
    ax2 = ax.twinx()
    # CORREGIDO: Usar color con transparencia RGBA en lugar de alpha en tick_params
    ax2.bar(df['timestamp'], df['volume'], alpha=0.1, label='Volume', color='#A23B72')
    ax2.set_ylabel('Volume', color='#A23B72')
    # CORREGIDO: Eliminar alpha de tick_params, usar grid_alpha si es necesario
    ax2.tick_params(axis='y', labelcolor='#A23B72')
    ax2.grid(False)  # Desactivar grilla del eje secundario para evitar superposicion
    
    # Formato de fechas en el eje X
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # Labels y titulo
    ax.set_xlabel('Date')
    ax.set_ylabel('Price (USDT)')
    ax.set_title(f'BNBUSDT Price Chart\n{start_date} to {end_date}')
    
    # Leyenda combinada
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    
    # Grid y layout
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    
    # Guardar y mostrar
    output_path = config.LOGS_DIR / "bnbusdt_chart.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Grafico guardado en: {output_path}")
    plt.show()