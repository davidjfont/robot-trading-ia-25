# 🚀 Sistema Autónomo de Trading con Agentes IA

Sistema completo de trading automatizado que utiliza agentes de IA locales para análisis de sentimiento, señales técnicas y ejecución de órdenes en MetaTrader 5.

> ⚠️ **IMPORTANTE**: Este sistema debe probarse EXCLUSIVAMENTE en **cuenta DEMO** antes de cualquier uso con capital real.

## 📁 Estructura del Proyecto

```
08_BROKER/
├── config.yaml              # Configuración global
├── requirements.txt         # Dependencias Python
├── run.py                   # 🚀 Orquestador principal
├── agents/                  # Agentes de IA
│   ├── llm_provider.py      # Abstracción Ollama/LLM
│   ├── base_agent.py        # Clase base
│   ├── news_agent.py        # Análisis de noticias
│   ├── sentiment_agent.py   # Análisis de sentimiento
│   ├── technical_agent.py   # Análisis técnico
│   └── risk_agent.py        # Gestión de riesgo
├── scraping/                # Recolección de datos
│   ├── base_scraper.py      # Scraper base (Playwright)
│   ├── news_scraper.py      # Scrapers de noticias
│   └── storage.py           # Base de datos SQLite
├── strategies/              # Motor de estrategia
│   ├── indicators.py        # Indicadores técnicos
│   ├── signals.py           # Generador de señales
│   └── combiner.py          # Decisión multi-agente
├── backtester/              # Validación
│   └── engine.py            # Motor de backtesting
├── mt5/                     # MetaTrader 5
│   ├── connector.py         # Conexión MT5
│   └── order_agent.py       # Ejecución de órdenes
├── ui/                      # Interfaz
│   └── dashboard.py         # Dashboard Streamlit
└── data/                    # Datos
    ├── trading.db           # Base de datos
    └── logs/                # Logs del sistema
```

## 🚀 Inicio Rápido

### 1. Activar entorno virtual

```powershell
cd "c:\Users\wishk\Desktop\2026 - Innovation Architect\08_BROKER"
.\venv\Scripts\Activate.ps1
```

### 2. Verificar Ollama y modelo Mistral

```powershell
# Ver modelos disponibles
ollama list

# Si Mistral no está instalado:
ollama pull mistral
```

### 3. Abrir MetaTrader 5

Asegúrate de que MT5 está abierto y conectado a tu cuenta demo.

### 4. Ejecutar el sistema

```powershell
# Opción A: Ejecutar el bot de trading
python run.py

# Opción B: Solo el dashboard
.\venv\Scripts\streamlit.exe run ui/dashboard.py
```

## 🔧 Configuración

Edita `config.yaml` para ajustar:

- **Credenciales MT5**: Cuenta, contraseña, servidor
- **Símbolos**: Pares de divisas a tradear
- **Riesgo**: SL/TP, tamaño máximo, pérdida diaria
- **LLM**: Modelo y parámetros

## 🧠 Arquitectura de Agentes

| Agente | Función |
|--------|---------|
| NewsAgent | Scrapea y analiza noticias |
| SentimentAgent | Scoring de sentimiento con LLM |
| TechnicalAgent | Señales EMA/RSI/MACD |
| RiskAgent | Control de riesgo |
| OrderAgent | Ejecuta órdenes en MT5 |

## 📊 Flujo de Trading

1. **Scraping**: Recolectar noticias cada 15 min
2. **Análisis técnico**: Calcular indicadores
3. **Análisis de sentimiento**: LLM analiza noticias
4. **Decisión**: Combinar señales multi-agente
5. **Validación**: RiskAgent aprueba/rechaza
6. **Ejecución**: OrderAgent envía a MT5

## ⚠️ Seguridad

- El sistema está configurado en **modo DEMO**
- Las órdenes reales están **comentadas** en `run.py`
- Revisa el código antes de habilitar trading real

## 📈 Dashboard

Accede al dashboard en `http://localhost:8501` para ver:
- Señales en tiempo real
- Posiciones abiertas
- Noticias analizadas
- Estado de agentes
- Rendimiento histórico

## 🛠️ Comandos Útiles

```powershell
# Ejecutar tests de módulos individuales
python -m agents.llm_provider
python -m agents.technical_agent
python -m mt5.connector
python -m backtester.engine

# Ver logs
Get-Content data/logs/trading.log -Tail 50
```

## 🖱️ Ejecución Rápida con .BAT

Haz doble clic en **`start.bat`** en la raíz del proyecto para abrir el menú interactivo:

```
╔════════════════════════════════════════════════╗
║     🚀 TRADING BOT - SISTEMA AUTONOMO 🚀      ║
╠════════════════════════════════════════════════╣
║   [1] Iniciar TODO (MT5 + Dashboard + Bot)    ║
║   [2] Solo Dashboard                          ║
║   [3] Solo Bot (requiere MT5 abierto)         ║
║   [4] Salir                                   ║
╚════════════════════════════════════════════════╝
```

> **Nota**: Si MetaTrader 5 está instalado en una ruta diferente, edita `start.bat` y modifica la ruta del `terminal64.exe`.
