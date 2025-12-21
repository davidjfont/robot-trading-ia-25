"""
Indicators - Indicadores técnicos para análisis de mercado
"""

from typing import Optional, Dict, Any
import numpy as np

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


class TechnicalIndicators:
    """
    Colección de indicadores técnicos para trading.
    
    Todos los métodos son estáticos para facilitar su uso.
    """
    
    @staticmethod
    def sma(series: 'pd.Series', period: int = 20) -> 'pd.Series':
        """Simple Moving Average"""
        return series.rolling(window=period).mean()
    
    @staticmethod
    def ema(series: 'pd.Series', period: int = 20) -> 'pd.Series':
        """Exponential Moving Average"""
        return series.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def rsi(series: 'pd.Series', period: int = 14) -> 'pd.Series':
        """
        Relative Strength Index
        
        RSI > 70: Sobrecompra
        RSI < 30: Sobreventa
        """
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def macd(series: 'pd.Series', fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, 'pd.Series']:
        """
        Moving Average Convergence Divergence
        
        Returns:
            Dict con 'macd', 'signal', 'histogram'
        """
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram
        }
    
    @staticmethod
    def bollinger_bands(series: 'pd.Series', period: int = 20, std_dev: float = 2.0) -> Dict[str, 'pd.Series']:
        """
        Bollinger Bands
        
        Returns:
            Dict con 'upper', 'middle', 'lower'
        """
        middle = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        return {
            "upper": upper,
            "middle": middle,
            "lower": lower
        }
    
    @staticmethod
    def atr(high: 'pd.Series', low: 'pd.Series', close: 'pd.Series', period: int = 14) -> 'pd.Series':
        """
        Average True Range - Mide volatilidad
        """
        prev_close = close.shift(1)
        
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()
        
        return atr
    
    @staticmethod
    def stochastic(high: 'pd.Series', low: 'pd.Series', close: 'pd.Series', 
                   k_period: int = 14, d_period: int = 3) -> Dict[str, 'pd.Series']:
        """
        Stochastic Oscillator
        
        Returns:
            Dict con '%K' y '%D'
        """
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        
        k = 100 * (close - lowest_low) / (highest_high - lowest_low)
        d = k.rolling(window=d_period).mean()
        
        return {
            "k": k,
            "d": d
        }
    
    @staticmethod
    def momentum(series: 'pd.Series', period: int = 10) -> 'pd.Series':
        """Momentum indicator"""
        return series - series.shift(period)
    
    @staticmethod
    def williams_r(high: 'pd.Series', low: 'pd.Series', close: 'pd.Series', period: int = 14) -> 'pd.Series':
        """Williams %R"""
        highest_high = high.rolling(window=period).max()
        lowest_low = low.rolling(window=period).min()
        
        wr = -100 * (highest_high - close) / (highest_high - lowest_low)
        return wr
    
    @staticmethod
    def cci(high: 'pd.Series', low: 'pd.Series', close: 'pd.Series', period: int = 20) -> 'pd.Series':
        """Commodity Channel Index"""
        typical_price = (high + low + close) / 3
        sma = typical_price.rolling(window=period).mean()
        mad = typical_price.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())
        
        cci = (typical_price - sma) / (0.015 * mad)
        return cci
    
    @staticmethod
    def pivot_points(high: float, low: float, close: float) -> Dict[str, float]:
        """
        Calcula niveles de pivot points
        
        Args:
            high: Máximo del período anterior
            low: Mínimo del período anterior
            close: Cierre del período anterior
        
        Returns:
            Dict con Pivot, R1, R2, R3, S1, S2, S3
        """
        pivot = (high + low + close) / 3
        
        return {
            "pivot": round(pivot, 5),
            "r1": round(2 * pivot - low, 5),
            "r2": round(pivot + (high - low), 5),
            "r3": round(high + 2 * (pivot - low), 5),
            "s1": round(2 * pivot - high, 5),
            "s2": round(pivot - (high - low), 5),
            "s3": round(low - 2 * (high - pivot), 5)
        }


if __name__ == "__main__":
    print("=" * 50)
    print("Test de Indicadores Técnicos")
    print("=" * 50)
    
    if not PANDAS_AVAILABLE:
        print("❌ pandas no disponible")
        exit(1)
    
    # Crear datos de prueba
    np.random.seed(42)
    n = 100
    
    base = 1.1000
    returns = np.random.randn(n) * 0.002
    close = pd.Series(base * np.cumprod(1 + returns))
    high = close * (1 + np.abs(np.random.randn(n)) * 0.001)
    low = close * (1 - np.abs(np.random.randn(n)) * 0.001)
    
    # Test indicadores
    print("\n--- SMA(20) ---")
    sma = TechnicalIndicators.sma(close, 20)
    print(f"Último valor: {sma.iloc[-1]:.5f}")
    
    print("\n--- EMA(20) ---")
    ema = TechnicalIndicators.ema(close, 20)
    print(f"Último valor: {ema.iloc[-1]:.5f}")
    
    print("\n--- RSI(14) ---")
    rsi = TechnicalIndicators.rsi(close, 14)
    print(f"Último valor: {rsi.iloc[-1]:.2f}")
    
    print("\n--- MACD ---")
    macd = TechnicalIndicators.macd(close)
    print(f"MACD: {macd['macd'].iloc[-1]:.6f}")
    print(f"Signal: {macd['signal'].iloc[-1]:.6f}")
    print(f"Histogram: {macd['histogram'].iloc[-1]:.6f}")
    
    print("\n--- Bollinger Bands ---")
    bb = TechnicalIndicators.bollinger_bands(close)
    print(f"Upper: {bb['upper'].iloc[-1]:.5f}")
    print(f"Middle: {bb['middle'].iloc[-1]:.5f}")
    print(f"Lower: {bb['lower'].iloc[-1]:.5f}")
    
    print("\n--- ATR(14) ---")
    atr = TechnicalIndicators.atr(high, low, close, 14)
    print(f"ATR: {atr.iloc[-1]:.6f}")
    
    print("\n--- Pivot Points ---")
    pivots = TechnicalIndicators.pivot_points(high.iloc[-1], low.iloc[-1], close.iloc[-1])
    print(f"Pivot: {pivots['pivot']}")
    print(f"R1: {pivots['r1']}, S1: {pivots['s1']}")
