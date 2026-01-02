"""
Technical Analysis Agent - Agente de análisis técnico con indicadores
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from loguru import logger
import numpy as np

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from .base_agent import BaseAgent, AgentResult
from scraping.storage import get_storage



class TrendDirection(Enum):
    """Dirección de tendencia"""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class TechnicalSignal:
    """Señal técnica individual"""
    indicator: str
    value: float
    signal: str  # BUY/SELL/HOLD
    strength: float  # 0-1


class TechnicalAgent(BaseAgent):
    """
    Agente de análisis técnico que calcula indicadores y genera señales.
    
    Indicadores soportados:
    - EMA (Exponential Moving Average)
    - RSI (Relative Strength Index)
    - MACD (Moving Average Convergence Divergence)
    - Bollinger Bands
    - ATR (Average True Range)
    """
    
    def __init__(self):
        super().__init__("TechnicalAgent")
        self.storage = get_storage()

        
        # Configuración de indicadores
        self.config = {
            "ema_fast": 12,
            "ema_slow": 26,
            "rsi_period": 14,
            "rsi_overbought": 70,
            "rsi_oversold": 30,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "bb_period": 20,
            "bb_std": 2,
            "atr_period": 14
        }
    
    def execute(self, data: Any) -> AgentResult:
        """
        Ejecuta análisis técnico sobre datos de precio
        
        Args:
            data: Dict con "prices" (DataFrame o lista) y "symbol"
        """
        if not PANDAS_AVAILABLE:
            return AgentResult(
                agent_name=self.name,
                success=False,
                error="pandas no disponible"
            )
        
        if not data or "prices" not in data:
            return AgentResult(
                agent_name=self.name,
                success=False,
                error="No se proporcionaron datos de precio"
            )
        
        try:
            prices = data["prices"]
            symbol = data.get("symbol", "UNKNOWN")
            
            # Convertir a DataFrame si es necesario
            if isinstance(prices, list):
                df = pd.DataFrame(prices)
            else:
                df = prices.copy()
            
            # Verificar columnas requeridas
            required_cols = ["close"]
            if not all(col in df.columns for col in required_cols):
                # Intentar normalizar nombres de columnas
                df.columns = df.columns.str.lower()
            
            if "close" not in df.columns:
                return AgentResult(
                    agent_name=self.name,
                    success=False,
                    error="Columna 'close' no encontrada en datos"
                )
            
            # Calcular indicadores
            signals = []
            
            # EMA
            ema_signal = self._calculate_ema_signal(df)
            if ema_signal:
                signals.append(ema_signal)
            
            # RSI
            rsi_signal = self._calculate_rsi_signal(df)
            if rsi_signal:
                signals.append(rsi_signal)
            
            # MACD
            macd_signal = self._calculate_macd_signal(df)
            if macd_signal:
                signals.append(macd_signal)
            
            # Calcular señal combinada
            result = self._combine_signals(signals)
            
            # Guardar log en DB
            self.storage.save_agent_log(
                self.name,
                f"Análisis {symbol}",
                f"{result['signal']} (score: {result['score']})",
                True
            )
            
            return AgentResult(
                agent_name=self.name,
                success=True,
                data={
                    "symbol": symbol,
                    "signals": [
                        {
                            "indicator": s.indicator,
                            "value": s.value,
                            "signal": s.signal,
                            "strength": s.strength
                        } for s in signals
                    ],
                    "combined_signal": result["signal"],
                    "combined_score": result["score"],
                    "trend": result["trend"],
                    "atr": self._calculate_atr(df, self.config["atr_period"])
                }
            )
            
        except Exception as e:
            logger.error(f"Error en TechnicalAgent: {e}")
            return AgentResult(
                agent_name=self.name,
                success=False,
                error=str(e)
            )
    
    def _calculate_ema(self, series: pd.Series, period: int) -> pd.Series:
        """Calcula EMA"""
        return series.ewm(span=period, adjust=False).mean()
    
    def _calculate_ema_signal(self, df: pd.DataFrame) -> Optional[TechnicalSignal]:
        """Genera señal basada en cruce de EMAs"""
        try:
            close = df["close"]
            
            ema_fast = self._calculate_ema(close, self.config["ema_fast"])
            ema_slow = self._calculate_ema(close, self.config["ema_slow"])
            
            # Señal basada en posición relativa
            last_fast = ema_fast.iloc[-1]
            last_slow = ema_slow.iloc[-1]
            
            # Verificar cruce
            prev_fast = ema_fast.iloc[-2] if len(ema_fast) > 1 else last_fast
            prev_slow = ema_slow.iloc[-2] if len(ema_slow) > 1 else last_slow
            
            diff = (last_fast - last_slow) / last_slow * 100
            
            if prev_fast <= prev_slow and last_fast > last_slow:
                # Cruce alcista
                signal = "BUY"
                strength = min(abs(diff) / 0.5, 1.0)
            elif prev_fast >= prev_slow and last_fast < last_slow:
                # Cruce bajista
                signal = "SELL"
                strength = min(abs(diff) / 0.5, 1.0)
            elif last_fast > last_slow:
                signal = "BUY"
                strength = min(abs(diff) / 1.0, 0.7)
            else:
                signal = "SELL"
                strength = min(abs(diff) / 1.0, 0.7)
            
            return TechnicalSignal(
                indicator="EMA_CROSS",
                value=round(diff, 4),
                signal=signal,
                strength=round(strength, 2)
            )
            
        except Exception as e:
            logger.debug(f"Error calculando EMA: {e}")
            return None
    
    def _calculate_rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        """Calcula RSI"""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_rsi_signal(self, df: pd.DataFrame) -> Optional[TechnicalSignal]:
        """Genera señal basada en RSI"""
        try:
            rsi = self._calculate_rsi(df["close"], self.config["rsi_period"])
            last_rsi = rsi.iloc[-1]
            
            if pd.isna(last_rsi):
                return None
            
            if last_rsi < self.config["rsi_oversold"]:
                signal = "BUY"
                strength = (self.config["rsi_oversold"] - last_rsi) / self.config["rsi_oversold"]
            elif last_rsi > self.config["rsi_overbought"]:
                signal = "SELL"
                strength = (last_rsi - self.config["rsi_overbought"]) / (100 - self.config["rsi_overbought"])
            else:
                signal = "HOLD"
                # Cerca de 50 = más neutral
                strength = 1 - abs(last_rsi - 50) / 50
            
            return TechnicalSignal(
                indicator="RSI",
                value=round(last_rsi, 2),
                signal=signal,
                strength=round(min(strength, 1.0), 2)
            )
            
        except Exception as e:
            logger.debug(f"Error calculando RSI: {e}")
            return None
    
    def _calculate_macd_signal(self, df: pd.DataFrame) -> Optional[TechnicalSignal]:
        """Genera señal basada en MACD"""
        try:
            close = df["close"]
            
            # MACD Line
            ema_fast = self._calculate_ema(close, self.config["macd_fast"])
            ema_slow = self._calculate_ema(close, self.config["macd_slow"])
            macd_line = ema_fast - ema_slow
            
            # Signal Line
            signal_line = self._calculate_ema(macd_line, self.config["macd_signal"])
            
            # Histogram
            histogram = macd_line - signal_line
            
            last_macd = macd_line.iloc[-1]
            last_signal = signal_line.iloc[-1]
            last_hist = histogram.iloc[-1]
            prev_hist = histogram.iloc[-2] if len(histogram) > 1 else last_hist
            
            # Detectar cruce
            if prev_hist <= 0 and last_hist > 0:
                signal = "BUY"
                strength = 0.8
            elif prev_hist >= 0 and last_hist < 0:
                signal = "SELL"
                strength = 0.8
            elif last_hist > 0:
                signal = "BUY"
                strength = 0.5
            else:
                signal = "SELL"
                strength = 0.5
            
            return TechnicalSignal(
                indicator="MACD",
                value=round(last_hist, 6),
                signal=signal,
                strength=round(strength, 2)
            )
            
        except Exception as e:
            logger.debug(f"Error calculando MACD: {e}")
            return None

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calcula el Average True Range (ATR) actual"""
        try:
            high = df["high"]
            low = df["low"]
            close = df["close"].shift(1)
            
            tr1 = high - low
            tr2 = abs(high - close)
            tr3 = abs(low - close)
            
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=period).mean()
            
            val = atr.iloc[-1]
            return float(val) if not pd.isna(val) else 0.0
        except Exception as e:
            logger.error(f"Error calculando ATR: {e}")
            return 0.0
    
    def _combine_signals(self, signals: List[TechnicalSignal]) -> Dict[str, Any]:
        """Combina múltiples señales técnicas"""
        if not signals:
            return {
                "signal": "HOLD",
                "score": 0.0,
                "trend": "neutral"
            }
        
        # Pesos por indicador
        weights = {
            "EMA_CROSS": 0.35,
            "RSI": 0.30,
            "MACD": 0.35
        }
        
        total_weight = 0
        weighted_score = 0
        
        for sig in signals:
            weight = weights.get(sig.indicator, 0.33)
            
            # Convertir señal a score (-1 a 1)
            if sig.signal == "BUY":
                score = sig.strength
            elif sig.signal == "SELL":
                score = -sig.strength
            else:
                score = 0
            
            weighted_score += score * weight
            total_weight += weight
        
        final_score = weighted_score / total_weight if total_weight > 0 else 0
        
        # Determinar señal final
        if final_score > 0.3:
            signal = "BUY"
            trend = "bullish"
        elif final_score < -0.3:
            signal = "SELL"
            trend = "bearish"
        else:
            signal = "HOLD"
            trend = "neutral"
        
        return {
            "signal": signal,
            "score": round(final_score, 3),
            "trend": trend
        }
    
    def analyze_symbol(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """Wrapper conveniente para analizar un símbolo"""
        result = self.run({"prices": df, "symbol": symbol})
        
        if result.success:
            return result.data
        
        return {
            "symbol": symbol,
            "error": result.error,
            "combined_signal": "HOLD",
            "combined_score": 0.0
        }


if __name__ == "__main__":
    print("=" * 50)
    print("Test de TechnicalAgent")
    print("=" * 50)
    
    if not PANDAS_AVAILABLE:
        print("❌ pandas no disponible")
        exit(1)
    
    # Crear datos de prueba
    np.random.seed(42)
    n = 100
    
    # Simular precios con tendencia alcista
    base = 1.1000
    returns = np.random.randn(n) * 0.002 + 0.0002  # Drift positivo
    prices = base * np.cumprod(1 + returns)
    
    df = pd.DataFrame({
        "close": prices,
        "high": prices * (1 + np.abs(np.random.randn(n)) * 0.001),
        "low": prices * (1 - np.abs(np.random.randn(n)) * 0.001),
        "open": np.roll(prices, 1)
    })
    
    agent = TechnicalAgent()
    result = agent.analyze_symbol(df, "EURUSD")
    
    print(f"\nSímbolo: {result.get('symbol')}")
    print(f"Señal combinada: {result.get('combined_signal')}")
    print(f"Score: {result.get('combined_score')}")
    print(f"Tendencia: {result.get('trend')}")
    
    print("\nIndicadores individuales:")
    for sig in result.get("signals", []):
        print(f"  {sig['indicator']}: {sig['signal']} (valor: {sig['value']}, fuerza: {sig['strength']})")
