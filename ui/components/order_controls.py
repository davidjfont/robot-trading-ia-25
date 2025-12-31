"""
Order Controls - Componente de control de órdenes manuales
"""

import streamlit as st
from typing import Optional, Dict, Any
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mt5.connector import MT5Connector, Position
from mt5.order_agent import OrderAgent
from core.symbols import get_all_symbols


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
            get_all_symbols(),
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
            width='stretch',
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
        if st.button("💰 Cerrar Profit", width='stretch', key="close_profit"):
            close_positions_by_profit("profit")
    
    with col2:
        if st.button("📉 Cerrar Loss", width='stretch', key="close_loss"):
            close_positions_by_profit("loss")
    
    with col3:
        if st.button("🚨 Cerrar Todo", type="primary", width='stretch', key="close_all"):
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
    # NOTA: No desconectamos aquí - el conector se comparte en session_state
    
    if not positions:
        st.info("No hay posiciones abiertas para gestionar")
        return
    
    for pos in positions:
        with st.expander(f"#{pos.ticket} - {pos.symbol} {'🟢 BUY' if pos.type == 'BUY' else '🔴 SELL'}"):

            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Volumen", f"{pos.volume} lotes")
                st.metric("Profit", f"€{pos.profit:.2f}")
            
            with col2:
                st.metric("Precio Apertura", f"{pos.open_price:.5f}")
                st.metric("Precio Actual", f"{pos.current_price:.5f}")

            
            with col3:
                st.metric("SL", f"{pos.sl:.5f}" if pos.sl > 0 else "No definido")
                st.metric("TP", f"{pos.tp:.5f}" if pos.tp > 0 else "No definido")
            
            st.divider()
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if st.button("🔄 Break-Even", key=f"be_{pos.ticket}"):
                    if apply_breakeven_logic(pos):
                        st.success(f"BE aplicado a #{pos.ticket}")
            
            with col2:
                if st.button("📏 Trailing", key=f"tr_{pos.ticket}"):
                    if apply_trailing_logic(pos, 30):
                        st.success(f"Trailing activo en #{pos.ticket}")

            
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
                    if close_position_executed(pos.ticket):
                        st.rerun()



def get_connector() -> Optional[MT5Connector]:
    """Obtiene conexión MT5 desde la sesión"""
    if 'mt5_connector' in st.session_state:
        connector = st.session_state['mt5_connector']
        if connector.ensure_connected():
            return connector
    return None



def execute_order(symbol: str, order_type: str, volume: float, 
                  sl_pips: Optional[int], tp_pips: Optional[int]):
    """Ejecuta una orden manual"""
    
    connector = get_connector()
    if not connector:
        st.error("❌ No hay conexión activa con MT5 en la sesión.")
        return

    
    try:
        # Obtener precio actual
        tick = connector.get_symbol_tick(symbol)
        if not tick:
            st.error(f"❌ No se pudo obtener precio de {symbol}")
            return
        
        price = tick.ask if order_type == "BUY" else tick.bid
        point = connector.get_symbol_info(symbol).point
        
        # Ejecutar orden usando el agente
        order_agent = OrderAgent()
        result_agent = order_agent.execute({
            "symbol": symbol,
            "type": order_type.upper(),
            "volume": volume,
            "sl_pips": sl_pips,
            "tp_pips": tp_pips
        })
        
        if result_agent.success:
            st.success(f"✅ Orden {order_type} ejecutada: {symbol} @ {result_agent.data.get('price', 0):.5f}")
            st.balloons()
        else:
            st.error(f"❌ Error ejecutando orden: {result_agent.error}")

    
    except Exception as e:
        st.error(f"❌ Error: {e}")



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
            if order_agent.close_position(pos.ticket):
                closed += 1

        
        st.success(f"✅ Cerradas {closed} de {len(positions)} posiciones")
    
    except Exception as e:
        st.error(f"❌ Error: {e}")



def close_positions_by_profit(profit_type: str):
    """Cierra posiciones filtrando por profit (positivo o negativo)"""
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
        target_positions = []
        
        for pos in positions:
            if profit_type == "profit" and pos.profit > 0:
                target_positions.append(pos)
            elif profit_type == "loss" and pos.profit < 0:
                target_positions.append(pos)
        
        if not target_positions:
            st.info(f"No hay posiciones en {'Garantía' if profit_type == 'profit' else 'Pérdida'} para cerrar")
            return
            
        for pos in target_positions:
            if order_agent.close_position(pos.ticket):
                closed += 1
                
        st.success(f"✅ Cerradas {closed} de {len(target_positions)} posiciones en {profit_type}")
        st.rerun()
        
    except Exception as e:
        st.error(f"❌ Error: {e}")


def apply_breakeven_logic(pos: Position) -> bool:
    """Aplica break-even a una posición (mueve SL al precio de entrada + pequeño buffer)"""
    order_agent = OrderAgent()
    # Pequeño buffer para cubrir spread/comisión (ej: 2 pips)
    symbol_info = order_agent.connector.get_symbol_info(pos.symbol)
    if not symbol_info:
        return False
        
    point = symbol_info.point
    buffer = 20 * point # 2 pips
    
    if pos.type == "BUY":
        new_sl = pos.open_price + buffer
        # Solo mover si el precio actual está lo suficientemente lejos y es una mejora de SL
        if pos.current_price > new_sl and new_sl > pos.sl:
            return order_agent.modify_position(pos.ticket, new_sl, pos.tp)
    else: # SELL
        new_sl = pos.open_price - buffer
        if pos.current_price < new_sl and (pos.sl == 0 or new_sl < pos.sl):
            return order_agent.modify_position(pos.ticket, new_sl, pos.tp)
            
    return False


def apply_trailing_logic(pos: Position, distance_pips: int = 30) -> bool:
    """Aplica un trailing stop puntual (un solo paso)"""
    order_agent = OrderAgent()
    symbol_info = order_agent.connector.get_symbol_info(pos.symbol)
    if not symbol_info:
        return False
        
    point = symbol_info.point
    distance = distance_pips * point * 10
    
    if pos.type == "BUY":
        new_sl = pos.current_price - distance
        if new_sl > pos.sl:
            return order_agent.modify_position(pos.ticket, new_sl, pos.tp)
    else: # SELL
        new_sl = pos.current_price + distance
        if pos.sl == 0 or new_sl < pos.sl:
            return order_agent.modify_position(pos.ticket, new_sl, pos.tp)
            
    return False


def apply_breakeven_all():
    """Aplica break-even a todas las posiciones en profit significativo"""
    order_agent = OrderAgent()
    positions = order_agent.connector.get_positions()
    count = 0
    for pos in positions:
        if pos.profit > 0 and apply_breakeven_logic(pos):
            count += 1
    st.success(f"✅ BE aplicado a {count} posiciones")


def apply_trailing_all():
    """Aplica trailing stop a todas las posiciones activas"""
    order_agent = OrderAgent()
    positions = order_agent.connector.get_positions()
    count = 0
    for pos in positions:
        if apply_trailing_logic(pos):
            count += 1
    st.success(f"✅ Trailing aplicado a {count} posiciones")


def close_position_executed(ticket: int) -> bool:
    """Ejecuta el cierre de una posición desde la UI"""
    order_agent = OrderAgent()
    if order_agent.close_position(ticket):
        # El cierre puede tardar un poco en reflejarse en MT5
        return True
    return False

