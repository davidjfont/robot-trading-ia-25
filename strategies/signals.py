"""
Signals - Generador de señales de trading combinando múltiples fuentes
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from loguru import logger
import yaml
import os

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


class SignalType(Enum):
    """Tipos de señal"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradingSignal:
    """Señal de trading completa"""
    symbol: str
    signal_type: SignalType
    strength: float  # 0-1
    technical_score: float
    sentiment_score: float
    news_score: float
    combined_score: float
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "type": self.signal_type.value,
            "strength": self.strength,
            "technical_score": self.technical_score,
            "sentiment_score": self.sentiment_score,
            "news_score": self.news_score,
            "combined_score": self.combined_score,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


class SignalGenerator:
    """
    Generador de señales de trading que combina análisis técnico,
    sentimiento y noticias para producir señales accionables.
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        
        # Pesos de la estrategia
        strategy_config = self.config.get("strategy", {})
        weights = strategy_config.get("weights", {})
        
        self.weight_technical = weights.get("technical", 0.4)
        self.weight_sentiment = weights.get("sentiment", 0.3)
        self.weight_news = weights.get("news", 0.3)
        
        self.signal_threshold = strategy_config.get("signal_threshold", 0.5)
        
        logger.info(f"SignalGenerator inicializado. Pesos: T={self.weight_technical}, S={self.weight_sentiment}, N={self.weight_news}")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Carga configuración"""
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            full_path = os.path.join(base_dir, config_path)
            
            with open(full_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception:
            return {}
    
    def generate_signal(
        self,
        symbol: str,
        technical_data: Dict[str, Any],
        sentiment_data: Dict[str, Any],
        news_data: Dict[str, Any]
    ) -> TradingSignal:
        """
        Genera una señal de trading combinando múltiples fuentes
        
        Args:
            symbol: Par de divisas (ej: "EURUSD")
            technical_data: Datos del TechnicalAgent
            sentiment_data: Datos del SentimentAgent
            news_data: Datos del NewsAgent
        
        Returns:
            TradingSignal con la señal combinada
        """
        # Extraer scores de cada fuente
        technical_score = self._extract_technical_score(technical_data)
        sentiment_score = self._extract_sentiment_score(sentiment_data)
        news_score = self._extract_news_score(news_data)
        
        # Combinar scores con pesos
        combined_score = (
            technical_score * self.weight_technical +
            sentiment_score * self.weight_sentiment +
            news_score * self.weight_news
        )
        
        # Determinar tipo de señal
        if combined_score >= self.signal_threshold:
            signal_type = SignalType.BUY
        elif combined_score <= -self.signal_threshold:
            signal_type = SignalType.SELL
        else:
            signal_type = SignalType.HOLD
        
        # Calcular fuerza de la señal
        strength = min(abs(combined_score), 1.0)
        
        signal = TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            strength=round(strength, 3),
            technical_score=round(technical_score, 3),
            sentiment_score=round(sentiment_score, 3),
            news_score=round(news_score, 3),
            combined_score=round(combined_score, 3),
            metadata={
                "technical_signal": technical_data.get("combined_signal"),
                "technical_details": technical_data.get("signals", []),
                "sentiment": sentiment_data.get("sentiment"),
                "sentiment_details": sentiment_data,
                "news_count": news_data.get("news_count", 0),
                "news_details": news_data
            }
        )
        
        logger.debug(f"Señal generada para {symbol}: {signal_type.value} (score: {combined_score:.3f})")
        
        return signal
    
    def _extract_technical_score(self, data: Dict[str, Any]) -> float:
        """Extrae score técnico normalizado (-1 a 1)"""
        if not data:
            return 0.0
        
        # Si viene del TechnicalAgent
        if "combined_score" in data:
            return data["combined_score"]
        
        # Si viene como señal simple
        signal = data.get("signal", "HOLD").upper()
        strength = data.get("strength", 0.5)
        
        if signal == "BUY":
            return strength
        elif signal == "SELL":
            return -strength
        else:
            return 0.0
    
    def _extract_sentiment_score(self, data: Dict[str, Any]) -> float:
        """Extrae score de sentimiento normalizado (-1 a 1)"""
        if not data:
            return 0.0
        
        # Score directo
        if "score" in data:
            return data["score"]
        
        # Basado en sentimiento textual
        sentiment = data.get("sentiment", "neutral").lower()
        confidence = data.get("confidence", 0.5)
        
        if sentiment == "bullish":
            return confidence
        elif sentiment == "bearish":
            return -confidence
        else:
            return 0.0
    
    def _extract_news_score(self, data: Dict[str, Any]) -> float:
        """Extrae score de noticias normalizado (-1 a 1)"""
        if not data:
            return 0.0
        
        # Score directo
        if "score" in data:
            return data["score"]
        
        # Basado en sentimiento de noticias
        sentiment = data.get("sentiment", "neutral").lower()
        confidence = data.get("confidence", 0.5)
        news_count = data.get("news_count", 0)
        
        # Ajustar confianza por cantidad de noticias
        count_factor = min(news_count / 5, 1.0)
        
        if sentiment == "bullish":
            return confidence * count_factor
        elif sentiment == "bearish":
            return -confidence * count_factor
        else:
            return 0.0
    
    def should_trade(self, signal: TradingSignal) -> bool:
        """Determina si una señal es lo suficientemente fuerte para operar"""
        if signal.signal_type == SignalType.HOLD:
            return False
        
        return signal.strength >= 0.3  # Mínimo 30% de fuerza
    
    def get_signals_summary(self, signals: List[TradingSignal]) -> Dict[str, Any]:
        """Genera resumen de múltiples señales"""
        if not signals:
            return {"total": 0, "buy": 0, "sell": 0, "hold": 0}
        
        buy_signals = [s for s in signals if s.signal_type == SignalType.BUY]
        sell_signals = [s for s in signals if s.signal_type == SignalType.SELL]
        hold_signals = [s for s in signals if s.signal_type == SignalType.HOLD]
        
        return {
            "total": len(signals),
            "buy": len(buy_signals),
            "sell": len(sell_signals),
            "hold": len(hold_signals),
            "strongest_buy": max((s.symbol for s in buy_signals), default=None, key=lambda x: next((s.strength for s in buy_signals if s.symbol == x), 0)),
            "strongest_sell": max((s.symbol for s in sell_signals), default=None, key=lambda x: next((s.strength for s in sell_signals if s.symbol == x), 0)),
            "avg_strength": sum(s.strength for s in signals) / len(signals)
        }


if __name__ == "__main__":
    print("=" * 50)
    print("Test de SignalGenerator")
    print("=" * 50)
    
    generator = SignalGenerator()
    
    # Datos de prueba
    technical = {
        "combined_score": 0.6,
        "combined_signal": "BUY",
        "trend": "bullish"
    }
    
    sentiment = {
        "sentiment": "bullish",
        "score": 0.45,
        "confidence": 0.7
    }
    
    news = {
        "sentiment": "bullish",
        "score": 0.3,
        "news_count": 5
    }
    
    signal = generator.generate_signal("EURUSD", technical, sentiment, news)
    
    print(f"\n📊 Señal para {signal.symbol}")
    print(f"   Tipo: {signal.signal_type.value}")
    print(f"   Fuerza: {signal.strength:.0%}")
    print(f"   Score combinado: {signal.combined_score:.3f}")
    print(f"   - Técnico: {signal.technical_score:.3f}")
    print(f"   - Sentimiento: {signal.sentiment_score:.3f}")
    print(f"   - Noticias: {signal.news_score:.3f}")
    print(f"\n   ¿Operar? {'✅ SÍ' if generator.should_trade(signal) else '❌ NO'}")
