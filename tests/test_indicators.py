"""
Tests for TechnicalIndicators
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.indicators import TechnicalIndicators


class TestTechnicalIndicators:
    """Tests para indicadores técnicos"""
    
    @pytest.fixture
    def sample_data(self):
        """Genera datos OHLC de ejemplo"""
        np.random.seed(42)
        n = 100
        
        # Simular precio con tendencia
        base = 1.1000
        trend = np.cumsum(np.random.randn(n) * 0.0005)
        close = base + trend
        
        high = close + np.abs(np.random.randn(n) * 0.0003)
        low = close - np.abs(np.random.randn(n) * 0.0003)
        open_price = low + np.random.rand(n) * (high - low)
        
        return pd.DataFrame({
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'tick_volume': np.random.randint(100, 1000, n)
        })
    
    @pytest.fixture
    def indicators(self, sample_data):
        """Crea instancia de TechnicalIndicators"""
        return TechnicalIndicators(sample_data)
    
    def test_ema_calculation(self, indicators):
        """Test cálculo de EMA"""
        ema = indicators.ema(period=20)
        
        assert len(ema) == 100
        assert not ema.isna().all()
        # EMA debería seguir la tendencia del precio
        assert abs(ema.iloc[-1] - indicators.df['close'].iloc[-1]) < 0.01
    
    def test_rsi_bounds(self, indicators):
        """Test que RSI está entre 0 y 100"""
        rsi = indicators.rsi(period=14)
        
        valid_rsi = rsi.dropna()
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()
    
    def test_macd_components(self, indicators):
        """Test que MACD retorna componentes correctos"""
        macd, signal, hist = indicators.macd()
        
        assert len(macd) == 100
        assert len(signal) == 100
        assert len(hist) == 100
        
        # Histograma = MACD - Signal
        valid_idx = ~(macd.isna() | signal.isna())
        np.testing.assert_array_almost_equal(
            hist[valid_idx],
            (macd - signal)[valid_idx],
            decimal=10
        )
    
    def test_bollinger_bands(self, indicators):
        """Test Bollinger Bands"""
        upper, middle, lower = indicators.bollinger_bands(period=20, std_dev=2)
        
        # Upper siempre > middle > lower
        valid_idx = ~(upper.isna() | lower.isna())
        assert (upper[valid_idx] >= middle[valid_idx]).all()
        assert (middle[valid_idx] >= lower[valid_idx]).all()
    
    def test_atr_positive(self, indicators):
        """Test que ATR es siempre positivo"""
        atr = indicators.atr(period=14)
        
        valid_atr = atr.dropna()
        assert (valid_atr > 0).all()
    
    def test_calculate_all(self, indicators):
        """Test cálculo de todos los indicadores"""
        df = indicators.calculate_all()
        
        expected_columns = ['ema_20', 'ema_50', 'rsi', 'macd', 'macd_signal', 'atr']
        for col in expected_columns:
            assert col in df.columns, f"Missing column: {col}"


class TestSignalGeneration:
    """Tests para generación de señales"""
    
    @pytest.fixture
    def bullish_data(self):
        """Genera datos con tendencia alcista clara"""
        n = 100
        close = np.linspace(1.1000, 1.1500, n)  # Tendencia alcista
        high = close + 0.0005
        low = close - 0.0005
        
        return pd.DataFrame({
            'open': close - 0.0002,
            'high': high,
            'low': low,
            'close': close,
            'tick_volume': np.ones(n) * 500
        })
    
    @pytest.fixture
    def bearish_data(self):
        """Genera datos con tendencia bajista clara"""
        n = 100
        close = np.linspace(1.1500, 1.1000, n)  # Tendencia bajista
        high = close + 0.0005
        low = close - 0.0005
        
        return pd.DataFrame({
            'open': close + 0.0002,
            'high': high,
            'low': low,
            'close': close,
            'tick_volume': np.ones(n) * 500
        })
    
    def test_bullish_trend_detection(self, bullish_data):
        """Test detección de tendencia alcista"""
        indicators = TechnicalIndicators(bullish_data)
        df = indicators.calculate_all()
        
        # En tendencia alcista, EMA corta > EMA larga
        # y precio cerca de máximos
        last_close = df['close'].iloc[-1]
        last_ema20 = df['ema_20'].iloc[-1]
        
        # Precio debería estar cerca de EMA en tendencia fuerte
        assert abs(last_close - last_ema20) < 0.01
    
    def test_bearish_trend_detection(self, bearish_data):
        """Test detección de tendencia bajista"""
        indicators = TechnicalIndicators(bearish_data)
        df = indicators.calculate_all()
        
        last_close = df['close'].iloc[-1]
        last_ema20 = df['ema_20'].iloc[-1]
        
        assert abs(last_close - last_ema20) < 0.01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
