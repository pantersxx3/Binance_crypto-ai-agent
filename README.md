<<<<<<< HEAD
# Crypto AI Trading Bot

Sistema avanzado de trading automatizado para criptomonedas que combina **an®¢lisis t®¶cnico** con **inteligencia artificial** (LLMs locales y remotos) para tomar decisiones de trading informadas.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-red.svg)](LICENSE)
[![Binance](https://img.shields.io/badge/Binance-API-yellow.svg)](https://www.binance.com/)

---

## Caracter®™sticas Principales

### Inteligencia Artificial Flexible
- **Multi-Provider LLM**: Soporte para modelos locales (LM Studio/Ollama) y remotos (OllamaFreeAPI)
- **10+ Modelos Disponibles**: Qwen2.5, Llama3, DeepSeek-R1, Mistral, GPT-OSS, etc.
- **Fallback Autom®¢tico**: Si la API remota falla, usa modelo local autom®¢ticamente
- **Aprendizaje Continuo**: Valida y aprende de cada decisi®Æn tomada

### An®¢lisis T®¶cnico Avanzado

| Indicador | Configuraci®Æn | Prop®Æsito |
|-----------|--------------|-----------|
| RSI | 14 per®™edos | Sobrecompra/sobreventa |
| MACD | 12,26,9 | Momentum y cruces |
| Bollinger Bands | 20,2 | Volatilidad y posici®Æn relativa |
| ATR | 14 per®™odos | Volatilidad absoluta |
| Stochastic | 14,3 | Momentum corto plazo |
| Volumen | vs SMA 20 | Confirmaci®Æn de movimientos |
| EMA | 9/20 | Regimen de mercado |

### Gesti®Æn de Riesgo
- ? Stop Loss configurable (default: 1.0%)
- ? Take Profit configurable (default: 2.5%)
- ? trailing Stop (opcional)
- ? M®¢ximo de posiciones simult®¢neas
- ? Confianza m®™nima para operar
- ? Hard Stop Loss de seguridad (5%)

### y Sistema de Aprendizaje
```
1. IA decide °˙ 2. Se ejecuta °˙ 3. Se valida ? 4. Se aprende ? 5. Mejora pr®Æxima decisi®Æn

```

Cada validaci®Æn genera patrones aprendidos que se inyectan en futuras decisiones.

### Checkpoint & Resume
- **Backtesting**: Si cortas+ La fjecuci®Æn, continu®¢ desde donde quedaste
- **Live Trading**: Recupera posiciones abiertas al reiniciar
- **Fresh Start**: Opci®Æn `--fresh` para empezar desde cero

---

## Requisitos

### Software
- Python 3.11+
- SQLite3
- LM Studio u Ollama (para modelos locales)
- OllamaFreeAPI (opcional, para modelos remotos gratuitos)

### Hardware Recomendado

| Componente | M®™n | Recomendado |
|------------|--------|-------------|
| RAM | 8GB | 16GB |
| CPU | 4 cores | 8 cores |
| Almacenamiento | 10GB | 50GB SSD |
| GPU | No requerida | NVIDIA 6GB+ (opcional) |

---

## Instalaci®Æn

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

**Opci®Æn A: OllamaFreeAPI (Gratis, sin hardware local)**
`` `json
{
  "llm_provider": {
    "use_ollama_free": true,
    "ollama_free_model": "gpt-oss:20b",
    "fallback_to_local": true
  }
}
````

**Opci®Æn B: Local (LM Studio)**
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

# Con modelo espec®™fico
python main.py --backtest --model gpt-oss:20b
```

### Live Trading
```bash
# Modo simulaci®Æn (dry run)
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

## Configuraci®Æn

### Par®¢metros Principales (config.json)

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

| Modelo | Tama?o | Velocidad | Recomendado |
|--------|--------|-----------|--------------|
| gpt-oss:20b | 20B | Lenta | M®¢xima calidad |
| deepseek-r1:latest | -7B | ? Media | Razonamiento |
| llama3.2:3b | 3B | R®¢pida | Testing r®¢pido |
| mistral:latest | 7B | ? Media | Balance |
| llama3:latest | 8B | ? Media | General |

---

## Arquitectura

```
crypto-ai-trading-bot/
©¿©§©§ agents/
©¶   ©¿©§©§ brain.py              # Cerebro IA
©¶   ©¿©§©§ llm_adapter.py        # Adaptador multi-provider
©¶   ©∏©§©§ validator.py          # Validaci®Æn
©¿©§©§ data/
©¶   ©¿©§©§ collector.py          # Datos + indicadores
©¶   ©∏©§©§ market_data.db        # OHLCV hist®Æricos
©¿©§©§ execution/
©¶   ©∏©§©§ executor.py           # ®Ærdenes Binance
©¿©§©§ risk/
©¶   ©∏©§©§ manager.py            # Gesti®Æn de riesgo
©¿©§©§ main.py                   # Punto de entrada
©¿©§©§ config.json               # Configuraci®Æn
©∏©§©§ requirements.txt          # Dependencias
```

---

## Advertencias de Riesgo

> **IMPORTANTE**: Este software es solo para fines educativos.

- El trading de criptomonedas conlleva **alto riesgo**
- Nunca inviertas m®¢s de lo que puedas perder
- El rendimiento pasado **no garantiza** resultados futuros
- prueba en **Testnet/Dry Run** antes de Mainnet
- El autor **no se responsabiliza** por p®¶rdidas

### Checklist Antes de Live Trading

| Requisito | Estado M®™nimo |
|------------|-----------------|
| Backtesting | 50+ trades |
| Win Rate | >55% estable |
| Profit Factor | >1.5 |
| Paper trading | 2-4 semanas |
| Hard Stop Loss | 5% m®¢ximo |

---

## Roadmap

- [ ] Dashboard web en tiempo real
- [ ] M®≤ltiples pares simult®¢neos
- [ ] Telegram/Discord notifications
- [ ] An®¢lisis de sentimiento
- [ ] M®¢s exchanges (KuCoin, Bybit)
- [ ] M?tricas avanzadas (Sharpe, Sortino)

---

## Resultados de Testing

| Modelo | Trades | Win Rate | PnL | Per®™edo |
|--------|--------|-----------|------|-----------|
| gpt-oss:20b | 40 | 60.0% | -39.7%* | Jan-Mar 2026 |
| qwen2.5-7b | 14 | 69.2% | +6.68% | Jan 2024 |

*Sin optimizaci®Æn de gesti®Æn de riesgo

---

## Licencia

MIT License - Ver `LICENSE` para m®¢s informaci®Æn.

---

## Contacto

- **GitHub Issues**: Bugs y features
- **Email**: tuemail@ejemplo.com

---

<div align="center">

**Desarrollado con amor para la comunidad crypto**

°Ô **Si te gusta, dale una estrella!**

---

### Disclaimer

Este proyecto es **educativo**. El trading de criptomonedas es riesgoso y puedes perder todo tu capital.

**Usa bajo tu propio riesgo.**
</div>
=======
# Crypto AI Trading Bot

Sistema avanzado de trading automatizado para criptomonedas que combina **an√°lisis t√âcnico** con **inteligencia artificial** (LLMs locales y remotos) para tomar decisiones de trading informadas.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-red.svg)](LICENSE)
[![Binance](https://img.shields.io/badge/Binance-API-yellow.svg)](https://www.binance.com/)

---

## Caracter√≠sticas Principales

### Inteligencia Artificial Flexible
- **Multi-Provider LLM**: Soporte para modelos locales (LM Studio/Ollama) y remotos (OllamaFreeAPI)
- **10+ Modelos Disponibles**: Qwen2.5, Llama3, DeepSeek-R1, Mistral, GPT-OSS, etc.
- **Fallback Autom√°tico**: Si la API remota falla, usa modelo local autom√°ticamente
- **Aprendizaje Continuo**: Valida y aprende de cada decisi√≥n tomada

### An√°lisis T√âcnico Avanzado

| Indicador | Configuraci√≥n | Prop√≥sito |
|-----------|--------------|-----------|
| RSI | 14 per√≠edos | Sobrecompra/sobreventa |
| MACD | 12,26,9 | Momentum y cruces |
| Bollinger Bands | 20,2 | Volatilidad y posici√≥n relativa |
| ATR | 14 per√≠odos | Volatilidad absoluta |
| Stochastic | 14,3 | Momentum corto plazo |
| Volumen | vs SMA 20 | Confirmaci√≥n de movimientos |
| EMA | 9/20 | Regimen de mercado |

### Gesti√≥n de Riesgo
- ‚úÖ Stop Loss configurable (default: 1.0%)
- ‚úÖ Take Profit configurable (default: 2.5%)
- ‚úÖ trailing Stop (opcional)
- ‚úÖ M√°ximo de posiciones simult√°neas
- ‚úÖ Confianza m√≠nima para operar
- ‚úÖ Hard Stop Loss de seguridad (5%)

### y Sistema de Aprendizaje
```
1. IA decide ‚Üí 2. Se ejecuta ‚Üí 3. Se valida ‚Äí 4. Se aprende ‚Äí 5. Mejora pr√≥xima decisi√≥n

```

Cada validaci√≥n genera patrones aprendidos que se inyectan en futuras decisiones.

### Checkpoint & Resume
- **Backtesting**: Si cortas+ La fjecuci√≥n, continu√° desde donde quedaste
- **Live Trading**: Recupera posiciones abiertas al reiniciar
- **Fresh Start**: Opci√≥n `--fresh` para empezar desde cero

---

## Requisitos

### Software
- Python 3.11+
- SQLite3
- LM Studio u Ollama (para modelos locales)
- OllamaFreeAPI (opcional, para modelos remotos gratuitos)

### Hardware Recomendado

| Componente | M√≠n | Recomendado |
|------------|--------|-------------|
| RAM | 8GB | 16GB |
| CPU | 4 cores | 8 cores |
| Almacenamiento | 10GB | 50GB SSD |
| GPU | No requerida | NVIDIA 6GB+ (opcional) |

---

## Instalaci√≥n

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

**Opci√≥n A: OllamaFreeAPI (Gratis, sin hardware local)**
`` `json
{
  "llm_provider": {
    "use_ollama_free": true,
    "ollama_free_model": "gpt-oss:20b",
    "fallback_to_local": true
  }
}
````

**Opci√≥n B: Local (LM Studio)**
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

# Con modelo espec√≠fico
python main.py --backtest --model gpt-oss:20b
```

### Live Trading
```bash
# Modo simulaci√≥n (dry run)
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

## Configuraci√≥n

### Par√°metros Principales (config.json)

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

| Modelo | Tama√±o | Velocidad | Recomendado |
|--------|--------|-----------|--------------|
| gpt-oss:20b | 20B | Lenta | M√°xima calidad |
| deepseek-r1:latest | -7B | ‚öÅ Media | Razonamiento |
| llama3.2:3b | 3B | R√°pida | Testing r√°pido |
| mistral:latest | 7B | ‚öÅ Media | Balance |
| llama3:latest | 8B | ‚öÅ Media | General |

---

## Arquitectura

```
crypto-ai-trading-bot/
‚îú‚îÄ‚îÄ agents/
‚îÇ   ‚îú‚îÄ‚îÄ brain.py              # Cerebro IA
‚îÇ   ‚îú‚îÄ‚îÄ llm_adapter.py        # Adaptador multi-provider
‚îÇ   ‚îî‚îÄ‚îÄ validator.py          # Validaci√≥n
‚îú‚îÄ‚îÄ data/
‚îÇ   ‚îú‚îÄ‚îÄ collector.py          # Datos + indicadores
‚îÇ   ‚îî‚îÄ‚îÄ market_data.db        # OHLCV hist√≥ricos
‚îú‚îÄ‚îÄ execution/
‚îÇ   ‚îî‚îÄ‚îÄ executor.py           # √ìrdenes Binance
‚îú‚îÄ‚îÄ risk/
‚îÇ   ‚îî‚îÄ‚îÄ manager.py            # Gesti√≥n de riesgo
‚îú‚îÄ‚îÄ main.py                   # Punto de entrada
‚îú‚îÄ‚îÄ config.json               # Configuraci√≥n
‚îî‚îÄ‚îÄ requirements.txt          # Dependencias
```

---

## Advertencias de Riesgo

> **IMPORTANTE**: Este software es solo para fines educativos.

- El trading de criptomonedas conlleva **alto riesgo**
- Nunca inviertas m√°s de lo que puedas perder
- El rendimiento pasado **no garantiza** resultados futuros
- prueba en **Testnet/Dry Run** antes de Mainnet
- El autor **no se responsabiliza** por p√©rdidas

### Checklist Antes de Live Trading

| Requisito | Estado M√≠nimo |
|------------|-----------------|
| Backtesting | 50+ trades |
| Win Rate | >55% estable |
| Profit Factor | >1.5 |
| Paper trading | 2-4 semanas |
| Hard Stop Loss | 5% m√°ximo |

---

## Roadmap

- [ ] Dashboard web en tiempo real
- [ ] M√∫ltiples pares simult√°neos
- [ ] Telegram/Discord notifications
- [ ] An√°lisis de sentimiento
- [ ] M√°s exchanges (KuCoin, Bybit)
- [ ] M√£tricas avanzadas (Sharpe, Sortino)

---

## Resultados de Testing

| Modelo | Trades | Win Rate | PnL | Per√≠edo |
|--------|--------|-----------|------|-----------|
| gpt-oss:20b | 40 | 60.0% | -39.7%* | Jan-Mar 2026 |
| qwen2.5-7b | 14 | 69.2% | +6.68% | Jan 2024 |

*Sin optimizaci√≥n de gesti√≥n de riesgo

---

## Licencia

MIT License - Ver `LICENSE` para m√°s informaci√≥n.

---

## Contacto

- **GitHub Issues**: Bugs y features
- **Email**: tuemail@ejemplo.com

---

<div align="center">

**Desarrollado con amor para la comunidad crypto**

‚òÖ **Si te gusta, dale una estrella!**

---

### Disclaimer

Este proyecto es **educativo**. El trading de criptomonedas es riesgoso y puedes perder todo tu capital.

**Usa bajo tu propio riesgo.**
</div>
>>>>>>> fb24ba45e033b337c5e839a7aeb7c5889fd7c793
