# Binance_crypto-ai-agent
Crypto AI Trading Bot - Sistema de Trading Automatizado con IA

Sistema avanzado de trading automatizado para criptomonedas que combina análisis técnico con inteligencia artificial (LLMs locales) para tomar decisiones de trading informadas en tiempo real.
🌟 Características Principales
🤖 Inteligencia Artificial
Modelos LLM locales (Ollama/LM Studio) - Sin dependencia de APIs externas
Aprendizaje continuo - El sistema aprende de cada operación realizada
Análisis contextual - Considera patrones históricos y condiciones de mercado
Múltiples modelos - Soporte para diferentes modelos (Qwen2.5, Llama3.2, DeepSeek)
📊 Análisis Técnico Multi-Timeframe
Timeframe Principal: 1h (análisis detallado)
Timeframe Confirmación: 4h (tendencia general)
Indicadores Implementados:
RSI (14 períodos) - Detección de sobrecompra/sobreventa
EMA 9/20 - Cruce para determinar régimen de mercado
MACD (12,26,9) - Confirmación de momentum
Trend Strength - Fuerza de la tendencia actual
🎯 Gestión de Riesgo Avanzada
Stop Loss dinámico: 1.0% configurable
Take Profit: 1.5% configurable
Órdenes OCO (One-Cancels-Other) - Protección automática
Máximo de slots: Control de posiciones simultáneas
Detección de balance mínimo: Prevención de liquidación
Confianza mínima: 70% para ejecutar operaciones
📈 Backtesting y Live Trading
Backtesting histórico: Datos reales de Binance Mainnet
Live Trading: Ejecución en tiempo real (Testnet/Mainnet)
Modo Dry Run: Simulación sin riesgo
Soporte SPOT y FUTURES: Con apalancamiento configurable
💾 Base de Datos y Persistencia
SQLite para almacenamiento local
Decisiones registradas: Timestamp, dirección, confianza, hipótesis
Outcomes tracking: Entry/Exit, PnL, precisión
Model Stats: Estadísticas agregadas por modelo
🖥️ Dashboard en Tiempo Real
FastAPI backend moderno y rápido
WebSocket para logs en vivo
Visualización de:
Modelos entrenados
Sesiones de trading
Decisiones históricas
Estadísticas de precisión
Posiciones abiertas
Trades recientes
🧠 Sistema de Aprendizaje Automático
Feedback loop: Últimas 3 decisiones en cada análisis
Horizonte temporal: Análisis de precisión a 1h, 4h, 24h
Pattern recognition: Identificación de patrones exitosos/fallidos
Insights automáticos:
Suficiencia de datos
Limitaciones del modelo
Recomendaciones accionables
Brechas de datos
📋 Requisitos
Software
Python 3.11+
SQLite3
Ollama o LM Studio (para LLM local)
Dependencias Python
bash
1
Modelos Recomendados
Qwen2.5-3B (recomendado - balance calidad/rendimiento)
Llama3.2-3B (alternativa)
DeepSeek-R1 (máxima calidad)
🚀 Instalación
Clonar repositorio
bash
12
Configurar variables de entorno
bash
12
Configurar LLM local
bash
12345
Instalar dependencias
bash
1
📖 Uso
Backtesting
bash
1
Live Trading
bash
1
Dashboard
bash
123
⚙️ Configuración
config.json - Parámetros Principales
json
12345678910111213141516171819202122
📊 Estructura del Proyecto
123456789101112131415161718
🔍 Cómo Funciona
Flujo de Decisión
Recolección de Datos: Obtiene velas 1h y 4h de Binance
Cálculo de Indicadores: RSI, EMA, MACD, Trend Strength
Análisis IA: Envía snapshot al LLM con:
Datos técnicos actuales
Últimas 3 decisiones y resultados
Reglas de trading
Decisión: BUY/SELL/HOLD con nivel de confianza
Validación de Riesgo: Verifica:
Confianza >= mínimo configurado
Balance suficiente
Slots disponibles
Ejecución:
Si AUTO_EXIT_ENABLED=false: Coloca órdenes OCO (TP/SL)
Si AUTO_EXIT_ENABLED=true: IA decide cuándo cerrar
Registro: Guarda decisión y outcome en SQLite
Aprendizaje: Próxima decisión incluye feedback
Sistema de Aprendizaje
Cada decisión se almacena con:
Timestamp y contexto de mercado
Dirección (BUY/SELL) y confianza
Indicadores en el momento (RSI, regime, trend)
Resultado (PnL, was_correct)
El sistema analiza:
Precisión por horizonte (1h, 4h, 24h)
Patrones exitosos (ej: BUY con RSI<40 en bullish)
Patrones fallidos (ej: SELL en bullish fuerte)
Calibración de confianza (¿80% confianza = 80% aciertos?)
📈 Métricas y Estadísticas
El dashboard muestra:
Win Rate: % de operaciones ganadoras
PnL Total: Ganancia/pérdida acumulada
Precisión por RSI: Rendimiento por zona de RSI
Precisión por Tendencia: Rendimiento por tipo de tendencia
Buy/Sell Analysis: Comparativa BUY vs SELL
Horizonte Temporal: Precisión a 1h, 4h, 24h
⚠️ Advertencias de Riesgo
IMPORTANTE: Este software es solo para fines educativos y de investigación.
El trading de criptomonedas conlleva alto riesgo de pérdida
Nunca inviertas más de lo que puedas permitirte perder
El rendimiento pasado no garantiza resultados futuros
Prueba exhaustivamente en Testnet antes de usar Mainnet
El autor no se responsabiliza por pérdidas financieras
🤝 Contribuciones
Las contribuciones son bienvenidas:
Fork el proyecto
Crea una rama (git checkout -b feature/AmazingFeature)
Commit tus cambios (git commit -m 'Add AmazingFeature')
Push a la rama (git push origin feature/AmazingFeature)
Abre un Pull Request
📝 Roadmap
Soporte para múltiples pares simultáneos
Estrategias personalizables via YAML
Telegram/Discord notifications
Análisis de sentimiento de noticias
Machine Learning avanzado (scikit-learn)
Optimización de parámetros genética
Soporte para más exchanges (KuCoin, Bybit)
📄 Licencia
Distribuido bajo la licencia MIT. Ver LICENSE para más información.
📞 Contacto
GitHub Issues: Para bugs y feature requests
Discussions: Para preguntas generales
Desarrollado con ❤️ para la comunidad crypto
⭐ Si te gusta este proyecto, dale una estrella!
