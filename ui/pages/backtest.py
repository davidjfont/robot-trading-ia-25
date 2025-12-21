"""
Backtest UI - Interfaz visual para backtesting
"""

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backtester.engine import BacktestEngine


def render_backtest_page():
    """Renderiza la página de backtesting"""
    
    st.title("🔬 Backtesting Visual")
    st.caption("Prueba estrategias con datos históricos")
    
    # Sidebar con configuración
    render_backtest_config()
    
    # Área principal
    col1, col2 = st.columns([2, 1])
    
    with col1:
        render_backtest_chart()
    
    with col2:
        render_backtest_results()
    
    st.divider()
    
    # Tabla de operaciones
    render_backtest_trades()


def render_backtest_config():
    """Renderiza configuración del backtest en sidebar"""
    
    with st.sidebar:
        st.header("⚙️ Configuración Backtest")
        
        # Símbolo y timeframe
        symbol = st.selectbox(
            "Símbolo",
            ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
            key="bt_symbol"
        )
        
        timeframe = st.selectbox(
            "Timeframe",
            ["M1", "M5", "M15", "M30", "H1", "H4", "D1"],
            index=2,
            key="bt_timeframe"
        )
        
        st.divider()
        
        # Período
        st.subheader("📅 Período")
        
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "Inicio",
                value=datetime.now() - timedelta(days=90),
                key="bt_start"
            )
        with col2:
            end_date = st.date_input(
                "Fin",
                value=datetime.now(),
                key="bt_end"
            )
        
        st.divider()
        
        # Parámetros de estrategia
        st.subheader("📊 Estrategia")
        
        strategy_type = st.selectbox(
            "Tipo",
            ["EMA Crossover", "RSI Oversold/Overbought", "MACD Signal", "Combinada (IA)"],
            key="bt_strategy"
        )
        
        # Parámetros según estrategia
        if strategy_type == "EMA Crossover":
            ema_fast = st.number_input("EMA Rápida", value=20, min_value=5, max_value=50, key="ema_fast")
            ema_slow = st.number_input("EMA Lenta", value=50, min_value=20, max_value=200, key="ema_slow")
        
        elif strategy_type == "RSI Oversold/Overbought":
            rsi_period = st.number_input("Período RSI", value=14, min_value=5, max_value=30, key="rsi_period")
            rsi_oversold = st.number_input("Oversold", value=30, min_value=10, max_value=40, key="rsi_os")
            rsi_overbought = st.number_input("Overbought", value=70, min_value=60, max_value=90, key="rsi_ob")
        
        st.divider()
        
        # Gestión de riesgo
        st.subheader("🛡️ Riesgo")
        
        initial_balance = st.number_input(
            "Balance Inicial (€)",
            value=1000,
            min_value=100,
            max_value=100000,
            step=100,
            key="bt_balance"
        )
        
        lot_size = st.number_input(
            "Tamaño Lote",
            value=0.1,
            min_value=0.01,
            max_value=1.0,
            step=0.01,
            key="bt_lot"
        )
        
        sl_pips = st.number_input(
            "Stop Loss (pips)",
            value=50,
            min_value=10,
            max_value=200,
            key="bt_sl"
        )
        
        tp_pips = st.number_input(
            "Take Profit (pips)",
            value=100,
            min_value=20,
            max_value=500,
            key="bt_tp"
        )
        
        st.divider()
        
        # Botón de ejecutar
        if st.button("🚀 Ejecutar Backtest", type="primary", use_container_width=True):
            run_backtest()


def run_backtest():
    """Ejecuta el backtest con la configuración actual"""
    
    with st.spinner("Ejecutando backtest..."):
        try:
            # Obtener parámetros
            symbol = st.session_state.get('bt_symbol', 'EURUSD')
            initial_balance = st.session_state.get('bt_balance', 1000)
            lot_size = st.session_state.get('bt_lot', 0.1)
            sl_pips = st.session_state.get('bt_sl', 50)
            tp_pips = st.session_state.get('bt_tp', 100)
            
            # Crear engine
            engine = BacktestEngine(
                initial_balance=initial_balance,
                default_lot_size=lot_size,
                sl_pips=sl_pips,
                tp_pips=tp_pips
            )
            
            # Ejecutar con datos de ejemplo
            results = engine.run()
            
            # Guardar resultados en session state
            st.session_state['bt_results'] = results
            st.session_state['bt_equity_curve'] = engine.get_equity_curve() if hasattr(engine, 'get_equity_curve') else []
            st.session_state['bt_trades'] = engine.get_trades() if hasattr(engine, 'get_trades') else []
            
            st.success("✅ Backtest completado!")
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Error ejecutando backtest: {e}")


def render_backtest_chart():
    """Renderiza el gráfico de resultados del backtest"""
    
    st.subheader("📈 Curva de Equity")
    
    results = st.session_state.get('bt_results', None)
    
    if not results:
        # Mostrar gráfico de ejemplo
        st.info("Configura y ejecuta un backtest para ver resultados")
        
        # Datos de ejemplo
        n_points = 100
        x = list(range(n_points))
        base = 1000
        returns = np.random.randn(n_points) * 10
        equity = base + np.cumsum(returns)
        
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=x,
            y=equity,
            mode='lines',
            name='Equity (Ejemplo)',
            line=dict(color='#2196F3', width=2),
            fill='tozeroy',
            fillcolor='rgba(33, 150, 243, 0.1)'
        ))
        
        # Línea de balance inicial
        fig.add_hline(y=base, line_dash="dash", line_color="gray", 
                      annotation_text="Balance Inicial")
        
        fig.update_layout(
            height=400,
            template="plotly_dark",
            xaxis_title="Operaciones",
            yaxis_title="Equity (€)",
            showlegend=True,
            margin=dict(l=50, r=50, t=30, b=50)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        return
    
    # Gráfico con resultados reales
    equity_curve = st.session_state.get('bt_equity_curve', [])
    
    if equity_curve:
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            y=equity_curve,
            mode='lines',
            name='Equity',
            line=dict(color='#00c853', width=2),
            fill='tozeroy',
            fillcolor='rgba(0, 200, 83, 0.1)'
        ))
        
        fig.add_hline(y=equity_curve[0], line_dash="dash", line_color="gray",
                      annotation_text="Balance Inicial")
        
        fig.update_layout(
            height=400,
            template="plotly_dark",
            xaxis_title="Operaciones",
            yaxis_title="Equity (€)",
            showlegend=True,
            margin=dict(l=50, r=50, t=30, b=50)
        )
        
        st.plotly_chart(fig, use_container_width=True)


def render_backtest_results():
    """Renderiza resultados del backtest"""
    
    st.subheader("📊 Resultados")
    
    results = st.session_state.get('bt_results', None)
    
    if not results:
        # Datos de ejemplo
        results = {
            'net_profit': 0,
            'net_profit_pct': 0,
            'total_trades': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'max_drawdown_pct': 0,
            'sharpe_ratio': 0
        }
    
    # Métricas principales
    profit = results.get('net_profit', 0)
    profit_color = "green" if profit >= 0 else "red"
    
    st.markdown(f"""
    <div style="text-align: center; padding: 1rem; background: linear-gradient(135deg, #1a1a2e, #16213e); border-radius: 10px; margin-bottom: 1rem;">
        <h1 style="margin: 0; color: {profit_color};">€{profit:.2f}</h1>
        <p style="margin: 0.5rem 0 0 0; color: #888;">Profit Neto ({results.get('net_profit_pct', 0):.1f}%)</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Grid de métricas
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Total Trades", results.get('total_trades', 0))
        st.metric("Win Rate", f"{results.get('win_rate', 0)*100:.1f}%")
        st.metric("Profit Factor", f"{results.get('profit_factor', 0):.2f}")
    
    with col2:
        st.metric("Max Drawdown", f"{results.get('max_drawdown_pct', 0):.1f}%")
        st.metric("Sharpe Ratio", f"{results.get('sharpe_ratio', 0):.2f}")
        st.metric("Expectativa", f"€{results.get('expectancy', 0):.2f}")
    
    # Comparación con benchmark
    st.divider()
    st.markdown("**vs. Buy & Hold:**")
    
    buy_hold = results.get('buy_hold_return', 0)
    alpha = profit - buy_hold
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Buy & Hold", f"€{buy_hold:.2f}")
    with col2:
        st.metric("Alpha", f"€{alpha:.2f}", delta=f"{alpha:.2f}")


def render_backtest_trades():
    """Renderiza tabla de operaciones del backtest"""
    
    st.subheader("📝 Operaciones del Backtest")
    
    trades = st.session_state.get('bt_trades', [])
    
    if not trades:
        # Datos de ejemplo
        trades_data = []
        for i in range(10):
            is_win = np.random.random() > 0.4
            profit = np.random.uniform(30, 80) if is_win else np.random.uniform(-50, -20)
            trades_data.append({
                'N°': i + 1,
                'Tipo': 'BUY' if np.random.random() > 0.5 else 'SELL',
                'Entrada': 1.0850 + np.random.uniform(-0.01, 0.01),
                'Salida': 1.0850 + np.random.uniform(-0.01, 0.01),
                'Profit': profit,
                'Resultado': '✅' if is_win else '❌'
            })
        
        df = pd.DataFrame(trades_data)
    else:
        df = pd.DataFrame(trades)
    
    # Formatear y mostrar
    def color_profit(val):
        if isinstance(val, (int, float)):
            color = 'green' if val > 0 else 'red' if val < 0 else 'gray'
            return f'color: {color}'
        return ''
    
    st.dataframe(
        df.style.applymap(color_profit, subset=['Profit'] if 'Profit' in df.columns else []),
        use_container_width=True,
        height=300
    )
    
    # Estadísticas rápidas
    if 'Profit' in df.columns:
        total_profit = df['Profit'].sum()
        winners = len(df[df['Profit'] > 0])
        losers = len(df[df['Profit'] < 0])
        
        st.caption(f"Total: {len(df)} operaciones | Profit: €{total_profit:.2f} | Ganadores: {winners} | Perdedores: {losers}")


def render_optimization_panel():
    """Panel de optimización de parámetros"""
    
    st.subheader("🔧 Optimización de Parámetros")
    
    st.markdown("""
    Ejecuta múltiples backtests con diferentes parámetros para encontrar la configuración óptima.
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Parámetro a optimizar:**")
        param_to_optimize = st.selectbox(
            "Parámetro",
            ["EMA Rápida", "EMA Lenta", "RSI Period", "Stop Loss", "Take Profit"],
            key="opt_param"
        )
        
        param_min = st.number_input("Valor mínimo", value=10, key="opt_min")
        param_max = st.number_input("Valor máximo", value=50, key="opt_max")
        param_step = st.number_input("Paso", value=5, key="opt_step")
    
    with col2:
        st.markdown("**Métrica objetivo:**")
        objective = st.selectbox(
            "Optimizar para",
            ["Profit Neto", "Sharpe Ratio", "Profit Factor", "Win Rate"],
            key="opt_objective"
        )
        
        st.markdown("**Restricciones:**")
        min_trades = st.number_input("Mínimo trades", value=20, key="opt_min_trades")
        max_dd = st.number_input("Max Drawdown (%)", value=20.0, key="opt_max_dd")
    
    if st.button("🔬 Ejecutar Optimización", use_container_width=True):
        with st.spinner("Optimizando..."):
            st.info("Optimización en desarrollo...")


# Ejecutar como página standalone de Streamlit
if __name__ == "__main__":
    st.set_page_config(page_title="Backtest", page_icon="🔬", layout="wide")
    render_backtest_page()
