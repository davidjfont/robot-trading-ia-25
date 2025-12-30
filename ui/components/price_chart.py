"""
Price Chart - Gráfico de velas con indicadores y análisis LLM
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
from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mt5.connector import MT5Connector
from strategies.indicators import TechnicalIndicators
from agents.sentiment_agent import SentimentAgent
from agents.technical_agent import TechnicalAgent
from scraping.storage import get_storage



def render_price_chart(symbol: str = "EURUSD", timeframe: str = "M15", 
                       llm_analysis: Optional[Dict] = None):
    """Renderiza gráfico de velas con indicadores y análisis LLM"""
    
    st.subheader(f"📊 Gráfico {symbol} - {timeframe}")
    
    # Controles del gráfico
    col1, col2, col3, col4 = st.columns(4)
    
    # Sincronización inteligente con la barra lateral

    if 'prev_sidebar_symbol' not in st.session_state:
        st.session_state['prev_sidebar_symbol'] = symbol
    if 'prev_sidebar_tf' not in st.session_state:
        st.session_state['prev_sidebar_tf'] = timeframe

    # Si el usuario cambia algo en la barra lateral, forzamos actualización del widget correspondiente
    if st.session_state['prev_sidebar_symbol'] != symbol:
        st.session_state['chart_symbol_selector'] = symbol
        st.session_state['prev_sidebar_symbol'] = symbol

    if st.session_state['prev_sidebar_tf'] != timeframe:
        st.session_state['chart_tf_selector'] = timeframe
        st.session_state['prev_sidebar_tf'] = timeframe

    # Inicializar valores de los selectores si no existen
    if 'chart_symbol_selector' not in st.session_state:
        st.session_state['chart_symbol_selector'] = symbol
    if 'chart_tf_selector' not in st.session_state:
        st.session_state['chart_tf_selector'] = timeframe

    # Obtener lista de símbolos de la sesión o usar una por defecto más amplia
    selected_symbols = st.session_state.get('selected_symbols', [])
    if not selected_symbols:
        symbols_list = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "GOLD", "BTCUSD"]
    else:
        symbols_list = selected_symbols

    # Asegurar que el símbolo actual esté en la lista (evitar errores de Streamlit selectbox)
    if symbol not in symbols_list:
        symbols_list = list(symbols_list) + [symbol]

    tf_list = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]

    with col1:
        chart_symbol = st.selectbox(
            "Símbolo",
            symbols_list,
            key="chart_symbol_selector"
        )
    
    with col2:
        chart_timeframe = st.selectbox(
            "Timeframe",
            tf_list,
            key="chart_tf_selector"
        )

    
    with col3:
        num_candles = st.selectbox(
            "Velas",
            [50, 100, 200, 500],
            index=1,
            key="chart_candles_selector"
        )
    
    with col4:
        show_indicators = st.multiselect(
            "Indicadores",
            ["EMA 20", "EMA 50", "EMA 200", "RSI", "MACD", "Bollinger"],
            default=["EMA 20", "EMA 50"],
            key="chart_ind_selector"
        )

    
    # Obtener datos
    df = get_ohlc_data(chart_symbol, chart_timeframe, num_candles)
    
    if df is None or df.empty:
        st.warning("No se pudieron obtener datos del mercado")
        # Mostrar datos de ejemplo
        df = generate_sample_data(num_candles)
    
    # Calcular indicadores
    df = calculate_indicators(df, show_indicators)
    
    # Crear gráfico
    fig = create_chart(df, chart_symbol, show_indicators, llm_analysis)
    
    # Mostrar gráfico
    st.plotly_chart(fig, width='stretch')
    
    # Análisis dinámico si no se proporciona uno fijo
    if llm_analysis is None:
        with st.spinner(f"Analizando {chart_symbol}..."):
            llm_analysis = get_current_llm_analysis(chart_symbol, df)
    
    # Panel de análisis LLM
    if llm_analysis:
        render_llm_analysis_panel(llm_analysis)

    
    return chart_symbol, chart_timeframe


def get_ohlc_data(symbol: str, timeframe: str, num_candles: int) -> Optional[pd.DataFrame]:
    """Obtiene datos OHLC de MT5 reusando el conector de la sesión"""
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

        
        # Pasar el timeframe como string directamente al conector
        data = connector.get_rates(symbol, timeframe, num_candles)

        # NOTA: No desconectamos
        
        if data is not None and len(data) > 0:

            df = pd.DataFrame(data)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            return df
        
        return None
    
    except Exception as e:
        return None


def generate_sample_data(num_candles: int) -> pd.DataFrame:
    """Genera datos de ejemplo para demostración"""
    np.random.seed(42)
    
    dates = pd.date_range(end=datetime.now(), periods=num_candles, freq='15min')
    
    # Generar precios simulados
    base_price = 1.0850
    returns = np.random.randn(num_candles) * 0.001
    close = base_price + np.cumsum(returns)
    
    high = close + np.abs(np.random.randn(num_candles) * 0.0005)
    low = close - np.abs(np.random.randn(num_candles) * 0.0005)
    
    # Asegurar que open esté entre high y low
    open_prices = low + np.random.rand(num_candles) * (high - low)
    
    df = pd.DataFrame({
        'time': dates,
        'open': open_prices,
        'high': high,
        'low': low,
        'close': close,
        'tick_volume': np.random.randint(100, 1000, num_candles)
    })
    
    return df


def calculate_indicators(df: pd.DataFrame, indicators: List[str]) -> pd.DataFrame:
    """Calcula indicadores técnicos"""
    
    if "EMA 20" in indicators:
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    
    if "EMA 50" in indicators:
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    if "EMA 200" in indicators:
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    if "RSI" in indicators:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
    
    if "MACD" in indicators:
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
    
    if "Bollinger" in indicators:
        df['bb_mid'] = df['close'].rolling(window=20).mean()
        df['bb_std'] = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_mid'] + (df['bb_std'] * 2)
        df['bb_lower'] = df['bb_mid'] - (df['bb_std'] * 2)
    
    return df


def create_chart(df: pd.DataFrame, symbol: str, indicators: List[str],
                 llm_analysis: Optional[Dict] = None) -> go.Figure:
    """Crea el gráfico con Plotly"""
    
    # Determinar número de subplots
    num_rows = 1
    row_heights = [0.7]
    
    if "RSI" in indicators:
        num_rows += 1
        row_heights.append(0.15)
    
    if "MACD" in indicators:
        num_rows += 1
        row_heights.append(0.15)
    
    # Crear subplots
    fig = make_subplots(
        rows=num_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights
    )
    
    # Gráfico de velas
    fig.add_trace(
        go.Candlestick(
            x=df['time'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name=symbol,
            increasing_line_color='#00c853',
            decreasing_line_color='#ff1744'
        ),
        row=1, col=1
    )
    
    # EMAs
    if "EMA 20" in indicators and 'ema_20' in df.columns:
        fig.add_trace(
            go.Scatter(x=df['time'], y=df['ema_20'], name='EMA 20',
                      line=dict(color='#2196F3', width=1)),
            row=1, col=1
        )
    
    if "EMA 50" in indicators and 'ema_50' in df.columns:
        fig.add_trace(
            go.Scatter(x=df['time'], y=df['ema_50'], name='EMA 50',
                      line=dict(color='#FF9800', width=1)),
            row=1, col=1
        )
    
    if "EMA 200" in indicators and 'ema_200' in df.columns:
        fig.add_trace(
            go.Scatter(x=df['time'], y=df['ema_200'], name='EMA 200',
                      line=dict(color='#9C27B0', width=1)),
            row=1, col=1
        )
    
    # Bollinger Bands
    if "Bollinger" in indicators and 'bb_upper' in df.columns:
        fig.add_trace(
            go.Scatter(x=df['time'], y=df['bb_upper'], name='BB Upper',
                      line=dict(color='rgba(150,150,150,0.5)', width=1)),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=df['time'], y=df['bb_lower'], name='BB Lower',
                      line=dict(color='rgba(150,150,150,0.5)', width=1),
                      fill='tonexty', fillcolor='rgba(150,150,150,0.1)'),
            row=1, col=1
        )
    
    # RSI
    current_row = 2
    if "RSI" in indicators and 'rsi' in df.columns:
        fig.add_trace(
            go.Scatter(x=df['time'], y=df['rsi'], name='RSI',
                      line=dict(color='#673AB7', width=1)),
            row=current_row, col=1
        )
        # Líneas de sobrecompra/sobreventa
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=current_row, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=current_row, col=1)
        current_row += 1
    
    # MACD
    if "MACD" in indicators and 'macd' in df.columns:
        fig.add_trace(
            go.Scatter(x=df['time'], y=df['macd'], name='MACD',
                      line=dict(color='#2196F3', width=1)),
            row=current_row, col=1
        )
        fig.add_trace(
            go.Scatter(x=df['time'], y=df['macd_signal'], name='Signal',
                      line=dict(color='#FF9800', width=1)),
            row=current_row, col=1
        )
        # Histograma
        colors = ['#00c853' if val >= 0 else '#ff1744' for val in df['macd_hist']]
        fig.add_trace(
            go.Bar(x=df['time'], y=df['macd_hist'], name='MACD Hist',
                  marker_color=colors),
            row=current_row, col=1
        )
    
    # Añadir anotación de análisis LLM
    if llm_analysis:
        direction = llm_analysis.get('direction', 'HOLD')
        confidence = llm_analysis.get('confidence', 0)
        
        arrow_color = '#00c853' if direction == 'BUY' else '#ff1744' if direction == 'SELL' else '#ffc107'
        
        # Añadir anotación en la última vela
        last_time = df['time'].iloc[-1]
        last_price = df['close'].iloc[-1]
        
        fig.add_annotation(
            x=last_time,
            y=last_price,
            text=f"🤖 {direction} ({confidence*100:.0f}%)",
            showarrow=True,
            arrowhead=2,
            arrowcolor=arrow_color,
            font=dict(color=arrow_color, size=12),
            bgcolor="rgba(0,0,0,0.7)",
            row=1, col=1
        )
    
    # Configuración del layout
    fig.update_layout(
        title=f"📈 {symbol}",
        height=600,
        template="plotly_dark",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_rangeslider_visible=False,
        margin=dict(l=50, r=50, t=50, b=50)
    )
    
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')
    
    return fig


def render_llm_analysis_panel(analysis: Dict):
    """Renderiza panel de análisis LLM"""
    
    st.subheader("🧠 Análisis IA")
    
    direction = analysis.get('direction', 'HOLD')
    confidence = analysis.get('confidence', 0)
    reasoning = analysis.get('reasoning', 'Sin análisis disponible')
    
    # Color según dirección
    if direction == "BUY":
        color = "green"
        emoji = "📈"
    elif direction == "SELL":
        color = "red"
        emoji = "📉"
    else:
        color = "orange"
        emoji = "⏸️"
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.markdown(f"""
        <div style="text-align: center; padding: 1rem; background: linear-gradient(135deg, {color}, #333); border-radius: 10px;">
            <h1 style="margin: 0;">{emoji}</h1>
            <h2 style="margin: 0.5rem 0; color: white;">{direction}</h2>
            <h3 style="margin: 0; color: rgba(255,255,255,0.8);">{confidence*100:.0f}%</h3>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("**Razonamiento:**")
        st.write(reasoning)
        
        # Factores del análisis
        if 'factors' in analysis:
            st.markdown("**Factores considerados:**")
            for factor, score in analysis['factors'].items():
                st.progress(abs(score), text=f"{factor}: {score:+.2f}")


def get_current_llm_analysis(symbol: str, df: pd.DataFrame) -> Optional[Dict]:
    """Obtiene el análisis LLM actual para un símbolo combinando técnica y sentimiento"""
    try:
        # 1. Análisis Técnico
        tech_agent = TechnicalAgent()
        tech_result = tech_agent.analyze_symbol(df, symbol)
        
        # 2. Análisis de Sentimiento
        sentiment_agent = SentimentAgent()
        storage = get_storage()
        
        # Obtener noticias recientes procesadas
        recent_news = storage.get_recent_news(hours=48, processed=True)
        news_texts = [n.title for n in recent_news]
        
        if news_texts:
            sent_result = sentiment_agent.analyze_for_symbol(news_texts, symbol)
        else:
            sent_result = {"sentiment": "neutral", "score": 0.0, "confidence": 0.0, "relevant_news": 0}
            
        # 3. Combinar resultados para la UI
        # Mapeo de scores a dirección
        tech_score = tech_result.get("combined_score", 0) if tech_result else 0
        sent_score = sent_result.get("score", 0) if sent_result else 0
        combined_score = (tech_score * 0.6) + (sent_score * 0.4)
        
        if combined_score > 0.2:
            direction = "BUY"
        elif combined_score < -0.2:
            direction = "SELL"
        else:
            direction = "HOLD"
            
        # Generar razonamiento dinámico
        tech_sig = tech_result.get("combined_signal", "HOLD") if tech_result else "HOLD"
        sent_sig = sent_result.get("sentiment", "neutral") if sent_result else "neutral"
        relevant_news = sent_result.get("relevant_news", 0) if sent_result else 0
        
        reasoning = f"El análisis técnico es {tech_sig} con un score de {tech_score:.2f}. "
        reasoning += f"El sentimiento de las noticias es {sent_sig} (basado en {relevant_news} noticias relevantes). "
        
        if direction == "BUY":
            reasoning += "La convergencia de factores sugiere una oportunidad de COMPRA."
        elif direction == "SELL":
            reasoning += "Los indicadores sugieren una presión bajista, recomendando VENTA."
        else:
            reasoning += "No hay una dirección clara en este momento, se recomienda ESPERAR."

        return {
            'direction': direction,
            'confidence': min(abs(combined_score), 1.0),
            'reasoning': reasoning,
            'factors': {
                'Técnico': tech_score,
                'Sentimiento': sent_score,
                'Fundamental': 0.15  # Placeholder para futuros datos macro
            }
        }
    except Exception as e:
        logger.warning(f"Error generando análisis dinámico para {symbol}: {e}")
        # Retornar análisis por defecto en lugar de None
        return {
            'direction': 'HOLD',
            'confidence': 0.0,
            'reasoning': f'Análisis no disponible temporalmente. Sistema basándose en datos técnicos manuales.',
            'factors': {
                'Técnico': 0.0,
                'Sentimiento': 0.0,
                'Fundamental': 0.0
            }
        }

