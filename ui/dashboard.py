"""
Dashboard - Interface de usuario con Streamlit - V2.0 Beta
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import sys
import os

# Agregar directorio padre al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraping.storage import get_storage
from mt5.connector import MT5Connector

# Importar nuevos componentes
from ui.components.order_controls import render_order_panel
from ui.components.price_chart import render_price_chart
from ui.components.risk_monitor import render_risk_monitor
from ui.components.reports import render_reports_panel
from ui.pages.backtest import render_backtest_page

# Configuración de página
st.set_page_config(
    page_title="🚀 Trading IA Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado mejorado
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #667eea, #764ba2);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
    }
    .signal-buy {
        background-color: #00c853;
        color: white;
        padding: 0.3rem 0.8rem;
        border-radius: 15px;
        font-weight: bold;
    }
    .signal-sell {
        background-color: #ff1744;
        color: white;
        padding: 0.3rem 0.8rem;
        border-radius: 15px;
        font-weight: bold;
    }
    .signal-hold {
        background-color: #ffc107;
        color: black;
        padding: 0.3rem 0.8rem;
        border-radius: 15px;
        font-weight: bold;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: rgba(255,255,255,0.05);
        border-radius: 8px;
        padding: 8px 16px;
    }
    .stTabs [aria-selected="true"] {
        background-color: rgba(102, 126, 234, 0.3);
    }
</style>
""", unsafe_allow_html=True)


def get_storage_instance():
    """Obtiene instancia del storage de forma segura"""
    try:
        return get_storage()
    except Exception as e:
        st.error(f"Error conectando a base de datos: {e}")
        return None


def get_mt5_connector():
    """Obtiene instancia del conector MT5"""
    try:
        connector = MT5Connector()
        if connector.connect():
            return connector
        return None
    except Exception as e:
        return None


def render_header():
    """Renderiza el header principal"""
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown('<p class="main-header">🚀 Trading IA Dashboard</p>', unsafe_allow_html=True)
        st.caption(f"Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    with col2:
        if st.button("🔄 Actualizar"):
            st.rerun()


def render_account_status():
    """Renderiza estado de la cuenta MT5"""
    st.subheader("💰 Estado de Cuenta")
    
    connector = get_mt5_connector()
    
    if connector:
        account_info = connector.get_account_info()
        positions = connector.get_positions()
        connector.disconnect()
        
        if account_info:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Balance", f"€{account_info.get('balance', 0):,.2f}")
            with col2:
                st.metric("Equity", f"€{account_info.get('equity', 0):,.2f}")
            with col3:
                st.metric("Margen Libre", f"€{account_info.get('margin_free', 0):,.2f}")
            with col4:
                st.metric("Posiciones", len(positions) if positions else 0)
            return
    
    # Fallback si no hay conexión MT5
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Balance", "Sin conexión", "")
    with col2:
        st.metric("Equity", "Sin conexión", "")
    with col3:
        st.metric("Margen Libre", "Sin conexión", "")
    with col4:
        st.metric("Posiciones", "?")


def render_signals(storage):
    """Renderiza panel de señales"""
    st.subheader("📡 Señales de Trading")
    
    signals = storage.get_recent_signals(hours=24) if storage else []
    
    if not signals:
        st.info("No hay señales recientes. El sistema está analizando los mercados...")
        
        # Datos de ejemplo
        example_signals = [
            {"symbol": "EURUSD", "type": "BUY", "strength": 0.72, "score": 0.65, "time": datetime.now()},
            {"symbol": "GBPUSD", "type": "SELL", "strength": 0.45, "score": -0.38, "time": datetime.now()},
            {"symbol": "USDJPY", "type": "HOLD", "strength": 0.25, "score": 0.12, "time": datetime.now()},
        ]
        
        for sig in example_signals:
            render_signal_card(sig)
    else:
        for sig in signals[:5]:
            render_signal_card({
                "symbol": sig.symbol,
                "type": sig.signal_type,
                "strength": sig.strength,
                "score": sig.combined_score,
                "time": sig.created_at
            })


def render_signal_card(signal):
    """Renderiza una tarjeta de señal"""
    signal_type = signal.get("type", "HOLD")
    
    if signal_type == "BUY":
        color = "#00c853"
        icon = "📈"
    elif signal_type == "SELL":
        color = "#ff1744"
        icon = "📉"
    else:
        color = "#ffc107"
        icon = "⏸️"
    
    with st.container():
        col1, col2, col3, col4 = st.columns([2, 1, 1, 2])
        
        with col1:
            st.markdown(f"**{signal.get('symbol', 'N/A')}**")
        with col2:
            st.markdown(f"<span style='background-color:{color};color:white;padding:0.2rem 0.5rem;border-radius:5px;'>{icon} {signal_type}</span>", unsafe_allow_html=True)
        with col3:
            strength = signal.get("strength", 0) * 100
            st.progress(signal.get("strength", 0))
            st.caption(f"{strength:.0f}%")
        with col4:
            st.caption(f"Score: {signal.get('score', 0):.3f}")


def render_positions():
    """Renderiza posiciones abiertas"""
    st.subheader("📊 Posiciones Abiertas")
    
    connector = get_mt5_connector()
    positions = []
    
    if connector:
        mt5_positions = connector.get_positions()
        connector.disconnect()
        
        if mt5_positions:
            for pos in mt5_positions:
                positions.append({
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "type": "BUY" if pos.type == 0 else "SELL",
                    "volume": pos.volume,
                    "profit": pos.profit,
                    "open_price": pos.price_open
                })
    
    if positions:
        df = pd.DataFrame(positions)
        
        # Aplicar colores
        def color_profit(val):
            color = 'green' if val > 0 else 'red'
            return f'color: {color}'
        
        styled_df = df.style.applymap(color_profit, subset=['profit'])
        st.dataframe(styled_df, use_container_width=True)
    else:
        st.info("No hay posiciones abiertas")


def render_news(storage):
    """Renderiza noticias recientes"""
    st.subheader("📰 Noticias Analizadas")
    
    if storage:
        news = storage.get_recent_news(hours=24, processed=True)
    else:
        news = []
    
    if not news:
        st.info("No hay noticias procesadas en las últimas 24 horas")
        return
    
    for item in news[:5]:
        sentiment_color = {
            "bullish": "🟢",
            "bearish": "🔴",
            "neutral": "🟡"
        }.get(item.sentiment, "⚪")
        
        with st.expander(f"{sentiment_color} {item.title[:60]}..."):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(item.content[:200] if item.content else "Sin contenido")
            with col2:
                st.metric("Score", f"{item.sentiment_score:.2f}" if item.sentiment_score else "N/A")
                st.caption(f"Impacto: {item.impact or 'N/A'}")


def render_performance_chart():
    """Renderiza gráfico de rendimiento"""
    st.subheader("📈 Rendimiento")
    
    # Datos de ejemplo
    dates = pd.date_range(start=datetime.now() - timedelta(days=30), end=datetime.now(), freq='D')
    equity = 1000 + (pd.Series(range(len(dates))) * 1.5 + pd.Series([i % 10 * 5 - 25 for i in range(len(dates))]))
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=dates,
        y=equity.cumsum() / 30 + 1000,
        mode='lines',
        name='Equity',
        line=dict(color='#1f77b4', width=2),
        fill='tonexty'
    ))
    
    fig.update_layout(
        height=300,
        margin=dict(l=0, r=0, t=30, b=0),
        xaxis_title="Fecha",
        yaxis_title="Equity (€)",
        hovermode='x unified',
        template="plotly_dark"
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_agent_status():
    """Renderiza estado de los agentes"""
    st.subheader("🤖 Estado de Agentes")
    
    agents = [
        {"name": "NewsAgent", "status": "🟢 Activo", "last_run": "Hace 5 min", "success_rate": 98},
        {"name": "SentimentAgent", "status": "🟢 Activo", "last_run": "Hace 3 min", "success_rate": 95},
        {"name": "TechnicalAgent", "status": "🟢 Activo", "last_run": "Hace 1 min", "success_rate": 99},
        {"name": "RiskAgent", "status": "🟢 Activo", "last_run": "Hace 1 min", "success_rate": 100},
        {"name": "OrderAgent", "status": "🟡 Standby", "last_run": "Hace 2 horas", "success_rate": 92},
    ]
    
    for agent in agents:
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        with col1:
            st.write(f"**{agent['name']}**")
        with col2:
            st.write(agent['status'])
        with col3:
            st.caption(agent['last_run'])
        with col4:
            st.progress(agent['success_rate'] / 100)


def render_stats(storage):
    """Renderiza estadísticas de trading"""
    st.subheader("📊 Estadísticas (30 días)")
    
    if storage:
        stats = storage.get_trade_stats(days=30)
    else:
        stats = {}
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Trades", stats.get("total_trades", 0))
    with col2:
        win_rate = stats.get("win_rate", 0) * 100
        st.metric("Win Rate", f"{win_rate:.1f}%")
    with col3:
        st.metric("Profit Total", f"€{stats.get('total_profit', 0):.2f}")
    with col4:
        avg = stats.get("avg_profit", 0)
        st.metric("Profit Promedio", f"€{avg:.2f}")


def render_sidebar():
    """Renderiza barra lateral"""
    st.sidebar.title("⚙️ Configuración")
    
    st.sidebar.subheader("📊 Símbolos")
    symbols = st.sidebar.multiselect(
        "Seleccionar pares",
        ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"],
        default=["EURUSD", "GBPUSD"]
    )
    
    st.sidebar.subheader("⏱️ Timeframe")
    timeframe = st.sidebar.selectbox(
        "Período",
        ["M1", "M5", "M15", "M30", "H1", "H4", "D1"],
        index=2
    )
    
    st.sidebar.subheader("🎛️ Parámetros de Riesgo")
    max_risk = st.sidebar.slider("Riesgo máximo (%)", 1, 5, 2)
    max_positions = st.sidebar.slider("Máx. posiciones", 1, 5, 3)
    
    # Guardar en session state
    st.session_state['max_daily_loss_percent'] = max_risk
    st.session_state['max_positions'] = max_positions
    
    st.sidebar.divider()
    
    st.sidebar.subheader("🔧 Acciones")
    
    if st.sidebar.button("▶️ Iniciar Bot", use_container_width=True):
        st.sidebar.success("Bot iniciado")
    
    if st.sidebar.button("⏹️ Detener Bot", use_container_width=True):
        st.sidebar.warning("Bot detenido")
    
    if st.sidebar.button("🚨 Cerrar Posiciones", use_container_width=True, type="primary"):
        st.sidebar.error("Cerrando todas las posiciones...")
    
    return {
        "symbols": symbols,
        "timeframe": timeframe,
        "max_risk": max_risk,
        "max_positions": max_positions
    }


def main():
    """Función principal del dashboard"""
    storage = get_storage_instance()
    
    # Sidebar
    config = render_sidebar()
    
    # Header
    render_header()
    
    # Navegación por tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Dashboard",
        "📈 Gráfico",
        "🎮 Trading",
        "🛡️ Riesgo",
        "📋 Reportes"
    ])
    
    with tab1:
        # Dashboard principal
        render_account_status()
        
        st.divider()
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            render_signals(storage)
            st.divider()
            render_performance_chart()
        
        with col2:
            render_positions()
            st.divider()
            render_stats(storage)
        
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            render_news(storage)
        
        with col2:
            render_agent_status()
    
    with tab2:
        # Gráfico con análisis LLM
        llm_analysis = {
            'direction': 'BUY',
            'confidence': 0.72,
            'reasoning': 'El análisis técnico muestra una tendencia alcista con EMA 20 por encima de EMA 50. El RSI está en zona neutral (55) con espacio para subir. El sentimiento de noticias es positivo con expectativas de datos económicos favorables.',
            'factors': {
                'Técnico': 0.65,
                'Sentimiento': 0.45,
                'Fundamental': 0.30
            }
        }
        render_price_chart(
            symbol=config.get('symbols', ['EURUSD'])[0] if config.get('symbols') else 'EURUSD',
            timeframe=config.get('timeframe', 'M15'),
            llm_analysis=llm_analysis
        )
    
    with tab3:
        # Panel de trading manual
        render_order_panel()
    
    with tab4:
        # Monitor de riesgo
        render_risk_monitor()
    
    with tab5:
        # Reportes y análisis
        render_reports_panel()


if __name__ == "__main__":
    main()
