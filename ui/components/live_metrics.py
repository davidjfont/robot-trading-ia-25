"""
Live Metrics - Widget de métricas en tiempo real
"""

import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mt5.connector import MT5Connector
from agents.risk_agent import RiskAgent
from scraping.storage import get_storage


def render_live_metrics():
    """Renderiza métricas en tiempo real"""
    
    st.subheader("📊 Métricas en Vivo")
    
    # Obtener datos
    connector = get_connector()
    if not connector:
        st.warning("Sin conexión a MT5")
        return
    
    account = connector.get_account_info()
    positions = connector.get_positions()
    # NOTA: No desconectamos para mantener el flujo en tiempo real
    
    if not account:

        return
    
    balance = account.get('balance', 0)
    equity = account.get('equity', 0)
    margin_free = account.get('margin_free', 0)
    
    # RiskAgent status
    risk_agent = get_risk_agent()
    risk_status = risk_agent.get_full_status(balance, equity, margin_free)
    
    # Layout principal
    render_quick_stats(account, positions, risk_status)
    st.divider()
    render_risk_gauges(risk_status, balance)
    st.divider()
    render_pnl_chart()
    st.divider()
    render_recent_decisions(risk_status.get('recent_decisions', []))


def render_quick_stats(account: Dict, positions: List, risk: Dict):
    """Renderiza estadísticas rápidas"""
    
    col1, col2, col3, col4 = st.columns(4)
    
    balance = account.get('balance', 0)
    equity = account.get('equity', 0)
    profit = account.get('profit', 0)
    
    with col1:
        st.metric(
            "Balance",
            f"€{balance:,.2f}",
            delta=f"€{risk.get('daily_net', 0):.2f} hoy"
        )
    
    with col2:
        st.metric(
            "Equity",
            f"€{equity:,.2f}",
            delta=f"{-risk.get('drawdown_pct', 0):.1f}% DD" if risk.get('drawdown_pct', 0) > 0 else None,
            delta_color="inverse"
        )
    
    with col3:
        num_pos = len(positions) if positions else 0
        floating_pnl = sum(p.profit for p in positions) if positions else 0
        st.metric(
            "Posiciones",
            num_pos,
            delta=f"€{floating_pnl:.2f}" if num_pos > 0 else None
        )
    
    with col4:
        # Estado de riesgo con color
        status = risk.get('status', 'normal')
        color = risk.get('color', 'green')
        
        status_icons = {
            'normal': '🟢',
            'caution': '🟡', 
            'warning': '🟠',
            'blocked': '🔴',
            'emergency': '🚨'
        }
        
        st.metric(
            "Governance",
            f"{status_icons.get(status, '⚪')} {status.upper()}",
            delta=f"{risk.get('risk_budget_remaining', 1.0):.0%} Budget"
        )


def render_risk_gauges(risk: Dict, balance: float):
    """Renderiza medidores de riesgo"""
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        daily_loss = risk.get('daily_loss_pct', 0)
        max_daily = risk.get('max_allowed_pct', 2)
        render_mini_gauge("Pérdida Diaria", daily_loss, max_daily, "%")
    
    with col2:
        drawdown = risk.get('drawdown_pct', 0)
        max_dd = risk.get('max_drawdown_pct', 5)
        render_mini_gauge("Drawdown", drawdown, max_dd, "%")
    
    with col3:
        margin_used = 100 - risk.get('margin_free_pct', 100)
        render_mini_gauge("Risk Exposure", margin_used, 70, "%")
    
    with col4:
        consec = risk.get('streak_count', 0)
        render_mini_gauge("Streak Protection", consec, 3, "")
    
    # Nueva fila de métricas avanzadas
    st.markdown("<br>", unsafe_allow_html=True)
    col5, col6, col7, col8 = st.columns(4)
    
    storage = get_storage()
    stats = storage.get_trade_stats(days=7) # Ultima semana
    
    with col5:
        st.metric("Expectancy", f"€{stats.get('expectancy', 0):.2f}")
    
    with col6:
        st.metric("Profit/Min", f"€{stats.get('profit_per_minute', 0):.4f}")
    
    with col7:
        st.metric("Win Rate", f"{stats.get('win_rate', 0):.1%}")
    
    with col8:
        st.metric("Daily DD", f"{risk.get('drawdown_pct', 0):.1f}%")


def render_mini_gauge(title: str, current: float, limit: float, unit: str):
    """Renderiza un mini medidor"""
    
    pct = min((current / limit) * 100, 100) if limit > 0 else 0
    
    if pct < 50:
        color = "#00c853"
    elif pct < 75:
        color = "#ffc107"
    elif pct < 100:
        color = "#ff9800"
    else:
        color = "#ff1744"
    
    st.markdown(f"""
    <div style="text-align: center;">
        <small style="color: #888;">{title}</small>
        <div style="background: #333; border-radius: 5px; height: 8px; margin: 5px 0;">
            <div style="background: {color}; width: {pct}%; height: 100%; border-radius: 5px;"></div>
        </div>
        <strong style="color: {color};">{current:.1f}{unit}</strong>
        <small style="color: #666;"> / {limit:.0f}{unit}</small>
    </div>
    """, unsafe_allow_html=True)


def render_pnl_chart():
    """Renderiza gráfico de P&L intraday"""
    
    st.markdown("**📈 P&L del Día**")
    
    # Intentar obtener P&L real de las posiciones
    connector = get_connector()
    current_pnl = 0
    
    if connector:
        positions = connector.get_positions()
        if positions:
            current_pnl = sum(p.profit for p in positions)
    
    # Generar datos simulados basados en P&L actual
    hours = list(range(9, datetime.now().hour + 1)) if datetime.now().hour >= 9 else [9]
    
    if len(hours) == 1:
        pnl = [current_pnl]
    else:
        # Simular progresión hacia el P&L actual
        import random
        random.seed(datetime.now().day)  # Consistente por día
        pnl = []
        for i, h in enumerate(hours):
            if i == len(hours) - 1:
                pnl.append(current_pnl)
            else:
                progress = i / len(hours)
                noise = random.uniform(-20, 20)
                pnl.append(current_pnl * progress + noise)
    
    fig = go.Figure()
    
    # Color según P&L
    line_color = '#00c853' if current_pnl >= 0 else '#ff1744'
    fill_color = 'rgba(0, 200, 83, 0.1)' if current_pnl >= 0 else 'rgba(255, 23, 68, 0.1)'
    
    fig.add_trace(go.Scatter(
        x=[f"{h}:00" for h in hours],
        y=pnl,
        mode='lines+markers',
        name='P&L',
        line=dict(color=line_color, width=2),
        fill='tozeroy',
        fillcolor=fill_color
    ))
    
    # Línea de cero
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    
    fig.update_layout(
        height=200,
        margin=dict(l=40, r=40, t=20, b=30),
        xaxis_title="Hora",
        yaxis_title="€",
        template="plotly_dark",
        showlegend=False
    )
    
    st.plotly_chart(fig, width='stretch')
    st.caption(f"P&L Actual: €{current_pnl:.2f}")


def render_recent_decisions(decisions: List):
    """Renderiza log de decisiones recientes"""
    
    st.markdown("**🧠 Decisiones Recientes del RiskAgent**")
    
    if not decisions:
        st.caption("No hay decisiones registradas todavía")
        return
    
    for decision in reversed(decisions[-5:]):
        icon = "✅" if decision.approved else "❌"
        time_str = decision.timestamp.strftime("%H:%M:%S")
        
        with st.container():
            col1, col2, col3 = st.columns([1, 2, 3])
            
            with col1:
                st.caption(time_str)
            
            with col2:
                st.write(f"{icon} {decision.symbol}")
            
            with col3:
                if decision.reasons:
                    st.caption(decision.reasons[0][:50])


def render_quality_indicator():
    """Indicador de calidad de señales"""
    
    st.markdown("**📡 Calidad de Señales**")
    
    # Últimas 10 señales simuladas
    signals = [
        {"symbol": "EURUSD", "direction": "BUY", "correct": True},
        {"symbol": "GBPUSD", "direction": "SELL", "correct": False},
        {"symbol": "EURUSD", "direction": "BUY", "correct": True},
        {"symbol": "USDJPY", "direction": "SELL", "correct": True},
        {"symbol": "GBPUSD", "direction": "BUY", "correct": True},
    ]
    
    correct = sum(1 for s in signals if s['correct'])
    accuracy = (correct / len(signals)) * 100 if signals else 0
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.metric("Precisión", f"{accuracy:.0f}%", delta=f"{correct}/{len(signals)}")
    
    with col2:
        # Visualización de últimas señales
        signal_str = "".join(["🟢" if s['correct'] else "🔴" for s in signals])
        st.write(f"Últimas: {signal_str}")


def get_connector() -> Optional[MT5Connector]:
    """Obtiene conector MT5 reusando el de la sesión"""
    try:
        if 'mt5_connector' in st.session_state:
            connector = st.session_state['mt5_connector']
            if not connector.ensure_connected():
                connector.connect()
            return connector
        
        connector = MT5Connector()
        if connector.connect():
            st.session_state['mt5_connector'] = connector
            return connector
        return None
    except:
        return None



@st.cache_resource
def get_risk_agent() -> RiskAgent:
    """Obtiene instancia de RiskAgent (cacheado)"""
    return RiskAgent()


# Para ejecutar standalone
if __name__ == "__main__":
    st.set_page_config(page_title="Live Metrics", page_icon="📊", layout="wide")
    render_live_metrics()
