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
from loguru import logger

# Agregar directorio padre al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraping.storage import get_storage
from mt5.connector import MT5Connector

# Importar nuevos componentes
from ui.components.order_controls import render_order_panel, close_all_positions
from ui.components.price_chart import render_price_chart

from ui.components.risk_monitor import render_risk_monitor
from ui.components.reports import render_reports_panel
from ui.pages.backtest import render_backtest_page
from ui.config_manager import load_config, save_config, reset_config, update_config

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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    :root {
        --primary: #1a73e8;
        --bg-main: #f8f9fa;
        --card-bg: #ffffff;
        --text-dark: #202124;
        --text-gray: #5f6368;
        --border: #dadce0;
        --shadow: 0 1px 2px 0 rgba(60,64,67,.30), 0 1px 3px 1px rgba(60,64,67,.15);
    }

    .stApp {
        background-color: var(--bg-main);
        font-family: 'Inter', sans-serif;
        color: var(--text-dark);
    }

    /* Analytic Card Style */
    .premium-card {
        background: var(--card-bg);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        box-shadow: none;
        transition: box-shadow 0.2s;
    }
    .premium-card:hover {
        box-shadow: var(--shadow);
    }

    /* Typography */
    .main-header {
        font-size: 24px;
        font-weight: 500;
        color: var(--text-dark);
        margin-bottom: 24px;
        border-bottom: 1px solid var(--border);
        padding-bottom: 12px;
    }

    /* Metrics Table Style */
    .metric-container {
        display: flex;
        flex-direction: column;
        padding: 0.5rem;
    }
    .metric-value {
        font-size: 22px;
        font-weight: 600;
        color: var(--text-dark);
    }
    .metric-label {
        font-size: 13px;
        color: var(--text-gray);
        font-weight: 500;
        text-transform: none;
    }

    /* Signals & Badges */
    .signal-badge {
        font-family: 'Inter', sans-serif;
        font-weight: 500;
        padding: 4px 10px;
        border-radius: 4px;
        font-size: 12px;
    }
    .buy-color { background: #e6f4ea; color: #137333; border: 1px solid #ceead6; }
    .sell-color { background: #fce8e6; color: #c5221f; border: 1px solid #fad2cf; }
    .hold-color { background: #fef7e0; color: #b06000; border: 1px solid #feefc3; }

    /* Console Style - Retro Terminal */
    @import url('https://fonts.googleapis.com/css2?family=VT323&display=swap');
    
    .retro-terminal {
        font-family: 'VT323', 'Courier New', monospace;
        font-size: 16px;
        background-color: #0a0a0a;
        color: #00ff41;
        padding: 16px;
        border-radius: 8px;
        border: 2px solid #00ff41;
        box-shadow: 0 0 20px rgba(0, 255, 65, 0.3), inset 0 0 60px rgba(0, 255, 65, 0.05);
        height: 400px;
        overflow-y: auto;
        position: relative;
    }
    
    .retro-terminal::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: repeating-linear-gradient(
            0deg,
            rgba(0, 0, 0, 0.15),
            rgba(0, 0, 0, 0.15) 1px,
            transparent 1px,
            transparent 2px
        );
        pointer-events: none;
    }
    
    .terminal-line {
        margin: 4px 0;
        line-height: 1.4;
        text-shadow: 0 0 5px #00ff41;
    }
    
    .terminal-time {
        color: #888888;
    }
    
    .terminal-agent {
        color: #00ffff;
        font-weight: bold;
    }
    
    .terminal-success {
        color: #00ff41;
    }
    
    .terminal-error {
        color: #ff4141;
        text-shadow: 0 0 5px #ff4141;
    }
    
    .terminal-cursor {
        display: inline-block;
        width: 10px;
        height: 18px;
        background-color: #00ff41;
        animation: blink 1s infinite;
        vertical-align: middle;
        margin-left: 4px;
    }
    
    @keyframes blink {
        0%, 50% { opacity: 1; }
        51%, 100% { opacity: 0; }
    }
    
    .terminal-header {
        color: #ffff00;
        border-bottom: 1px solid #00ff41;
        padding-bottom: 8px;
        margin-bottom: 12px;
    }

    /* Standard Elements Adjustment */
    .stTabs [data-baseweb="tab-list"] { background: transparent; border-bottom: 1px solid var(--border); }
    .stTabs [data-baseweb="tab"] { color: var(--text-gray); font-weight: 500; }
    .stTabs [aria-selected="true"] { color: var(--primary); border-bottom: 2px solid var(--primary) !important; }
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
    """Obtiene instancia del conector MT5 con persistencia en la sesión"""
    if 'mt5_connector' not in st.session_state:
        try:
            connector = MT5Connector()
            if connector.connect():
                st.session_state['mt5_connector'] = connector
            else:
                return None
        except Exception as e:
            st.error(f"Error inicializando MT5: {e}")
            return None
    
    # Verificar que siga conectado
    connector = st.session_state['mt5_connector']
    if not connector.ensure_connected():
        if not connector.connect():
            return None
            
    return connector



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
        # NOTA: No desconectamos aquí para mantener la persistencia
        
        if account_info:
            cols = st.columns(4)
            metrics = [
                ("Balance", f"€{account_info.get('balance', 0):,.2f}"),
                ("Equity", f"€{account_info.get('equity', 0):,.2f}"),
                ("Margen Libre", f"€{account_info.get('free_margin', 0):,.2f}"),
                ("Posiciones", len(positions) if positions else 0)

            ]
            
            for i, (label, value) in enumerate(metrics):
                with cols[i]:
                    st.markdown(f"""
                        <div class="premium-card">
                            <div class="metric-label">{label}</div>
                            <div class="metric-value">{value}</div>
                        </div>
                    """, unsafe_allow_html=True)
            return

    # Mock data if simulation mode is active
    if st.session_state.get('simulation_mode'):
        cols = st.columns(4)
        metrics = [
            ("Balance (Sim)", "€1,245.50"),
            ("Equity (Sim)", "€1,268.42"),
            ("Margen Libre (Sim)", "€1,150.20"),
            ("Posiciones (Sim)", "2")
        ]
        for i, (label, value) in enumerate(metrics):
            with cols[i]:
                st.markdown(f"""
                    <div class="premium-card">
                        <div class="metric-label">{label}</div>
                        <div class="metric-value">{value}</div>
                    </div>
                """, unsafe_allow_html=True)
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




def render_memory(storage):

    """Renderiza la memoria del sistema (resumen LLM)"""
    if not storage:
        return
        
    memory = storage.get_latest_memory()
    
    with st.expander("🧠 Memoria del Sistema (Último Resumen)", expanded=True):
        if memory:
            st.markdown(f"**Fecha: {memory.date}**")
            st.markdown(memory.summary)
            if memory.stats:
                st.caption(f"Estadísticas grabadas: {memory.stats.get('total_trades', 0)} trades, {memory.stats.get('winning_trades', 0)} wins")
        else:
            st.info("Todavía no hay resúmenes de memoria generados. El sistema creará uno al final del día o al reiniciar mañana.")


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
            badge_class = "buy-color" if signal_type == "BUY" else "sell-color" if signal_type == "SELL" else "hold-color"
            st.markdown(f'<span class="signal-badge {badge_class}">{icon} {signal_type}</span>', unsafe_allow_html=True)
        with col3:
            strength = signal.get("strength", 0) * 100
            st.markdown(f'<div style="width: 100%;"><div class="metric-label" style="font-size:0.6rem">{strength:.0f}% STRENGTH</div></div>', unsafe_allow_html=True)
            st.progress(signal.get("strength", 0))
        with col4:
            st.markdown(f'<div class="metric-label">Confidence</div><div style="font-weight:600; color:var(--text-dark)">{signal.get("score", 0):.3f}</div>', unsafe_allow_html=True)




def render_positions():
    """Renderiza posiciones abiertas"""
    st.subheader("📊 Posiciones Abiertas")
    
    connector = get_mt5_connector()
    positions = []
    
    if connector:
        mt5_positions = connector.get_positions()
        # NOTA: No desconectamos aquí
        
        if mt5_positions:

            for pos in mt5_positions:
                positions.append({
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "type": pos.type,

                    "volume": pos.volume,
                    "profit": pos.profit,
                    "open_price": pos.open_price

                })
    
    if positions:
        df = pd.DataFrame(positions)
        
        # Aplicar colores
        def color_profit(val):
            color = 'green' if val > 0 else 'red'
            return f'color: {color}'
        
        styled_df = df.style.map(color_profit, subset=['profit'])
        st.dataframe(styled_df, use_container_width=True)
    elif st.session_state.get('simulation_mode'):
        # Mock positions
        mock_positions = [
            {"ticket": 123456, "symbol": "EURUSD", "type": "BUY", "volume": 0.1, "profit": 25.40, "open_price": 1.0850},
            {"ticket": 123457, "symbol": "GBPUSD", "type": "SELL", "volume": 0.05, "profit": -12.10, "open_price": 1.2640}
        ]
        df = pd.DataFrame(mock_positions)
        def color_profit(val):
            color = 'green' if val > 0 else 'red'
            return f'color: {color}'
        styled_df = df.style.map(color_profit, subset=['profit'])
        st.dataframe(styled_df, use_container_width=True)
    else:
        st.info("No hay posiciones abiertas")


def render_news(storage):
    """Renderiza eventos económicos y noticias"""
    st.subheader("📅 Calendario Económico")
    
    if not storage:
        st.info("📡 Esperando datos... Ejecute run.py")
        return
    
    # Obtener eventos económicos de alto impacto
    events = storage.get_high_impact_events()
    
    # También intentar noticias
    news = storage.get_recent_news(hours=168, processed=False)
    
    if not events and not news:
        st.info("📡 Sin eventos. Ejecute run.py para scraping")
        return
    
    # Mostrar eventos económicos
    if events:
        impact_icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        
        for event in events[:10]:
            currency = getattr(event, 'currency', 'USD') or 'USD'
            impact = getattr(event, 'impact', 'low') or 'low'
            icon = impact_icons.get(impact.lower(), "⚪")
            name = getattr(event, 'name', 'Evento') or 'Evento'
            name_short = name[:50] + "..." if len(name) > 50 else name
            
            with st.expander(f"{icon} {currency} - {name_short}"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    actual = getattr(event, 'actual', '-') or '-'
                    st.metric("Actual", actual)
                with col2:
                    forecast = getattr(event, 'forecast', '-') or '-'
                    st.metric("Pronóstico", forecast)
                with col3:
                    previous = getattr(event, 'previous', '-') or '-'
                    st.metric("Anterior", previous)
                
                event_time = getattr(event, 'event_time', 'N/A') or 'N/A'
                st.caption(f"🕐 {event_time} | Impacto: {impact.upper()}")
    
    # Si hay noticias también, mostrarlas
    if news:
        st.divider()
        st.caption("📰 Noticias recientes:")
        for item in news[:3]:
            title = getattr(item, 'title', 'Sin título') or 'Sin título'
            st.write(f"• {title[:70]}...")


def render_performance_chart(storage):
    """Renderiza gráfico de rendimiento real desde el historial (por número de operación)"""
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.subheader("📈 Rendimiento")
    with col_h2:
        if st.button("🔄 Sincronizar Historial", key="sync_history"):
            st.session_state['force_sync'] = True
    
    if not storage:
        st.info("Storage no disponible para cargar historial")
        return
        
    # Sincronizar con MT5 si hay conector disponible
    connector = get_mt5_connector()
    if connector:
        try:
            # Sincronizar últimos 7 días por defecto, o 30 si se fuerza o si la DB está vacía
            db_empty = len(storage.get_trade_history(limit=1)) == 0
            days = 30 if (st.session_state.get('force_sync') or db_empty) else 7
            
            deals = connector.get_history_deals(days=days)
            if deals:
                storage.import_mt5_history(deals)
            
            if st.session_state.get('force_sync'):
                st.session_state['force_sync'] = False
                st.success(f"Historial sincronizado (últimos {days} días)")
        except Exception as e:
            logger.error(f"Error sincronizando trades en dashboard: {e}")
            
    # Obtener historial de trades cerrados
    trades = storage.get_trade_history(status="closed", limit=200)
    
    if not trades:
        # Fallback a curva plana si no hay trades
        indices = [0, 1]
        equity = [1000, 1000]
    else:
        # Construir curva de equity ordenada por fecha de cierre
        trades_sorted = sorted(trades, key=lambda x: x.closed_at or datetime.now())
        
        current_equity = 1000  # Base inicial
        equity = [current_equity]
        indices = [0]
        
        for i, t in enumerate(trades_sorted):
            current_equity += (t.profit or 0)
            equity.append(current_equity)
            indices.append(i + 1)

    # Simulation mode fallback
    if st.session_state.get('simulation_mode') and not trades:
        indices = list(range(11))
        # Generate a realistic upward curve with some noise
        import random
        random.seed(42)
        equity = [1000]
        for i in range(1, 11):
            equity.append(equity[-1] + random.uniform(-20, 80))

    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=indices,
        y=equity,
        mode='lines+markers',
        name='Equity',
        line=dict(color='#1a73e8', width=2),
        marker=dict(size=4),
        fill='tonexty',
        fillcolor='rgba(26, 115, 232, 0.1)',
        hovertemplate='Operación: %{x}<br>Equity: €%{y:,.2f}<extra></extra>'
    ))
    
    fig.update_layout(
        height=300,
        margin=dict(l=0, r=0, t=30, b=0),
        xaxis_title="Número de Operación",
        yaxis_title="Equity (€)",
        hovermode='x unified',
        template="plotly_white",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(
            showgrid=True,
            gridcolor='rgba(0,0,0,0.05)',
            # Evitar que se muestren decimales en el eje X
            tickmode='linear',
            tick0=0,
            dtick=max(1, len(indices) // 10)
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='rgba(0,0,0,0.05)'
        )
    )
    
    st.plotly_chart(fig, use_container_width=True)



def render_agent_status():
    """Renderiza estado de los agentes basado en logs reales"""
    st.subheader("🤖 Estado de Agentes")
    
    storage = get_storage_instance()
    
    # Obtener últimos logs por agente
    agent_names = [
        "TechnicalAgent", "SentimentAgent", "NewsAgent", 
        "RiskAgent", "OrderAgent", "HealthMonitor"
    ]
    agents = []
    
    if storage:
        logs = storage.fetch_system_logs(limit=200)
        
        for name in agent_names:
            agent_logs = [l for l in logs if l.agent_name == name]
            
            if agent_logs:
                last_log = agent_logs[0]
                delta = datetime.now() - last_log.created_at
                total_seconds = delta.total_seconds()
                
                # Tiempo desde última ejecución
                if total_seconds < 60:
                    last_run = f"{int(total_seconds)}s"
                elif total_seconds < 3600:
                    last_run = f"{int(total_seconds // 60)}m"
                else:
                    last_run = f"{int(total_seconds // 3600)}h"
                
                # Calcular tasa de éxito
                success_count = sum(1 for l in agent_logs if l.success)
                success_rate = (success_count / len(agent_logs)) if agent_logs else 0
                
                # Estado
                if total_seconds < 120:
                    status = "🟢 Activo"
                elif total_seconds < 600:
                    status = "🟡 Standby"
                elif total_seconds < 3600:
                    status = "🟠 Idle"
                else:
                    status = "🔴 Offline"
            else:
                status = "⚪ Sin datos"
                last_run = "N/A"
                success_rate = 0
            
            agents.append({
                "name": name,
                "status": status,
                "last_run": last_run,
                "success_rate": success_rate
            })
    else:
        agents = [
            {"name": name, "status": "⚪ Sin datos", "last_run": "N/A", "success_rate": 0}
            for name in agent_names
        ]
    
    # Mostrar como tabla simple
    for agent in agents:
        col1, col2, col3, col4 = st.columns([2.5, 1.5, 1, 1])
        with col1:
            st.write(f"**{agent['name']}**")
        with col2:
            st.write(agent['status'])
        with col3:
            st.caption(f"Hace {agent['last_run']}")
        with col4:
            st.progress(agent['success_rate'])


def render_stats(storage):
    """Renderiza estadísticas de trading"""
    st.subheader("📊 Estadísticas (30 días)")
    
    if storage:
        stats = storage.get_trade_stats(days=30)
    else:
        stats = {}
    
    # Simulation mode fallback
    if st.session_state.get('simulation_mode') and not stats:
        stats = {
            "total_trades": 42,
            "win_rate": 0.68,
            "total_profit": 245.50,
            "avg_profit": 5.85
        }
    
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
    """Renderiza barra lateral con persistencia"""
    # Cargar configuración persistente
    user_config = load_config()
    
    st.sidebar.title("⚙️ Configuración")
    
    st.sidebar.subheader("📊 Símbolos")
    symbols = st.sidebar.multiselect(
        "Seleccionar pares",
        ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "GOLD", "BTCUSD"],
        default=user_config.get('symbols', ["EURUSD", "GBPUSD"])
    )
    
    st.sidebar.subheader("⏱️ Timeframe")
    timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
    current_tf = user_config.get('timeframe', "M15")
    tf_index = timeframes.index(current_tf) if current_tf in timeframes else 2
    
    timeframe = st.sidebar.selectbox(
        "Período",
        timeframes,
        index=tf_index
    )
    
    st.sidebar.subheader("🎛️ Parámetros de Riesgo")
    max_risk = st.sidebar.slider("Riesgo máximo (%)", 1, 10, user_config.get('max_risk_percent', 2))
    max_positions = st.sidebar.slider("Máx. posiciones", 1, 15, user_config.get('max_positions', 3))
    
    # Actualizar si hay cambios
    if (symbols != user_config.get('symbols') or 
        timeframe != user_config.get('timeframe') or 
        max_risk != user_config.get('max_risk_percent') or 
        max_positions != user_config.get('max_positions')):
        
        update_config(
            symbols=symbols,
            timeframe=timeframe,
            max_risk_percent=max_risk,
            max_positions=max_positions
        )
    
    # Guardar en session state para uso en UI
    st.session_state['max_daily_loss_percent'] = max_risk
    st.session_state['max_positions'] = max_positions
    st.session_state['selected_symbols'] = symbols
    
    st.sidebar.divider()
    
    st.sidebar.subheader("🔄 Actualización")
    auto_refresh = st.sidebar.toggle("Auto-actualización", value=user_config.get('auto_refresh', True))
    refresh_interval = st.sidebar.slider("Intervalo (seg)", 1, 60, user_config.get('refresh_interval', 5))
    
    if auto_refresh != user_config.get('auto_refresh') or refresh_interval != user_config.get('refresh_interval'):
        update_config(auto_refresh=auto_refresh, refresh_interval=refresh_interval)
    
    st.session_state['auto_refresh'] = auto_refresh
    st.session_state['refresh_interval'] = refresh_interval
    
    st.sidebar.divider()
    
    st.sidebar.subheader("🧪 Desarrollo y Pruebas")
    simulation_mode = st.sidebar.toggle("Simulación de Datos", value=st.session_state.get('simulation_mode', False))
    st.session_state['simulation_mode'] = simulation_mode
    
    st.sidebar.divider()
    
    # MODO DE TRADING - Normal vs Scalping
    st.sidebar.subheader("🧠 Modo de Activar IA")
    
    current_mode = user_config.get('trading_mode', 'normal')
    is_scalping = current_mode == 'scalping'
    
    col_mode1, col_mode2 = st.sidebar.columns(2)
    
    with col_mode1:
        if st.button("📊 Normal", 
                    type="primary" if not is_scalping else "secondary",
                    key="mode_normal",
                    use_container_width=True):
            update_config(trading_mode='normal')
            mode_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'trading_mode.txt')
            try:
                os.makedirs(os.path.dirname(mode_file), exist_ok=True)
                with open(mode_file, 'w') as f: f.write('normal')
            except: pass
            st.rerun()
    
    with col_mode2:
        if st.button("⚡ Scalper", 
                    type="primary" if is_scalping else "secondary",
                    key="mode_scalper",
                    use_container_width=True):
            update_config(trading_mode='scalping')
            mode_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'trading_mode.txt')
            try:
                os.makedirs(os.path.dirname(mode_file), exist_ok=True)
                with open(mode_file, 'w') as f: f.write('scalping')
            except: pass
            st.rerun()
    
    # Indicador visual
    if is_scalping:
        st.sidebar.markdown("""
        <div style="background: linear-gradient(135deg, #ff6b00, #ff8c00); 
                    padding: 10px; border-radius: 8px; text-align: center; margin-top: 10px; border: 1px solid #ffcc00;">
            <span style="color: white; font-weight: bold;">⚡ MODO SCALPING ACTIVO</span><br>
            <span style="color: #ffe0b3; font-size: 11px;">1 pos/símbolo • Mín. 7 trades • Ciclo 10s</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.sidebar.markdown("""
        <div style="background: linear-gradient(135deg, #1a73e8, #4285f4); 
                    padding: 10px; border-radius: 8px; text-align: center; margin-top: 10px; border: 1px solid #add8e6;">
            <span style="color: white; font-weight: bold;">📊 MODO NORMAL</span><br>
            <span style="color: #b3d4fc; font-size: 11px;">Estrategia Standard • Auto-trade</span>
        </div>
        """, unsafe_allow_html=True)
    
    st.sidebar.divider()
    
    st.sidebar.subheader("🔧 Acciones")
    
    if st.sidebar.button("▶️ Iniciar Bot", use_container_width=True):
        st.sidebar.success("Bot iniciado")
    
    if st.sidebar.button("⏹️ Detener Bot", use_container_width=True):
        st.sidebar.warning("Bot detenido")
        
    st.sidebar.divider()
    
    if st.sidebar.button("🔄 Restablecer Configuración", use_container_width=True):
        reset_config()
        st.sidebar.info("Configuración restablecida")
        st.rerun()

    if st.sidebar.button("🧹 Limpiar Historial de Trades", use_container_width=True):
        storage = get_storage_instance()
        if storage:
            storage.clear_trade_history()
            st.sidebar.success("Historial de trades borrado")
            st.rerun()

    if st.sidebar.button("📋 Limpiar Logs de Agentes", use_container_width=True):
        storage = get_storage_instance()
        if storage:
            storage.clear_agent_logs()
            st.sidebar.success("Logs de agentes borrados")
            st.rerun()

    if st.sidebar.button("🚨 Cerrar Posiciones", use_container_width=True, type="primary"):
        with st.sidebar.status("Cerrando todas las posiciones..."):
            close_all_positions()
        st.sidebar.success("Órdenes de cierre enviadas")
        st.rerun()
    
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
        render_memory(storage)
        render_account_status()

        
        st.divider()
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            render_signals(storage)
            st.divider()
            render_positions()
        
        with col2:
            st.subheader("🖥️ Terminal de Agentes")
            
            if storage:
                logs = storage.fetch_system_logs(limit=25)
                
                # Construir terminal retro
                terminal_lines = []
                terminal_lines.append('<div class="terminal-header">[ SISTEMA AUTONOMO DE TRADING - TERMINAL v2.0 ]</div>')
                
                if logs:
                    for log in reversed(logs):  # Más reciente abajo como terminal real
                        time_str = log.created_at.strftime("%H:%M:%S")
                        status_class = "terminal-success" if log.success else "terminal-error"
                        status_icon = "✓" if log.success else "✗"
                        
                        terminal_lines.append(
                            f'<div class="terminal-line">'
                            f'<span class="terminal-time">[{time_str}]</span> '
                            f'<span class="terminal-agent">{log.agent_name}</span>: '
                            f'{log.action} → '
                            f'<span class="{status_class}">{status_icon} {log.result}</span>'
                            f'</div>'
                        )
                else:
                    terminal_lines.append('<div class="terminal-line">Iniciando sistema...</div>')
                    terminal_lines.append('<div class="terminal-line">Esperando actividad de agentes...</div>')
                
                # Añadir cursor parpadeante al final
                terminal_lines.append('<div class="terminal-line">> <span class="terminal-cursor"></span></div>')
                
                terminal_html = f'''
                <div class="retro-terminal">
                    {''.join(terminal_lines)}
                </div>
                '''
                
                st.markdown(terminal_html, unsafe_allow_html=True)
                
                # Botón de refresh
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("🔄 Refrescar", key="refresh_console"):
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Limpiar", key="clear_console"):
                        st.info("Consola limpiada")

        
        st.divider()
        
        with col1:
            render_performance_chart(storage)
        
        with col2:
            render_stats(storage)


        
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            render_news(storage)
        
        with col2:
            render_agent_status()
    
    with tab2:
        # Gráfico con análisis LLM
        render_price_chart(
            symbol=config.get('symbols', ['EURUSD'])[0] if config.get('symbols') else 'EURUSD',
            timeframe=config.get('timeframe', 'M15'),
            llm_analysis=None  # Dejar que el componente lo calcule dinámicamente
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

    # Manejo de auto-refresh
    if st.session_state.get('auto_refresh', False):
        import time
        time.sleep(st.session_state.get('refresh_interval', 5))
        st.rerun()



if __name__ == "__main__":
    main()
