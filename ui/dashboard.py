"""
Dashboard - Interface de usuario con Streamlit - V2.0 Beta
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import pytz
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
from core.symbols import get_all_symbols

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

    /* --- SPA LAYOUT NEW STYLES --- */
    html {
        scroll-behavior: smooth !important;
    }
    
    /* Sticky Navbar */
    .sticky-nav {
        position: fixed;
        top: 3.5rem; /* Ajustado para estar debajo del header de Streamlit */
        left: 0;
        right: 0;
        margin: 0 auto;
        width: 90%;
        max-width: 800px;
        z-index: 99999;
        background: rgba(255, 255, 255, 0.90);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(0,0,0,0.05);
        padding: 10px 20px;
        display: flex;
        gap: 20px;
        justify-content: center;
        border-radius: 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        transition: all 0.3s ease;
    }
    
    /* Spacer to prevent content overlap */
    .nav-spacer {
        height: 60px;
        width: 100%;
    }
    
    .nav-link {
        color: var(--text-gray);
        text-decoration: none;
        font-weight: 600;
        padding: 8px 16px;
        border-radius: 20px;
        transition: all 0.2s ease;
        font-size: 14px;
    }
    
    .nav-link:hover {
        background: rgba(26, 115, 232, 0.1);
        color: var(--primary);
    }
    
    .section-title {
        font-family: 'Inter', sans-serif;
        font-weight: 700;
        font-size: 24px;
        color: var(--primary);
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        gap: 10px;
    }

    /* Bot Status pulsing dot */
    .status-dot {
        height: 10px;
        width: 10px;
        border-radius: 50%;
        display: inline-block;
        margin-right: 8px;
    }
    .dot-running {
        background-color: #00c853;
        box-shadow: 0 0 8px #00c853;
        animation: pulse-green 2s infinite;
    }
    .dot-stopped {
        background-color: #ff1744;
        box-shadow: 0 0 8px #ff1744;
    }
    @keyframes pulse-green {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 200, 83, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(0, 200, 83, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 200, 83, 0); }
    }

    /* Filters Interaction */
    .filter-btn {
        background: #f1f3f4;
        border: 1px solid #dadce0;
        border-radius: 16px;
        padding: 4px 12px;
        font-size: 12px;
        font-weight: 600;
        color: #5f6368;
        cursor: pointer;
        transition: all 0.2s;
    }
    .filter-btn-active {
        background: #e8f0fe;
        border-color: #1a73e8;
        color: #1a73e8;
    }
    .impact-filter-star {
        font-size: 14px;
        cursor: pointer;
        opacity: 0.4;
        transition: opacity 0.2s;
    }
    .impact-filter-active {
        opacity: 1;
    }

    /* --- MARKET NEWS & CALENDAR PREMIUM STYLES --- */
    .news-card {
        background: white;
        border-left: 4px solid var(--primary);
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .news-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    .news-source-tag {
        font-size: 10px;
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 0.5px;
        padding: 2px 6px;
        border-radius: 4px;
        margin-bottom: 6px;
        display: inline-block;
    }
    .source-reuters { background: #fee2e2; color: #991b1b; }
    .source-investing { background: #dcfce7; color: #166534; }
    .source-yahoo { background: #f3e8ff; color: #6b21a8; }
    .source-marketwatch { background: #fef9c3; color: #854d0e; }
    .source-cnbc { background: #dbeafe; color: #1e40af; }
    
    .news-title {
        font-weight: 600;
        font-size: 14px;
        color: var(--text-dark);
        line-height: 1.4;
        margin-bottom: 4px;
    }
    .news-meta {
        font-size: 11px;
        color: var(--text-gray);
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    .impact-glow-high {
        box-shadow: 0 0 12px rgba(255, 75, 75, 0.1);
    }
    
    /* ESTADOS POR TIEMPO - PROFESSIONAL OVERHAUL */
    .status-past { border-left: 5px solid #ff4b4b !important; background: #fff8f8; opacity: 0.85; }
    .status-today { border-left: 5px solid #00c853 !important; background: #f1fff1; font-weight: 500; }
    .status-future { border-left: 5px solid #9c27b0 !important; background: #fdf5ff; }
    .status-tomorrow { border-left: 5px solid #7b1fa2 !important; background: #f3e5f5; }

    .event-ticker-row {
        display: flex;
        align-items: center;
        padding: 10px 16px;
        border-bottom: 1px solid rgba(0,0,0,0.05);
        gap: 12px;
        transition: all 0.2s;
    }
    .event-ticker-row:hover { filter: brightness(0.98); }
    
    .event-time { font-family: 'Courier New', monospace; font-weight: 700; min-width: 130px; font-size: 13px; color: #333; }
    .event-currency { font-weight: 800; color: #111; min-width: 45px; font-size: 14px; }
    .event-name { flex-grow: 1; font-size: 14px; color: #222; }
    .event-impact-dot { width: 10px; height: 10px; border-radius: 50%; }
    
    .countdown-badge {
        font-size: 11px;
        font-weight: 800;
        padding: 3px 8px;
        border-radius: 6px;
        white-space: nowrap;
        text-transform: uppercase;
    }
    .badge-past { background: #fee2e2; color: #991b1b; }
    .badge-today { background: #dcfce7; color: #166534; }
    .badge-future { background: #f3e8ff; color: #6b21a8; }
    .badge-tomorrow { background: #f3e5f5; color: #4a148c; }
""", unsafe_allow_html=True)




def get_storage_instance():
    """Obtiene instancia del storage de forma segura"""
    try:
        return get_storage()
    except Exception as e:
        st.error(f"Error conectando a base de datos: {e}")
        return None


@st.cache_resource
def get_mt5_connector():
    """Obtiene instancia del conector MT5 con persistencia en la sesión"""
    import inspect
    import importlib
    import mt5.connector
    
    # Self-healing: Chequear si la instancia está obsoleta (falta argumento 'from_date')
    if 'mt5_connector' in st.session_state:
        connector = st.session_state['mt5_connector']
        try:
            sig = inspect.signature(connector.get_history_deals)
            if 'from_date' not in sig.parameters:
                st.warning("Detectada versión antigua del conector. Recargando...")
                try:
                    connector.disconnect()
                except:
                    pass
                del st.session_state['mt5_connector']
                # Force module reload to ensure we have new code
                importlib.reload(mt5.connector)
        except Exception as e:
            logger.warning(f"Error verificando firma de conector: {e}")

    if 'mt5_connector' not in st.session_state:
        try:
            # Reload module to be safe
            importlib.reload(mt5.connector)
            from mt5.connector import MT5Connector
            connector = MT5Connector()
            if connector.connect():
                st.session_state['mt5_connector'] = connector
            else:
                return None
        except Exception as e:
            st.error(f"Error inicializando MT5: {e}")
            return None
    return st.session_state['mt5_connector']

# --- CACHED DATA FETCHERS ---
@st.cache_data(ttl=5)
def get_cached_logs(_storage, limit=25):
    return _storage.fetch_system_logs(limit=limit)

@st.cache_data(ttl=60)
def get_cached_news(_storage):
    return _storage.get_recent_news(hours=24, limit=40)

@st.cache_data(ttl=10)
def get_cached_signals(_storage):
    # get_recent_signals usa 'hours' y 'symbol', no limit. Traemos últimos 24h y cortamos lista
    signals = _storage.get_recent_signals(hours=24)
    return signals[:5] if signals else []

@st.cache_data(ttl=60)
def get_cached_trade_history(_storage):
    return _storage.get_all_trade_results()

@st.cache_data(ttl=600)
def get_cached_events(_storage):
    # Ya gestionamos el límite dentro del storage para Ayer-Hoy-Mañana
    return _storage.get_high_impact_events()

# ---------------------------




def render_header():
    """Renderiza el header principal"""
    config = load_config()
    is_running = config.get('bot_running', False)
    status_color = "#00c853" if is_running else "#ff1744"
    status_label = "BOT ONLINE" if is_running else "BOT OFFLINE"
    dot_class = "dot-running" if is_running else "dot-stopped"

    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown(f'''
            <div style="display: flex; align-items: center; gap: 15px;">
                <p class="main-header" style="margin-bottom: 0; border: none; padding-bottom: 0;">🚀 Trading IA Dashboard</p>
                <div style="background: {status_color}22; color: {status_color}; padding: 4px 12px; border-radius: 20px; 
                            font-size: 12px; font-weight: 800; border: 1px solid {status_color}44; display: flex; align-items: center;">
                    <span class="status-dot {dot_class}" style="margin-right: 6px; width: 8px; height: 8px;"></span>
                    {status_label}
                </div>
            </div>
        ''', unsafe_allow_html=True)
        st.caption(f"Última actualización: {datetime.now().strftime('%d/%m %H:%M:%S')}")
    
    with col2:
        if st.button("🔄 Actualizar", width='stretch'):
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
            cols = st.columns(3)
            metrics = [
                ("Balance", f"€{account_info.get('balance', 0):,.2f}"),
                ("Equity", f"€{account_info.get('equity', 0):,.2f}"),
                ("Margen Libre", f"€{account_info.get('free_margin', 0):,.2f}")
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
    """Renderiza panel de señales con vista estable por símbolo"""
    st.subheader("📡 Señales de Trading")
    
    # Obtener símbolos activos
    selected_symbols = st.session_state.get('selected_symbols', ["EURUSD", "GBPUSD"])
    if not selected_symbols:
        st.info("Seleccione al menos un símbolo en la barra lateral para ver su estado.")
        return

    # Obtener señales reales
    db_signals = get_cached_signals(storage) if storage else []
    
    # Mapear señales a símbolos (la más reciente por símbolo)
    signal_map = {}
    for sig in db_signals:
        if sig.symbol not in signal_map:
            signal_map[sig.symbol] = sig

    # Renderizar tarjetas
    for symbol in selected_symbols:
        sig = signal_map.get(symbol)
        
        if sig:
            # Renderizar señal real
            render_signal_card({
                "symbol": sig.symbol,
                "type": sig.signal_type,
                "strength": sig.strength,
                "score": sig.combined_score,
                "time": sig.created_at,
                "extra_data": getattr(sig, 'extra_data', {})
            })
        else:
            # Fallback a HOLD/NEUTRAL profesional
            render_signal_card({
                "symbol": symbol,
                "type": "HOLD",
                "strength": 0.05,
                "score": 0.0,
                "time": datetime.now(),
                "reasoning": "Esperando configuración óptima de indicadores técnicos y sentimiento."
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
        col1, col2, col3, col4 = st.columns([2, 1.5, 1, 1.5])
        
        # Calculate Trend/Arrows first
        score = signal.get("score", 0)
        if score > 0.6: arrows = "🟢🟢 Strong"
        elif score > 0.2: arrows = "🟢 Bias"
        elif score < -0.6: arrows = "🔴 Strong"
        elif score < -0.2: arrows = "🔴🔴 Bias"
        else: arrows = "🟦 Neutral"

        with col1:
            st.markdown(f"**{signal.get('symbol', 'N/A')}**")
        with col2:
            badge_class = "buy-color" if signal_type == "BUY" else "sell-color" if signal_type == "SELL" else "hold-color"
            # Display Badge AND Trend
            st.markdown(f'''
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="signal-badge {badge_class}">{icon} {signal_type}</span>
                    <span style="font-size: 12px; color: #666;">{arrows}</span>
                </div>
            ''', unsafe_allow_html=True)
        with col3:
            strength = signal.get("strength", 0) * 100
            st.markdown(f'<div style="width: 100%;"><div class="metric-label" style="font-size:0.6rem">{strength:.0f}% STR</div></div>', unsafe_allow_html=True)
            st.progress(signal.get("strength", 0))
        with col4:
            st.markdown(f'<div class="metric-label">Confidence</div><div style="font-weight:600; color:var(--text-dark)">{signal.get("score", 0):.3f}</div>', unsafe_allow_html=True)
            
            # Show reasoning if available (moved from below)
            if "reasoning" in signal:
                with st.expander("📝", expanded=False):
                    st.write(signal["reasoning"])
            elif "extra_data" in signal and signal["extra_data"]:
                 with st.expander("📝", expanded=False):
                    st.json(signal["extra_data"])




def render_positions():
    """Renderiza posiciones abiertas con control Snake"""
    st.subheader("📊 Posiciones & Snake Manager")
    
    storage = get_storage_instance()
    connector = get_mt5_connector()
    positions = []
    
    # Obtener sesiones activas de Snake
    active_snakes = {}
    if storage:
        sessions = storage.get_active_snake_sessions()
        for s in sessions:
            active_snakes[s.ticket] = s

    if connector:
        mt5_positions = connector.get_positions()
        if mt5_positions:
            for p in mt5_positions:
                positions.append(p)
    elif st.session_state.get('simulation_mode'):
        # Mock positions as objects
        class MockPos:
            def __init__(self, ticket, symbol, type_, volume, profit, open_price):
                self.ticket = ticket
                self.symbol = symbol
                self.type = type_
                self.volume = volume
                self.profit = profit
                self.open_price = open_price
        
        positions = [
            MockPos(123456, "EURUSD", 0, 1.0, 25.40, 1.0850),
            MockPos(123457, "GBPUSD", 1, 0.5, -12.10, 1.2640)
        ]

    if not positions:
        st.info("No hay posiciones abiertas")
        return

    # Initialize notified trades set
    if 'notified_trades' not in st.session_state:
        st.session_state['notified_trades'] = set()

    # Renderizar lista de tarjetas
    for i, pos in enumerate(positions):
        ticket = pos.ticket
        symbol = pos.symbol
        # MT5 type: 0=BUY, 1=SELL
        type_str = "BUY" if (pos.type == 0 or pos.type == "BUY") else "SELL"
        profit = pos.profit
        
        profit_color = "#00c853" if profit >= 0 else "#ff1744"
        bg_color = "rgba(0, 200, 83, 0.1)" if profit >= 0 else "rgba(255, 23, 68, 0.1)"
        
        with st.container():
            col_info, col_snake = st.columns([3, 2])
            
            with col_info:
                st.markdown(f"""
                <div style="border-left: 4px solid {profit_color}; padding: 10px; background: {bg_color}; border-radius: 4px; margin-bottom: 5px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <span style="font-weight:700; font-size:16px;">{symbol}</span>
                            <span style="font-size:12px; color:#666;">#{ticket}</span>
                            <br>
                            <span style="color:{profit_color}; font-weight:600;">{type_str}</span> 
                            <span style="font-size:13px;">x{pos.volume}</span>
                        </div>
                        <div style="text-align:right;">
                            <span style="font-size:18px; font-weight:700; color:{profit_color};">
                                {profit:+.2f}
                            </span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            with col_snake:
                if ticket in active_snakes:
                    session = active_snakes[ticket]
                    
                    # Calcular tiempo restante
                    elapsed = (datetime.now() - session.start_time).total_seconds()
                    remaining = max(0, session.duration_seconds - elapsed)
                    progress = min(elapsed / session.duration_seconds, 1.0)
                    
                    st.caption(f"🐍 Snake Active: {remaining:.0f}s left")
                    st.progress(progress)
                else:
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        # Selector de tiempos extendido
                        options_map = {
                            1: "1s", 10: "10s", 30: "30s", 60: "1m", 
                            300: "5m", 600: "10m", 1800: "30m", 3600: "1h", 14400: "4h"
                        }
                        
                        duration = st.selectbox(
                            "⏱️", 
                            options=list(options_map.keys()), 
                            format_func=lambda x: options_map[x], 
                            key=f"snake_t_{ticket}",
                            label_visibility="collapsed"
                        )
                    with c2:
                        if st.button("🐍 Go", key=f"snake_k_{ticket}", type="secondary", width='stretch'):
                            if storage:
                                storage.create_snake_session(ticket, symbol, duration, pos.open_price, profit)
                                st.rerun()


def render_news(storage):
    """Renderiza eventos económicos y noticias con diseño premium y deduplicación"""
    if not storage:
        st.info("📡 Esperando datos... Ejecute run.py")
        return

    # Usar pestañas para organizar
    tab_calendar, tab_news = st.tabs(["📅 Calendario Maestro", "📰 Pulso del Mercado (Live)"])
    
    with tab_calendar:
        col_c1, col_c2, col_c3 = st.columns([2, 2, 1])
        with col_c1:
            st.markdown("### 🗓️ Eventos de Impacto")
        
        # Filtros de persistencia en session_state
        if 'cal_filter_day' not in st.session_state: st.session_state.cal_filter_day = ["HOY"]
        if 'cal_filter_impact' not in st.session_state: st.session_state.cal_filter_impact = [1, 2, 3]

        with col_c2:
            fcols = st.columns(3)
            days = ["AYER", "HOY", "MAÑANA"]
            for i, d in enumerate(days):
                active = d in st.session_state.cal_filter_day
                if fcols[i].button(d, key=f"btn_day_{d}", width='stretch', 
                                 type="primary" if active else "secondary"):
                    if active:
                        if len(st.session_state.cal_filter_day) > 1:
                            st.session_state.cal_filter_day.remove(d)
                    else:
                        st.session_state.cal_filter_day.append(d)
                    st.rerun()
            
            sc1, sc2, sc3 = st.columns(3)
            stars = ["⭐", "⭐⭐", "⭐⭐⭐"]
            for i in range(3):
                with [sc1, sc2, sc3][i]:
                    active = (i+1) in st.session_state.cal_filter_impact
                    if st.button(stars[i], key=f"btn_star_{i+1}", width='stretch',
                               type="primary" if active else "secondary"):
                        if active:
                            if len(st.session_state.cal_filter_impact) > 1:
                                st.session_state.cal_filter_impact.remove(i+1)
                        else:
                            st.session_state.cal_filter_impact.append(i+1)
                        st.rerun()

        with col_c3:
            if st.button("🚀 Scrape Now", key="scrape_events_now", width='stretch'):
                with st.spinner("Scrapeando nuevas fuentes..."):
                    import subprocess
                    try:
                        subprocess.Popen([sys.executable, "force_scrape.py"])
                        st.success("Scrapeo iniciado en segundo plano")
                        get_cached_events.clear()
                    except Exception as e:
                        st.error(f"Error al iniciar scrapeo: {e}")
            
            if st.button("🔄 Refrescar", key="refresh_events", width='stretch'):
                get_cached_events.clear()
                st.rerun()
        
        events = get_cached_events(storage)
        if not events:
            st.info("No hay eventos programados para hoy.")
        else:
            # DEDUPLICACIÓN AGRESIVA EN UI
            unique_events = {}
        if not events:
            st.info("No hay eventos programados (Ayer-Hoy-Mañana).")
        else:
            # 1. NORMALIZACIÓN Y PROCESAMIENTO (AYER-HOY-MAÑANA)
            madrid_tz = pytz.timezone('Europe/Madrid')
            now_madrid = datetime.now(tz=madrid_tz)
            
            # Límites de ventana (Día completo)
            yesterday_start = (now_madrid - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow_end = (now_madrid + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999)
            
            processed_data = []
            seen_signatures = set()

            for ev in events:
                time_val = getattr(ev, 'event_time', '')
                if not time_val: continue
                
                try:
                    # Parsing flexible
                    dt_event = None
                    ts_str = str(time_val).lower().strip()
                    scraped_at = getattr(ev, 'scraped_at', now_madrid.replace(tzinfo=None))
                    
                    # Normalizar scraped_at a Madrid
                    dt_scraped = pytz.utc.localize(scraped_at).astimezone(madrid_tz) if scraped_at.tzinfo is None else scraped_at.astimezone(madrid_tz)

                    if hasattr(time_val, 'strftime'):
                        dt_event = time_val
                    elif 'min' in ts_str or 'ahora' in ts_str or 'now' in ts_str:
                        # Caso especial: tiempo relativo
                        # Solo es válido si se scrapeó hace poco (< 24h)
                        if (now_madrid - dt_scraped).total_seconds() > 86400:
                            continue # Stale relative time
                            
                        # Extraer minutos si existen
                        import re
                        match = re.search(r'(\d+)', ts_str)
                        if match:
                            mins = int(match.group(1))
                            dt_event = dt_scraped + timedelta(minutes=mins)
                        else:
                            dt_event = dt_scraped 
                    else:
                        ts_str_clean = ts_str.replace('z', '+00:00').upper()
                        try:
                            if ' ' in ts_str_clean and '/' in ts_str_clean:
                                dt_event = datetime.strptime(ts_str_clean, "%Y/%m/%d %H:%M:%S")
                            else:
                                dt_event = datetime.fromisoformat(ts_str_clean)
                        except:
                            # Fallback final: No podemos determinar la hora
                            continue
                    
                    if dt_event.tzinfo is None:
                        dt_event = pytz.utc.localize(dt_event)
                    
                    dt_mad = dt_event.astimezone(madrid_tz)
                    
                    # FILTRO DE VENTANA (Ayer, Hoy, Mañana)
                    if not (yesterday_start <= dt_mad <= tomorrow_end):
                        continue
                        
                    # DEDUPLICACIÓN ESTRICTA (Minuto a minuto)
                    # Usamos H:M para evitar que micro-segundos generen duplicados falsos
                    sig = f"{ev.name}_{ev.currency}_{dt_mad.strftime('%Y-%m-%d %H:%M')}"
                    if sig in seen_signatures: continue
                    seen_signatures.add(sig)
                    
                    # LÓGICA DE ESTADOS Y COLORES
                    status = ""
                    time_display = ""
                    countdown_text = ""
                    badge_class = ""
                    
                    diff_min = int((dt_mad - now_madrid).total_seconds() / 60)
                    is_today = dt_mad.date() == now_madrid.date()
                    is_yesterday = dt_mad.date() == (now_madrid - timedelta(days=1)).date()
                    is_tomorrow = dt_mad.date() == (now_madrid + timedelta(days=1)).date()
                    
                    if diff_min < -10:
                        status = "status-past"
                        time_display = dt_mad.strftime('%H:%M')
                        countdown_text = f"Hace {abs(diff_min)//60}h" if abs(diff_min) > 60 else f"Hace {abs(diff_min)}m"
                        if not is_today:
                            time_display = dt_mad.strftime('%m/%d %H:%M')
                        badge_class = "badge-past"
                    elif -10 <= diff_min <= 0:
                        status = "status-today"
                        time_display = dt_mad.strftime('%H:%M')
                        countdown_text = "AHORA"
                        badge_class = "badge-today"
                    elif diff_min > 0 and is_today:
                        status = "status-today"
                        time_display = dt_mad.strftime('%H:%M')
                        countdown_text = f"En {diff_min} min" if diff_min < 60 else f"En {diff_min//60}h"
                        badge_class = "badge-today"
                    else:
                        status = "status-tomorrow" if is_tomorrow else "status-future"
                        time_display = dt_mad.strftime('%m/%d - %H:%M')
                        countdown_text = f"En {diff_min//60}h"
                        badge_class = "badge-tomorrow" if is_tomorrow else "badge-future"

                    processed_data.append({
                        'obj': ev,
                        'dt': dt_mad,
                        'status': status,
                        'time_display': time_display,
                        'countdown': countdown_text,
                        'badge_class': badge_class,
                        'impact': (ev.impact or 'low').lower()
                    })
                except Exception as e:
                    logger.error(f"Error procesando evento calendario: {e}")
                    continue

            # 2. FILTRAR POR USER SELECTION
            f_day = st.session_state.cal_filter_day
            f_impact = st.session_state.cal_filter_impact
            
            filtered_data = []
            for item in processed_data:
                # Mapeo de impacto a número
                imp_num = 3 if item['impact'] == "high" else 2 if item['impact'] == "medium" else 1
                if imp_num not in f_impact: continue
                
                # Filtro de día (Soporta múltiple selección)
                dt_mad = item['dt']
                day_match = False
                if "HOY" in f_day and dt_mad.date() == now_madrid.date(): day_match = True
                if "AYER" in f_day and dt_mad.date() == (now_madrid - timedelta(days=1)).date(): day_match = True
                if "MAÑANA" in f_day and dt_mad.date() == (now_madrid + timedelta(days=1)).date(): day_match = True
                
                if not day_match: continue
                filtered_data.append(item)

            # 3. ORDENAR Y DEDUPLICAR TÍTULOS (Opcional: Agrupar si son el mismo)
            filtered_data.sort(key=lambda x: x['dt'])
            
            last_title = None
            last_date = None
            
            # Helper para nombres de días en español
            dias_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            meses_es = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

            # 4. RENDERIZAR
            for item in filtered_data:
                ev = item['obj']
                dt_mad = item['dt']
                
                # HEADERS DE FECHA (Estilo Mockup)
                current_date = dt_mad.date()
                if current_date != last_date:
                    dia_semana = dias_es[dt_mad.weekday()]
                    mes = meses_es[dt_mad.month - 1]
                    
                    label = ""
                    if current_date == now_madrid.date(): label = " - HOY"
                    elif current_date == (now_madrid - timedelta(days=1)).date(): label = " - AYER"
                    elif current_date == (now_madrid + timedelta(days=1)).date(): label = " - MAÑANA"
                    
                    header_text = f"{dia_semana.upper()}, {dt_mad.day} {mes.upper()}{label}"
                    st.markdown(f'<div style="background: #f1f3f4; padding: 10px 16px; border-left: 5px solid #1a73e8; margin-top: 20px; margin-bottom: 10px; font-weight: 800; color: #202124; font-size: 14px; letter-spacing: 0.5px; border-radius: 4px;">'
                                f'{header_text}'
                                f'</div>', unsafe_allow_html=True)
                    last_date = current_date
                    last_title = None # Reset title grouping on new day

                # Si el título se repite exactamente igual al anterior, lo atenuamos o simplificamos
                is_duplicate = (ev.name == last_title)
                last_title = ev.name
                
                display_name = f'<span style="opacity: 0.5;">↳</span> {ev.name}' if is_duplicate else ev.name
                
                impact_raw = item['impact']
                if impact_raw == "high": stars = "⭐⭐⭐"; dot_color = "#ff4b4b"
                elif impact_raw == "medium": stars = "⭐⭐"; dot_color = "#ffa500"
                else: stars = "⭐"; dot_color = "#4fc3f7"
                
                glow = "impact-glow-high" if impact_raw == "high" else ""
                
                # Resultado final (Actual / Forecast / Prev)
                results_html = ""
                if ev.actual:
                    # Comparar actual con forecast si existe
                    try:
                        # Limpieza básica para comparación numérica
                        def clean_val(v):
                            if not v: return 0.0
                            s = str(v).replace('%','').replace('K','').replace('M','').replace(',','').replace('B','').strip()
                            return float(s) if s else 0.0
                            
                        act_f = clean_val(ev.actual)
                        for_f = clean_val(ev.forecast) if ev.forecast else act_f
                        res_color = "#137333" if act_f >= for_f else "#c5221f"
                    except:
                        res_color = "#444"
                    
                    prev_disp = f'<span style="color: #666; font-weight: 400; font-size: 11px;" title="Prev">[{ev.previous or "-"}]</span>' if ev.previous else ""
                    
                    results_html = f'<div style="display: flex; gap: 8px; font-size: 13px; font-weight: 700; justify-content: flex-end; align-items: center;"><span style="color: {res_color};" title="Actual">{ev.actual}</span><span style="color: #777; font-weight: 400; font-size: 12px;" title="Forecast">({ev.forecast or "-"})</span>{prev_disp}</div>'
                else:
                    prev_disp = f'<span style="color: #aaa; font-size: 10px;">[{ev.previous or "-"}]</span>' if ev.previous else ""
                    results_html = f'<div style="text-align: right; display: flex; gap: 6px; justify-content: flex-end; align-items: center;"><span style="color: #999; font-size: 11px;">{ev.forecast or "-"} (exp)</span>{prev_disp}</div>'

                st.markdown(f'<div class="event-ticker-row {item["status"]} {glow}">'
                            f'<div class="event-time" title="MADRID: {item["time_display"]}">🕒 {item["time_display"]}</div>'
                            f'<div style="min-width: 90px;"><span class="countdown-badge {item["badge_class"]}">{item["countdown"]}</span></div>'
                            f'<div class="event-impact-dot" style="background: {dot_color};"></div>'
                            f'<div style="font-size: 11px; min-width: 55px; white-space: nowrap;">{stars}</div>'
                            f'<div class="event-currency" style="width: 40px; font-weight: bold;">{ev.currency or "USD"}</div>'
                            f'<div class="event-name" style="{"opacity: 0.7;" if is_duplicate else ""}">{display_name}</div>'
                            f'<div style="min-width: 120px;">{results_html}</div>'
                            f'</div>', unsafe_allow_html=True)

    with tab_news:
        col_n1, col_n2 = st.columns([3, 1])
        with col_n1:
            st.markdown("### 📡 Noticias Institucionales (Layered)")
        with col_n2:
            if st.button("🔄 Actualizar", key="refresh_news_live"):
                get_cached_news.clear()
                st.rerun()
        
        news_items = get_cached_news(storage)
        if not news_items:
            st.info("Sin noticias recientes. El scraper está en modo escucha...")
        else:
            # DEDUPLICACIÓN POR TÍTULO
            unique_news = {}
            for item in news_items:
                title_slug = item.title.strip().lower()[:100]
                if title_slug not in unique_news:
                    unique_news[title_slug] = item
            
            # Mostrar últimos 15
            display_news = list(unique_news.values())[:15]
            
            for item in display_news:
                source = (item.source or 'generic').lower()
                
                # Localizar tiempo de noticia a Madrid
                madrid_tz = pytz.timezone('Europe/Madrid')
                ts = item.scraped_at if hasattr(item, 'scraped_at') else datetime.utcnow()
                if ts.tzinfo is None:
                    ts = pytz.utc.localize(ts)
                ts_madrid = ts.astimezone(madrid_tz)
                time_display = ts_madrid.strftime('%d/%m %H:%M')
                
                st.markdown(f"""
                <div class="news-card">
                    <span class="news-source-tag source-{source}">{source}</span>
                    <div class="news-title">{item.title}</div>
                    <div class="news-meta">
                        <span>🕒 {time_display}</span>
                        <a href="{item.url}" target="_blank" style="text-decoration: none; color: var(--primary); font-weight: 600;">Leer →</a>
                    </div>
                </div>
                """, unsafe_allow_html=True)


def render_performance_chart(storage):
    """Renderiza gráfico de rendimiento real desde el historial (por número de operación)"""
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.subheader("📈 Rendimiento")
    
    if not storage:
        st.info("Storage no disponible para cargar historial")
        return
        
    # --- Sync & Reset Controls ---
    with st.expander("⚙️ Opciones de Historial (Sincronización y Reset)", expanded=False):
        c1, c2, c3 = st.columns([1.5, 1, 1])
        
        with c1:
            # Date Picker for custom sync
            default_date = datetime.now() - timedelta(days=30)
            sync_date = st.date_input("Sincronizar desde:", value=default_date)
            
        with c2:
            st.write("") # Spacer
            st.write("") 
            if st.button("🔄 Sincronizar Selección"):
                st.session_state['force_sync_date'] = sync_date
                st.session_state['force_sync_type'] = "date"
        
        with c3:
            st.write("") # Spacer
            st.write("")
            if st.button("🌍 Sincronizar TOTAL"):
                st.session_state['force_sync_type'] = "all"
        
        st.divider()
        c_diag1, c_diag2 = st.columns([1, 1])
        with c_diag1:
            if st.button("🔍 Diagnosticar Salud de DB", use_container_width=True):
                connector = get_mt5_connector()
                with st.spinner("Analizando base de datos..."):
                    health = storage.run_health_check(connector=connector)
                    st.session_state['db_health'] = health
        
        with c_diag2:
            if st.button("🛠️ Sincronización PROFUNDA", type="secondary", use_container_width=True):
                # Forzar 60 días para cubrir cualquier hueco
                st.session_state['force_sync_days'] = 60
                st.session_state['force_sync_type'] = "deep"

        # Mostrar resultados del diagnóstico si existen
        if 'db_health' in st.session_state:
            h = st.session_state['db_health']
            cols = st.columns(4)
            cols[0].metric("Físico", "✅ OK" if h['is_physically_ok'] else "❌ ERROR")
            cols[1].metric("Duplicados", h['duplicates'])
            cols[2].metric("Huérfanos", h['orphans'])
            cols[3].metric("Desfase MT5", "⚠️ SI" if h['sync_gap_detected'] else "✅ NO")
            
            if h['sync_gap_detected'] or h['orphans'] > 0:
                st.warning("⚠️ Se han detectado inconsistencias. Se recomienda 'Sincronización PROFUNDA'.")
        
        st.divider()
        if st.button("🗑️ RESETEAR / PONER A CERO", type="primary"):
            storage.clear_trade_history()
            st.cache_data.clear()
            st.success("Historial eliminado completamente.")
            st.rerun()

    # --- Sync Logic Execution ---
    connector = get_mt5_connector()
    sync_type = st.session_state.get('force_sync_type')
    
    if connector and sync_type:
        try:
            deals = []
            if sync_type == "all":
                # Sync last 365 days
                deals = connector.get_history_deals(days=365)
                msg = "Historial TOTAL (365 días) sincronizado."
            elif sync_type == "date":
                # Sync from specific date
                f_date = st.session_state.get('force_sync_date')
                if f_date:
                    # Convert date to datetime
                    dt_start = datetime.combine(f_date, datetime.min.time())
                    deals = connector.get_history_deals(from_date=dt_start)
                    msg = f"Historial desde {f_date} sincronizado."
            elif sync_type == "deep":
                # Deep sync 60 days
                deals = connector.get_history_deals(days=60)
                msg = "Sincronización PROFUNDA (60 días) completada."
            
            # Normal cleanup logic
            if deals:
                storage.import_mt5_history(deals, connector=connector)
                st.success(msg)
                # Clear trigger
                st.session_state['force_sync_type'] = None
                st.cache_data.clear()
                st.rerun()
            else:
                st.warning("No se encontraron trades en el periodo seleccionado en MT5.")
                st.session_state['force_sync_type'] = None
                
        except Exception as e:
            logger.error(f"Error sincronizando trades: {e}")
            st.error(f"Error de sincronización: {e}")
            
            
    # Obtener historial de trades cerrados
    trades = get_cached_trade_history(storage)
    
    if not trades:
        # Fallback a curva plana si no hay trades
        indices = [0, 1]
        equity = [1000, 1000]
    else:
        # Construir curva de equity ordenada por fecha de cierre
        trades_sorted = sorted(trades, key=lambda x: x.close_time or datetime.now())
        
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
    
    st.plotly_chart(fig, width='stretch')



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
        logs = get_cached_logs(storage, limit=200)
        
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
        # Optimización: Calcular stats desde historial cacheado pa ahorrar DB calls
        trades = get_cached_trade_history(storage)
        
        if trades:
            total = len(trades)
            wins = sum(1 for t in trades if t.profit > 0)
            total_profit = sum(t.profit for t in trades)
            win_rate = wins / total if total > 0 else 0
            avg = total_profit / total if total > 0 else 0
            
            stats = {
                "total_trades": total,
                "win_rate": win_rate,
                "total_profit": total_profit,
                "avg_profit": avg
            }
        else:
            stats = {}
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
        get_all_symbols(),
        default=user_config.get('symbols', get_all_symbols()[:2])
    )
    
    # Active Symbol for Charts (Single Select)
    st.sidebar.subheader("📈 Símbolo Activo (Gráfico)")
    active_symbol = st.sidebar.selectbox(
        "Ver Gráfico",
        symbols if symbols else ["EURUSD"],
        index=0 if symbols else 0,
        key="active_symbol_selector"
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
                    width='stretch'):
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
                    width='stretch'):
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
    
    is_running = user_config.get('bot_running', False)
    status_text = "INICIADO" if is_running else "DETENIDO"
    status_class = "dot-running" if is_running else "dot-stopped"
    
    st.sidebar.markdown(f"""
    <div style="display: flex; align-items: center; background: #f8f9fa; padding: 10px; border-radius: 8px; border: 1px solid #dadce0; margin-bottom: 10px;">
        <span class="status-dot {status_class}"></span>
        <span style="font-weight: 700; color: #202124; font-size: 13px;">ESTADO DEL BOT: </span>
        <span style="margin-left: 5px; font-weight: 800; color: {'#00c853' if is_running else '#ff1744'}; text-transform: uppercase;"> {status_text}</span>
    </div>
    """, unsafe_allow_html=True)

    if st.sidebar.button("▶️ Iniciar Bot", width='stretch', type="primary" if not is_running else "secondary"):
        update_config(bot_running=True)
        st.sidebar.success("Señal de INICIO enviada")
        st.rerun()
    
    if st.sidebar.button("⏹️ Detener Bot", width='stretch', type="primary" if is_running else "secondary"):
        update_config(bot_running=False)
        st.sidebar.warning("Señal de PARADA enviada")
        st.rerun()
        
    st.sidebar.divider()
    
    if st.sidebar.button("🔄 Restablecer Configuración", width='stretch'):
        reset_config()
        st.sidebar.info("Configuración restablecida")
        st.rerun()

    if st.sidebar.button("🧹 Limpiar Historial de Trades", width='stretch'):
        storage = get_storage_instance()
        if storage:
            storage.clear_trade_history()
            # También limpiar eventos económicos para reiniciar duplicados
            if hasattr(storage, 'clear_economic_events'):
                storage.clear_economic_events()
                
            st.cache_data.clear() # Limpiar cache de Streamlit para reflejar cambios
            st.sidebar.success("Historial y eventos borrados")
            st.rerun()

    if st.sidebar.button("📋 Limpiar Logs de Agentes", width='stretch'):
        storage = get_storage_instance()
        if storage:
            storage.clear_agent_logs()
            st.cache_data.clear() # Limpiar cache de logs
            st.sidebar.success("Logs de agentes borrados")
            st.rerun()

    if st.sidebar.button("🚨 Cerrar Posiciones", width='stretch', type="primary"):
        with st.sidebar.status("Cerrando todas las posiciones..."):
            close_all_positions()
        st.sidebar.success("Órdenes de cierre enviadas")
        st.rerun()
    
    return {
        "symbols": symbols,
        "active_symbol": active_symbol,
        "timeframe": timeframe,
        "max_risk": max_risk,
        "max_positions": max_positions
    }

def render_navbar():
    """Renderiza la barra de navegación superior pegajosa"""
    st.markdown("""
        <div class="sticky-nav">
            <a href="#dashboard" class="nav-link">📊 Dashboard</a>
            <a href="#chart" class="nav-link">📈 Gráfico</a>
            <a href="#trading" class="nav-link">🎮 Trading</a>
            <a href="#risk" class="nav-link">🛡️ Riesgo</a>
            <a href="#reports" class="nav-link">📋 Reportes</a>
        </div>
    """, unsafe_allow_html=True)


def main():
    """Función principal del dashboard"""
    storage = get_storage_instance()
    
    # Sidebar
    config = render_sidebar()
    
    # Header
    render_header()
    
    # NEW: Sticky Navbar
    render_navbar()
    st.markdown('<div class="nav-spacer"></div>', unsafe_allow_html=True)
    
    # --- SECCIÓN 1: DASHBOARD ---
    st.markdown('<div id="dashboard" class="section-container">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">📊 Dashboard</div>', unsafe_allow_html=True)
    
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
            logs = get_cached_logs(storage, limit=25)
            # Construir terminal retro
            terminal_lines = []
            terminal_lines.append('<div class="terminal-header">[ SISTEMA AUTONOMO DE TRADING - TERMINAL v2.0 ]</div>')
            if logs:
                for log in reversed(logs):
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
            
            terminal_lines.append('<div class="terminal-line">> <span class="terminal-cursor"></span></div>')
            terminal_html = f'''
            <div class="retro-terminal">
                {''.join(terminal_lines)}
            </div>
            '''
            st.markdown(terminal_html, unsafe_allow_html=True)
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("🔄 Refrescar", key="refresh_console"): st.rerun()
            with col_btn2:
                if st.button("🗑️ Limpiar", key="clear_console"): st.info("Consola limpiada")

    st.divider()
    with col1: render_performance_chart(storage)
    with col2: render_stats(storage)
    st.divider()
    col1, col2 = st.columns(2)
    with col1: render_news(storage)
    with col2: render_agent_status()
    
    st.markdown('</div>', unsafe_allow_html=True) # End Dashboard
    
    # --- SECCIÓN 2: GRÁFICO ---
    st.markdown('<div id="chart" class="section-container">', unsafe_allow_html=True)
    st.markdown(f'<div class="section-title">📈 Análisis Gráfico: {config.get("active_symbol", "EURUSD")}</div>', unsafe_allow_html=True)
    
    render_price_chart(
        symbol=config.get('active_symbol', 'EURUSD'),
        timeframe=config.get('timeframe', 'M15'),
        llm_analysis=None
    )
    st.markdown('</div>', unsafe_allow_html=True)
    
    
    # --- SECCIÓN 3: TRADING ---
    st.markdown('<div id="trading" class="section-container">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🎮 Control de Órdenes</div>', unsafe_allow_html=True)
    render_order_panel()
    st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 4: RIESGO ---
    st.markdown('<div id="risk" class="section-container">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🛡️ Monitor de Riesgo</div>', unsafe_allow_html=True)
    render_risk_monitor()
    st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 5: REPORTES ---
    st.markdown('<div id="reports" class="section-container">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">📋 Reportes & Inteligencia</div>', unsafe_allow_html=True)
    render_reports_panel()
    st.markdown('</div>', unsafe_allow_html=True)

    # Manejo de auto-refresh
    if st.session_state.get('auto_refresh', False):
        import time
        time.sleep(st.session_state.get('refresh_interval', 5))
        st.rerun()



if __name__ == "__main__":
    main()
