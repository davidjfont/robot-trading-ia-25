"""
Risk Monitor - Monitor de riesgo en tiempo real
"""

import streamlit as st
from typing import Optional, Dict
from datetime import datetime, date
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mt5.connector import MT5Connector


def render_risk_monitor():
    """Renderiza el panel de gobernanza de riesgo en tiempo real"""
    
    st.subheader("🛡️ Gobernanza de Riesgo")
    
    # Obtener datos de la cuenta
    account_data = get_account_data()
    
    if not account_data:
        st.warning("No se pudo conectar a MT5")
        return
    
    # Configuración de límites (desde session_state o defaults)
    max_daily_loss = st.session_state.get('max_daily_loss_percent', 2.0)
    max_drawdown = st.session_state.get('max_drawdown_percent', 5.0)
    max_exposure = st.session_state.get('max_exposure_percent', 10.0)
    
    # Calcular métricas
    balance = account_data.get('balance', 1000)
    equity = account_data.get('equity', 1000)
    margin_used = account_data.get('margin', 0)
    profit_today = account_data.get('profit_today', 0)
    
    # Calcular porcentajes
    daily_loss_percent = abs(min(profit_today, 0)) / balance * 100 if balance > 0 else 0
    drawdown_percent = (balance - equity) / balance * 100 if balance > 0 else 0
    exposure_percent = margin_used / balance * 100 if balance > 0 else 0
    
    # Layout de métricas
    col1, col2, col3 = st.columns(3)
    
    with col1:
        render_risk_gauge(
            title="Daily Risk Budget",
            current=daily_loss_percent,
            limit=max_daily_loss,
            unit="%",
            icon="📉"
        )
    
    with col2:
        render_risk_gauge(
            title="Drawdown",
            current=drawdown_percent,
            limit=max_drawdown,
            unit="%",
            icon="📊"
        )
    
    with col3:
        render_risk_gauge(
            title="Exposición",
            current=exposure_percent,
            limit=max_exposure,
            unit="%",
            icon="⚖️"
        )
    
    # --- NUEVA SECCIÓN: PRESUPUESTO DE RIESGO (ARAFURA 2026) ---
    st.divider()
    render_advanced_governance(daily_loss_percent, max_daily_loss)
    
    # Configuración de límites (desplegable)
    with st.expander("⚙️ Configurar Límites"):
        render_risk_config()


def render_risk_gauge(title: str, current: float, limit: float, unit: str, icon: str):
    """Renderiza un medidor de riesgo"""
    
    # Calcular porcentaje del límite
    percentage = min(current / limit * 100, 100) if limit > 0 else 0
    
    # Determinar color
    if percentage < 50:
        color = "#00c853"  # Verde
        status = "Seguro"
    elif percentage < 75:
        color = "#ffc107"  # Amarillo
        status = "Precaución"
    elif percentage < 100:
        color = "#ff9800"  # Naranja
        status = "Alerta"
    else:
        color = "#ff1744"  # Rojo
        status = "¡Límite!"
    
    st.markdown(f"""
    <div style="text-align: center; padding: 0.5rem;">
        <span style="font-size: 1.5rem;">{icon}</span>
        <h4 style="margin: 0.3rem 0;">{title}</h4>
        <div style="background: #333; border-radius: 10px; height: 20px; margin: 0.5rem 0;">
            <div style="background: {color}; width: {percentage}%; height: 100%; border-radius: 10px; transition: width 0.3s;"></div>
        </div>
        <p style="margin: 0; color: {color}; font-weight: bold;">{current:.2f}{unit} / {limit:.2f}{unit}</p>
        <small style="color: #888;">{status}</small>
    </div>
    """, unsafe_allow_html=True)


def render_risk_status(daily_loss: float, daily_limit: float, 
                       drawdown: float, dd_limit: float):
    """Renderiza el semáforo de estado general"""
    
    # Determinar estado general
    if daily_loss >= daily_limit or drawdown >= dd_limit:
        status = "COOLDOWN"
        color = "#ff1744"
        icon = "🔴"
        message = "🛡️ Streak Protection activada. Governance Cooldown en progreso."
    elif daily_loss >= daily_limit * 0.75 or drawdown >= dd_limit * 0.75:
        status = "ALERTA"
        color = "#ff9800"
        icon = "🟠"
        message = "⚠️ Acercándose a los límites de riesgo. Opere con precaución."
    elif daily_loss >= daily_limit * 0.5 or drawdown >= dd_limit * 0.5:
        status = "PRECAUCIÓN"
        color = "#ffc107"
        icon = "🟡"
        message = "ℹ️ Riesgo moderado. Monitoree sus operaciones."
    else:
        status = "NORMAL"
        color = "#00c853"
        icon = "🟢"
        message = "✅ Gobernanza activa: Parámetros dentro del Risk Budget."
    
    st.markdown(f"""
    <div style="display: flex; align-items: center; padding: 1rem; background: linear-gradient(90deg, {color}22, transparent); border-left: 4px solid {color}; border-radius: 5px;">
        <span style="font-size: 2rem; margin-right: 1rem;">{icon}</span>
        <div>
            <h3 style="margin: 0; color: {color};">Estado: {status}</h3>
            <p style="margin: 0.3rem 0 0 0; color: #ccc;">{message}</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Si estado crítico, mostrar botón de emergencia
    if status == "CRÍTICO":
        st.error("⚠️ LÍMITE DE RIESGO ALCANZADO")
        if st.button("🚨 CERRAR TODAS LAS POSICIONES", type="primary", width='stretch'):
            st.warning("Cerrando todas las posiciones...")


def render_advanced_governance(current_loss: float, daily_limit: float):
    """Muestra métricas avanzadas de gobernanza Arafura 2026"""
    
    budget_remaining = max(0, daily_limit - current_loss)
    budget_pct = (budget_remaining / daily_limit * 100) if daily_limit > 0 else 0
    
    c1, c2 = st.columns([2, 1])
    
    with c1:
        st.markdown(f"#### 🛰️ Risk Budget Identity")
        st.markdown(f"El presupuesto de seguridad está al **{budget_pct:.1f}%**. "
                   f"Se permiten nuevas operaciones mientras el budget sea > 0% e individualmente respeten la regla del 1%.")
        
        # Log de Vetos
        st.markdown("---")
        st.markdown("##### 🛡️ Últimos Vetos de Sentimiento")
        render_veto_log()
        
    with c2:
        # Mini Gauge de Budget
        import plotly.graph_objects as go
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = budget_pct,
            title = {'text': "Budget %"},
            gauge = {
                'axis': {'range': [0, 100]},
                'bar': {'color': "#00c853" if budget_pct > 20 else "#ff1744"},
                'steps': [
                    {'range': [0, 20], 'color': "rgba(255, 23, 68, 0.2)"},
                    {'range': [20, 100], 'color': "rgba(0, 200, 83, 0.1)"}
                ]
            }
        ))
        fig.update_layout(height=180, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

def render_veto_log():
    """Muestra los últimos vetos registrados en la DB"""
    from scraping.storage import get_storage
    storage = get_storage()
    if not storage:
        st.caption("No hay conexión con el storage")
        return
        
    logs = storage.fetch_agent_logs(limit=20)
    vetos = [l for l in logs if "SENTIMENT_VETO" in l.action]
    
    if not vetos:
        st.caption("✅ No se han registrado vetos recientemente.")
        return
        
    for v in vetos[:3]: # Mostrar últimos 3
        st.markdown(f"- **{v.action.replace('SENTIMENT_VETO ', '')}**: {v.result} "
                   f"<small style='color:#888'>({v.created_at[-8:]})</small>", 
                   unsafe_allow_html=True)


def render_risk_config():
    """Renderiza la configuración de límites de riesgo"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        max_daily = st.slider(
            "Pérdida diaria máxima (%)",
            min_value=0.5,
            max_value=10.0,
            value=float(st.session_state.get('max_daily_loss_percent', 2.0)),
            step=0.5,
            key="config_max_daily"
        )
        
        max_dd = st.slider(
            "Drawdown máximo (%)",
            min_value=1.0,
            max_value=20.0,
            value=float(st.session_state.get('max_drawdown_percent', 5.0)),
            step=1.0,
            key="config_max_dd"
        )
    
    with col2:
        max_exp = st.slider(
            "Exposición máxima (%)",
            min_value=5.0,
            max_value=50.0,
            value=float(st.session_state.get('max_exposure_percent', 10.0)),
            step=5.0,
            key="config_max_exp"
        )
        
        auto_stop = st.checkbox(
            "Auto-stop al alcanzar límite",
            value=st.session_state.get('auto_stop_enabled', True),
            key="config_auto_stop"
        )
    
    if st.button("💾 Guardar Configuración", key="save_risk_config"):
        st.session_state['max_daily_loss_percent'] = max_daily
        st.session_state['max_drawdown_percent'] = max_dd
        st.session_state['max_exposure_percent'] = max_exp
        st.session_state['auto_stop_enabled'] = auto_stop
        st.success("✅ Configuración guardada")


def get_account_data() -> Optional[Dict]:
    """Obtiene datos de la cuenta desde MT5, reusando el conector de la sesión si existe"""
    try:
        if 'mt5_connector' in st.session_state:
            connector = st.session_state['mt5_connector']
            if not connector.ensure_connected():
                connector.connect()
        else:
            connector = MT5Connector()
            if not connector.connect():
                return None
            st.session_state['mt5_connector'] = connector
        
        account_info = connector.get_account_info()

        positions = connector.get_positions()
        # NOTA: No desconectamos para permitir actualización en tiempo real
        
        if account_info:

            # Calcular profit del día (simplificado)
            profit_today = sum(pos.profit for pos in positions) if positions else 0
            
            return {
                'balance': account_info.get('balance', 0),
                'equity': account_info.get('equity', 0),
                'margin': account_info.get('margin', 0),
                'margin_free': account_info.get('margin_free', 0),
                'profit_today': profit_today
            }
        
        return None
    
    except Exception as e:
        return None


def check_risk_limits() -> Dict:
    """Verifica si se han alcanzado límites de riesgo"""
    account_data = get_account_data()
    
    if not account_data:
        return {'status': 'unknown', 'can_trade': True}
    
    balance = account_data.get('balance', 1000)
    equity = account_data.get('equity', 1000)
    profit_today = account_data.get('profit_today', 0)
    
    max_daily_loss = st.session_state.get('max_daily_loss_percent', 2.0)
    max_drawdown = st.session_state.get('max_drawdown_percent', 5.0)
    
    daily_loss_percent = abs(min(profit_today, 0)) / balance * 100 if balance > 0 else 0
    drawdown_percent = (balance - equity) / balance * 100 if balance > 0 else 0
    
    can_trade = True
    alerts = []
    
    if daily_loss_percent >= max_daily_loss:
        can_trade = False
        alerts.append(f"Pérdida diaria ({daily_loss_percent:.2f}%) ha alcanzado el límite ({max_daily_loss}%)")
    
    if drawdown_percent >= max_drawdown:
        can_trade = False
        alerts.append(f"Drawdown ({drawdown_percent:.2f}%) ha alcanzado el límite ({max_drawdown}%)")
    
    return {
        'status': 'blocked' if not can_trade else 'ok',
        'can_trade': can_trade,
        'alerts': alerts,
        'daily_loss_percent': daily_loss_percent,
        'drawdown_percent': drawdown_percent
    }
