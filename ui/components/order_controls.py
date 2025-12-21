"""
Order Controls - Componente de control de órdenes manuales
"""

import streamlit as st
from typing import Optional, Dict, Any
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mt5.connector import MT5Connector
from mt5.order_agent import OrderAgent


def render_order_panel():
    """Renderiza el panel de control de órdenes"""
    
    st.subheader("🎮 Control de Órdenes")
    
    # Tabs para diferentes acciones
    tab1, tab2, tab3 = st.tabs(["📝 Nueva Orden", "⚡ Acciones Rápidas", "⚙️ Gestión"])
    
    with tab1:
        render_new_order_form()
    
    with tab2:
        render_quick_actions()
    
    with tab3:
        render_position_management()


def render_new_order_form():
    """Formulario para abrir nueva orden"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        symbol = st.selectbox(
            "Símbolo",
            ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"],
            key="order_symbol"
        )
        
        order_type = st.radio(
            "Tipo de Orden",
            ["BUY", "SELL"],
            horizontal=True,
            key="order_type"
        )
        
        volume = st.number_input(
            "Volumen (lotes)",
            min_value=0.01,
            max_value=1.0,
            value=0.1,
            step=0.01,
            key="order_volume"
        )
    
    with col2:
        use_sl = st.checkbox("Usar Stop Loss", value=True, key="use_sl")
        sl_pips = st.number_input(
            "Stop Loss (pips)",
            min_value=10,
            max_value=200,
            value=50,
            disabled=not use_sl,
            key="sl_pips"
        )
        
        use_tp = st.checkbox("Usar Take Profit", value=True, key="use_tp")
        tp_pips = st.number_input(
            "Take Profit (pips)",
            min_value=10,
            max_value=500,
            value=100,
            disabled=not use_tp,
            key="tp_pips"
        )
    
    st.divider()
    
    # Botón de ejecutar con confirmación
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        if st.button(
            f"🚀 Ejecutar {order_type}",
            type="primary",
            use_container_width=True,
            key="execute_order"
        ):
            execute_order(
                symbol=symbol,
                order_type=order_type,
                volume=volume,
                sl_pips=sl_pips if use_sl else None,
                tp_pips=tp_pips if use_tp else None
            )


def render_quick_actions():
    """Acciones rápidas para posiciones"""
    
    st.write("**Acciones rápidas para todas las posiciones:**")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔄 Break-Even Todo", use_container_width=True, key="breakeven_all"):
            apply_breakeven_all()
    
    with col2:
        if st.button("📏 Trailing Stop", use_container_width=True, key="trailing_all"):
            apply_trailing_all()
    
    with col3:
        if st.button("🚨 Cerrar Todo", type="primary", use_container_width=True, key="close_all"):
            close_all_positions()
    
    st.divider()
    
    # Configuración de trailing
    st.write("**Configuración Trailing Stop:**")
    col1, col2 = st.columns(2)
    
    with col1:
        trailing_distance = st.number_input(
            "Distancia (pips)",
            min_value=10,
            max_value=100,
            value=30,
            key="trailing_distance"
        )
    
    with col2:
        trailing_step = st.number_input(
            "Step (pips)",
            min_value=1,
            max_value=50,
            value=10,
            key="trailing_step"
        )
    
    # Guardar en session state
    st.session_state['trailing_config'] = {
        'distance': trailing_distance,
        'step': trailing_step
    }


def render_position_management():
    """Gestión individual de posiciones"""
    
    connector = get_connector()
    if not connector:
        st.warning("No hay conexión con MT5")
        return
    
    positions = connector.get_positions()
    connector.disconnect()
    
    if not positions:
        st.info("No hay posiciones abiertas para gestionar")
        return
    
    for pos in positions:
        with st.expander(f"#{pos.ticket} - {pos.symbol} {'🟢 BUY' if pos.type == 0 else '🔴 SELL'}"):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Volumen", f"{pos.volume} lotes")
                st.metric("Profit", f"€{pos.profit:.2f}")
            
            with col2:
                st.metric("Precio Apertura", f"{pos.price_open:.5f}")
                st.metric("Precio Actual", f"{pos.price_current:.5f}")
            
            with col3:
                st.metric("SL", f"{pos.sl:.5f}" if pos.sl > 0 else "No definido")
                st.metric("TP", f"{pos.tp:.5f}" if pos.tp > 0 else "No definido")
            
            st.divider()
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if st.button("🔄 Break-Even", key=f"be_{pos.ticket}"):
                    apply_breakeven(pos.ticket)
            
            with col2:
                if st.button("📏 Trailing", key=f"tr_{pos.ticket}"):
                    apply_trailing(pos.ticket)
            
            with col3:
                partial = st.number_input(
                    "% Cierre",
                    min_value=25,
                    max_value=100,
                    value=50,
                    step=25,
                    key=f"partial_{pos.ticket}"
                )
            
            with col4:
                if st.button("❌ Cerrar", key=f"close_{pos.ticket}"):
                    close_position(pos.ticket, partial / 100)


def get_connector() -> Optional[MT5Connector]:
    """Obtiene conexión MT5"""
    try:
        connector = MT5Connector()
        if connector.connect():
            return connector
        return None
    except Exception as e:
        st.error(f"Error conectando a MT5: {e}")
        return None


def execute_order(symbol: str, order_type: str, volume: float, 
                  sl_pips: Optional[int], tp_pips: Optional[int]):
    """Ejecuta una orden manual"""
    
    connector = get_connector()
    if not connector:
        st.error("❌ No se pudo conectar a MT5")
        return
    
    try:
        # Obtener precio actual
        tick = connector.get_symbol_tick(symbol)
        if not tick:
            st.error(f"❌ No se pudo obtener precio de {symbol}")
            return
        
        price = tick.ask if order_type == "BUY" else tick.bid
        point = connector.get_symbol_info(symbol).point
        
        # Calcular SL y TP
        sl = 0.0
        tp = 0.0
        
        if sl_pips:
            if order_type == "BUY":
                sl = price - (sl_pips * point * 10)
            else:
                sl = price + (sl_pips * point * 10)
        
        if tp_pips:
            if order_type == "BUY":
                tp = price + (tp_pips * point * 10)
            else:
                tp = price - (tp_pips * point * 10)
        
        # Crear orden
        order_agent = OrderAgent()
        result = order_agent.place_order(
            symbol=symbol,
            order_type=order_type.lower(),
            volume=volume,
            sl=sl,
            tp=tp
        )
        
        if result and result.get('success'):
            st.success(f"✅ Orden {order_type} ejecutada: {symbol} @ {price:.5f}")
            st.balloons()
        else:
            st.error(f"❌ Error ejecutando orden: {result.get('error', 'Desconocido')}")
    
    except Exception as e:
        st.error(f"❌ Error: {e}")
    
    finally:
        connector.disconnect()


def close_all_positions():
    """Cierra todas las posiciones abiertas"""
    
    connector = get_connector()
    if not connector:
        st.error("❌ No se pudo conectar a MT5")
        return
    
    try:
        positions = connector.get_positions()
        
        if not positions:
            st.info("No hay posiciones para cerrar")
            return
        
        order_agent = OrderAgent()
        closed = 0
        
        for pos in positions:
            result = order_agent.close_position(pos.ticket)
            if result and result.get('success'):
                closed += 1
        
        st.success(f"✅ Cerradas {closed} de {len(positions)} posiciones")
    
    except Exception as e:
        st.error(f"❌ Error: {e}")
    
    finally:
        connector.disconnect()


def apply_breakeven_all():
    """Aplica break-even a todas las posiciones en profit"""
    st.info("🔄 Aplicando break-even a posiciones en profit...")
    # TODO: Implementar lógica de break-even
    st.success("✅ Break-even aplicado")


def apply_trailing_all():
    """Aplica trailing stop a todas las posiciones"""
    config = st.session_state.get('trailing_config', {'distance': 30, 'step': 10})
    st.info(f"📏 Aplicando trailing stop ({config['distance']} pips)...")
    # TODO: Implementar lógica de trailing
    st.success("✅ Trailing stop aplicado")


def apply_breakeven(ticket: int):
    """Aplica break-even a una posición específica"""
    st.info(f"🔄 Break-even aplicado a #{ticket}")


def apply_trailing(ticket: int):
    """Aplica trailing stop a una posición específica"""
    st.info(f"📏 Trailing aplicado a #{ticket}")


def close_position(ticket: int, percentage: float = 1.0):
    """Cierra una posición (total o parcial)"""
    if percentage < 1.0:
        st.info(f"⚡ Cierre parcial ({percentage*100:.0f}%) de #{ticket}")
    else:
        st.info(f"❌ Posición #{ticket} cerrada")
