"""
Reports - Componente de reportes y exportación
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import io
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strategies.analytics import TradingAnalytics, TradeResult
from scraping.storage import get_storage


def render_reports_panel():
    """Renderiza el panel de reportes"""
    
    st.subheader("📋 Reportes y Análisis")
    
    # Tabs para diferentes reportes
    tab1, tab2, tab3 = st.tabs(["📊 Métricas", "📝 Journal", "📤 Exportar"])
    
    with tab1:
        render_metrics_report()
    
    with tab2:
        render_trade_journal()
    
    with tab3:
        render_export_options()


def render_metrics_report():
    """Renderiza métricas profesionales"""
    
    # Selector de período
    period = st.selectbox(
        "Período",
        ["Última semana", "Último mes", "Últimos 3 meses", "Todo el historial"],
        key="metrics_period"
    )
    
    # Obtener trades del período
    trades = get_trades_for_period(period)
    
    if not trades:
        st.info("No hay trades registrados para este período")
        return
    
    analytics = TradingAnalytics(trades)
    metrics = analytics.calculate_all_metrics()
    
    # Métricas principales en cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Win Rate",
            f"{metrics['win_rate']*100:.1f}%",
            delta=None
        )
    
    with col2:
        profit_color = "normal" if metrics['net_profit'] >= 0 else "inverse"
        st.metric(
            "Profit Neto",
            f"€{metrics['net_profit']:.2f}",
            delta=f"{metrics['net_profit_pct']:.1f}%",
            delta_color=profit_color
        )
    
    with col3:
        st.metric(
            "Profit Factor",
            f"{metrics['profit_factor']:.2f}"
        )
    
    with col4:
        st.metric(
            "Sharpe Ratio",
            f"{metrics['sharpe_ratio']:.2f}"
        )
    
    st.divider()
    
    # Dos columnas de métricas detalladas
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📈 Rendimiento")
        metrics_df = pd.DataFrame({
            'Métrica': [
                'Total Trades',
                'Ganadores',
                'Perdedores',
                'Media Ganadora',
                'Media Perdedora',
                'Risk/Reward',
                'Expectativa'
            ],
            'Valor': [
                metrics['total_trades'],
                metrics['winning_trades'],
                metrics['losing_trades'],
                f"€{metrics['avg_winning_trade']:.2f}",
                f"€{metrics['avg_losing_trade']:.2f}",
                f"{metrics['risk_reward_ratio']:.2f}",
                f"€{metrics['expectancy']:.2f}"
            ]
        })
        st.dataframe(metrics_df, width='stretch', hide_index=True)
    
    with col2:
        st.markdown("### 📉 Riesgo")
        risk_df = pd.DataFrame({
            'Métrica': [
                'Max Drawdown',
                'Max DD %',
                'Sortino Ratio',
                'Calmar Ratio',
                'Recovery Factor',
                'Max Rachas +',
                'Max Rachas -'
            ],
            'Valor': [
                f"€{metrics['max_drawdown']:.2f}",
                f"{metrics['max_drawdown_pct']:.2f}%",
                f"{metrics['sortino_ratio']:.2f}",
                f"{metrics['calmar_ratio']:.2f}",
                f"{metrics['recovery_factor']:.2f}",
                metrics['max_consecutive_wins'],
                metrics['max_consecutive_losses']
            ]
        })
        st.dataframe(risk_df, width='stretch', hide_index=True)
    
    # Gráfico de equity curve
    st.markdown("### 📊 Curva de Equity")
    equity_curve = analytics.equity_curve
    
    if equity_curve:
        import plotly.graph_objects as go
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            y=equity_curve,
            mode='lines',
            name='Equity',
            line=dict(color='#2196F3', width=2),
            fill='tozeroy',
            fillcolor='rgba(33, 150, 243, 0.1)'
        ))
        
        fig.update_layout(
            height=300,
            margin=dict(l=50, r=50, t=30, b=30),
            xaxis_title="Operaciones",
            yaxis_title="Equity (€)",
            template="plotly_dark"
        )
        
        st.plotly_chart(fig, use_container_width=True)


def render_trade_journal():
    """Renderiza el journal de trades"""
    
    # Filtros
    col1, col2, col3 = st.columns(3)
    
    with col1:
        symbol_filter = st.multiselect(
            "Símbolo",
            ["Todos", "EURUSD", "GBPUSD", "USDJPY"],
            default=["Todos"],
            key="journal_symbol"
        )
    
    with col2:
        type_filter = st.multiselect(
            "Tipo",
            ["Todos", "BUY", "SELL"],
            default=["Todos"],
            key="journal_type"
        )
    
    with col3:
        result_filter = st.selectbox(
            "Resultado",
            ["Todos", "Ganadores", "Perdedores"],
            key="journal_result"
        )
    
    # Obtener y filtrar trades
    trades = get_all_trades()
    
    if not trades:
        st.info("No hay trades registrados en el journal")
        
        # Mostrar datos de ejemplo
        st.caption("Mostrando datos de ejemplo:")
        example_data = pd.DataFrame({
            'Fecha': [datetime.now() - timedelta(days=i) for i in range(5)],
            'Símbolo': ['EURUSD', 'GBPUSD', 'EURUSD', 'USDJPY', 'GBPUSD'],
            'Tipo': ['BUY', 'SELL', 'BUY', 'SELL', 'BUY'],
            'Volumen': [0.1, 0.05, 0.1, 0.1, 0.05],
            'Profit': [45.50, -23.00, 67.00, -15.50, 32.00],
            'Pips': [45.5, -23.0, 67.0, -15.5, 32.0],
            'Notas': ['Señal fuerte', 'Stop loss', 'Tendencia clara', 'Ruido', 'Rebote en soporte']
        })
        
        st.dataframe(
            example_data.style.map(
                lambda x: 'color: green' if isinstance(x, (int, float)) and x > 0 else 'color: red' if isinstance(x, (int, float)) and x < 0 else '',
                subset=['Profit', 'Pips']
            ),
            use_container_width=True
        )
        return
    
    # Crear DataFrame
    df = pd.DataFrame([{
        'Fecha': t.close_time,
        'Símbolo': t.symbol,
        'Tipo': t.order_type,
        'Volumen': t.volume,
        'Entrada': t.open_price,
        'Salida': t.close_price,
        'Profit': t.profit,
        'Duración': f"{t.duration_minutes:.0f} min"
    } for t in trades])
    
    # Aplicar filtros
    if "Todos" not in symbol_filter:
        df = df[df['Símbolo'].isin(symbol_filter)]
    
    if "Todos" not in type_filter:
        df = df[df['Tipo'].isin(type_filter)]
    
    if result_filter == "Ganadores":
        df = df[df['Profit'] > 0]
    elif result_filter == "Perdedores":
        df = df[df['Profit'] < 0]
    
    # Mostrar tabla
    st.dataframe(
        df.style.map(
            lambda x: 'color: green' if isinstance(x, (int, float)) and x > 0 else 'color: red' if isinstance(x, (int, float)) and x < 0 else '',
            subset=['Profit']
        ),
        use_container_width=True
    )

    
    # Estadísticas rápidas
    st.caption(f"Mostrando {len(df)} operaciones | Profit total: €{df['Profit'].sum():.2f}")


def render_export_options():
    """Renderiza opciones de exportación"""
    
    st.markdown("### 📤 Exportar Datos")
    
    # Selector de qué exportar
    export_type = st.selectbox(
        "¿Qué deseas exportar?",
        ["Historial de trades", "Métricas de rendimiento", "Reporte completo"],
        key="export_type"
    )
    
    # Período
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "Desde",
            value=datetime.now() - timedelta(days=30),
            key="export_start"
        )
    with col2:
        end_date = st.date_input(
            "Hasta",
            value=datetime.now(),
            key="export_end"
        )
    
    st.divider()
    
    # Botones de exportación
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📊 Exportar CSV", width='stretch'):
            csv_data = generate_csv_export(export_type, start_date, end_date)
            st.download_button(
                label="⬇️ Descargar CSV",
                data=csv_data,
                file_name=f"trading_export_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                key="download_csv"
            )
    
    with col2:
        if st.button("📑 Exportar Excel", width='stretch'):
            excel_data = generate_excel_export(export_type, start_date, end_date)
            st.download_button(
                label="⬇️ Descargar Excel",
                data=excel_data,
                file_name=f"trading_export_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_excel"
            )
    
    with col3:
        if st.button("📝 Generar Reporte", width='stretch'):
            report_text = generate_text_report(start_date, end_date)
            st.text_area("Reporte", report_text, height=400)
            st.download_button(
                label="⬇️ Descargar Reporte",
                data=report_text,
                file_name=f"trading_report_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain",
                key="download_report"
            )


def get_trades_for_period(period: str) -> List[TradeResult]:
    """Obtiene trades para un período específico de la base de datos"""
    storage = get_storage()
    all_trades = storage.get_all_trade_results()
    
    if not all_trades:
        return []
    
    now = datetime.now()
    if period == "Última semana":
        cutoff = now - timedelta(days=7)
    elif period == "Último mes":
        cutoff = now - timedelta(days=30)
    elif period == "Últimos 3 meses":
        cutoff = now - timedelta(days=90)
    else:  # Todo el historial
        return all_trades
        
    return [t for t in all_trades if t.close_time >= cutoff]


def get_all_trades() -> List[TradeResult]:
    """Obtiene todos los trades de la base de datos"""
    storage = get_storage()
    return storage.get_all_trade_results()



def generate_csv_export(export_type: str, start_date, end_date) -> str:
    """Genera exportación CSV"""
    # Datos de ejemplo
    df = pd.DataFrame({
        'Fecha': [datetime.now() - timedelta(days=i) for i in range(10)],
        'Símbolo': ['EURUSD'] * 10,
        'Tipo': ['BUY', 'SELL'] * 5,
        'Volumen': [0.1] * 10,
        'Profit': [45.50, -23.00, 67.00, -15.50, 32.00] * 2
    })
    
    return df.to_csv(index=False)


def generate_excel_export(export_type: str, start_date, end_date) -> bytes:
    """Genera exportación Excel"""
    df = pd.DataFrame({
        'Fecha': [datetime.now() - timedelta(days=i) for i in range(10)],
        'Símbolo': ['EURUSD'] * 10,
        'Tipo': ['BUY', 'SELL'] * 5,
        'Volumen': [0.1] * 10,
        'Profit': [45.50, -23.00, 67.00, -15.50, 32.00] * 2
    })
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Trades', index=False)
    
    return output.getvalue()


def generate_text_report(start_date, end_date) -> str:
    """Genera reporte en texto"""
    trades = get_all_trades()
    
    if not trades:
        return f"""
═══════════════════════════════════════════════════════════
                    REPORTE DE TRADING
═══════════════════════════════════════════════════════════

Período: {start_date} - {end_date}

No hay operaciones registradas en este período.

═══════════════════════════════════════════════════════════
        Generado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
═══════════════════════════════════════════════════════════
        """
    
    analytics = TradingAnalytics(trades)
    return analytics.generate_report()
