# Crypto AI Trading Bot

Sistema avanzado de trading automatizado para criptomonedas que combina **análisis tÉcnico** con **inteligencia artificial** (LLMs locales y remotos) para tomar decisiones de trading informadas.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-red.svg)](LICENSE)
[![Binance](https://img.shields.io/badge/Binance-API-yellow.svg)](https://www.binance.com/)

---

## Características Principales

### Inteligencia Artificial Flexible
- **Multi-Provider LLM**: Soporte para modelos locales (LM Studio/Ollama) y remotos (OllamaFreeAPI)
- **10+ Modelos Disponibles**: Qwen2.5, Llama3, DeepSeek-R1, Mistral, GPT-OSS, etc.
- **Fallback Automático**: Si la API remota falla, usa modelo local automáticamente
- **Aprendizaje Continuo**: Valida y aprende de cada decisión tomada

### Análisis TÉcnico Avanzado

| Indicador | Configuración | Propósito |
|-----------|--------------|-----------|
| RSI | 14 períedos | Sobrecompra/sobreventa |
| MACD | 12,26,9 | Momentum y cruces |
| Bollinger Bands | 20,2 | Volatilidad y posición relativa |
| ATR | 14 períodos | Volatilidad absoluta |
| Stochastic | 14,3 | Momentum corto plazo |
| Volumen | vs SMA 20 | Confirmación de movimientos |
| EMA | 9/20 | Regimen de mercado |

### Gestión de Riesgo
- ✅ Stop Loss configurable (default: 1.0%)
- ✅ Take Profit configurable (default: 2.5%)
- ✅ trailing Stop (opcional)
- ✅ Máximo de posiciones simultáneas
- ✅ Confianza mínima para operar
- ✅ Hard Stop Loss de seguridad (5%)

### y Sistema de Aprendizaje
```
1. IA decide → 2. Se ejecuta → 3. Se valida ‒ 4. Se aprende ‒ 5. Mejora próxima decisión

```

Cada validación genera patrones aprendidos que se inyectan en futuras decisiones.

### Checkpoint & Resume
- **Backtesting**: Si cortas+ La fjecución, continuá desde donde quedaste
- **Live Trading**: Recupera posiciones abiertas al reiniciar
- **Fresh Start**: Opción `--fresh` para empezar desde cero

---

## Requisitos

### Software
- Python 3.11+
- SQLite3
- LM Studio u Ollama (para modelos locales)
- OllamaFreeAPI (opcional, para modelos remotos gratuitos)

### Hardware Recomendado

| Componente | Mín | Recomendado |
|------------|--------|-------------|
| RAM | 8GB | 16GB |
| CPU | 4 cores | 8 cores |
| Almacenamiento | 10GB | 50GB SSD |
| GPU | No requerida | NVIDIA 6GB+ (opcional) |

---

## Instalación

### 1. Clonar repositorio
```bash
git clone https://github.com/tuusuario/crypto-ai-trading-bot.git
cd crypto-ai-trading-bot
```

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 3. Configurar
```bash
cp config.example.json config.json
nano config.json
```

### 4. Configurar LLM

**Opción A: OllamaFreeAPI (Gratis, sin hardware local)**
`` `json
{
  "llm_provider": {
    "use_ollama_free": true,
    "ollama_free_model": "gpt-oss:20b",
    "fallback_to_local": true
  }
}
````

**Opción B: Local (LM Studio)**
````json
{
  "llm_provider": {
    "use_ollama_free": false
  },
  "llm": {
    "model": "qwen2.5-7b-instruct",
    "base_url": "http://localhost:1234/v1"
  }
}
````

---

## Uso

### Backtesting
```bash
# Con fechas de config.json
python main.py --backtest

# Con fechas personalizadas
python main.py --backtest --start "1 Jan 2026" --end "1 Mar 2026"

# Forzar inicio fresco
python main.py --backtest --fresh

# Con modelo específico
python main.py --backtest --model gpt-oss:20b
```

### Live Trading
```bash
# Modo simulación (dry run)
python main.py

# Modo real (cambiar dry_run: false en config.json)
python main.py

# Forzar API remota
python main.py --use-ollamafree

# Forzar modelo local
python main.py --use-local
```

### Listar Modelos Disponibles
```bash
python main.py --list-models
```

### Ayuda Completa
```bash
python main.py --help
```

---

## Configuración

### Parámetros Principales (config.json)

````json
{
  "binance": {
    "use_testnet": true
  },
  "llm_provider": {
    "use_ollama_free": true,
    "ollama_free_model": "gpt-oss:20b",
    "fallback_to_local": true
  },
  "trading": {
    "trading_pairs": ["BNBUSDT"],
    "cycle_interval_seconds": 3600,
    "min_confidence": 65,
    "dry_run": true,
    "trade_mode": "spot"
  },
  "position_management": {
    "trade_amount_usdt": 100,
    "max_slots": 1,
    "use_tp_sl": true,
    "stop_loss_pct": 1.0,
    "take_profit_pct": 2.5
  }
}
````

### Modelos Soportados (OllamaFreeAPI)

| Modelo | Tamaño | Velocidad | Recomendado |
|--------|--------|-----------|--------------|
| gpt-oss:20b | 20B | Lenta | Máxima calidad |
| deepseek-r1:latest | -7B | ⚁ Media | Razonamiento |
| llama3.2:3b | 3B | Rápida | Testing rápido |
| mistral:latest | 7B | ⚁ Media | Balance |
| llama3:latest | 8B | ⚁ Media | General |

---

## Arquitectura

```
crypto-ai-trading-bot/
├── agents/
│   ├── brain.py              # Cerebro IA
│   ├── llm_adapter.py        # Adaptador multi-provider
│   └── validator.py          # Validación
├── data/
│   ├── collector.py          # Datos + indicadores
│   └── market_data.db        # OHLCV históricos
├── execution/
│   └── executor.py           # Órdenes Binance
├── risk/
│   └── manager.py            # Gestión de riesgo
├── main.py                   # Punto de entrada
├── config.json               # Configuración
└── requirements.txt          # Dependencias
```

---

## Advertencias de Riesgo

> **IMPORTANTE**: Este software es solo para fines educativos.

- El trading de criptomonedas conlleva **alto riesgo**
- Nunca inviertas más de lo que puedas perder
- El rendimiento pasado **no garantiza** resultados futuros
- prueba en **Testnet/Dry Run** antes de Mainnet
- El autor **no se responsabiliza** por pérdidas

### Checklist Antes de Live Trading

| Requisito | Estado Mínimo |
|------------|-----------------|
| Backtesting | 50+ trades |
| Win Rate | >55% estable |
| Profit Factor | >1.5 |
| Paper trading | 2-4 semanas |
| Hard Stop Loss | 5% máximo |

---

## Roadmap

- [ ] Dashboard web en tiempo real
- [ ] Múltiples pares simultáneos
- [ ] Telegram/Discord notifications
- [ ] Análisis de sentimiento
- [ ] Más exchanges (KuCoin, Bybit)
- [ ] Mãtricas avanzadas (Sharpe, Sortino)

---

## Resultados de Testing

| Modelo | Trades | Win Rate | PnL | Períedo |
|--------|--------|-----------|------|-----------|
| gpt-oss:20b | 40 | 60.0% | -39.7%* | Jan-Mar 2026 |
| qwen2.5-7b | 14 | 69.2% | +6.68% | Jan 2024 |

*Sin optimización de gestión de riesgo

---

## Licencia

MIT License - Ver `LICENSE` para más información.

---

## Contacto

- **GitHub Issues**: Bugs y features
- **Email**: tuemail@ejemplo.com

---

<div align="center">

**Desarrollado con amor para la comunidad crypto**

★ **Si te gusta, dale una estrella!**

---

### Disclaimer

Este proyecto es **educativo**. El trading de criptomonedas es riesgoso y puedes perder todo tu capital.

**Usa bajo tu propio riesgo.**
</div>
