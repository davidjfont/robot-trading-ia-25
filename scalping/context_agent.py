"""
Context Agent - Capa 1 del Sistema de Scalping
Decide si hoy/ahora se puede hacer scalping
"""

from datetime import datetime
from typing import Dict, Any, Tuple
from loguru import logger
import numpy as np


class ContextAgent:
    """
    Agente de Contexto (Macro-Micro)
    
    Evalúa:
    - Sesgo de sesión (Asia/Londres/NY)
    - Volatilidad real (ATR dinámico)
    - Estado del mercado (Tendencial/Rango/Caótico)
    
    Si no hay estructura → NO TRADE
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.sessions = {
            "asia": {"start": 0, "end": 8},      # 00:00 - 08:00 UTC
            "london": {"start": 8, "end": 16},   # 08:00 - 16:00 UTC
            "ny": {"start": 13, "end": 21},      # 13:00 - 21:00 UTC
        }
        self.min_atr_threshold = self.config.get('min_atr_threshold', 0.0005)
        
    def analyze(self, symbol: str, rates_m5: list, rates_m15: list = None, current_spread: float = 0.0) -> Dict[str, Any]:
        """
        Analiza el contexto actual para decidir si tradear
        
        Returns:
            {
                'can_trade': bool,
                'market_state': str,  # 'trending', 'ranging', 'chaotic'
                'session': str,
                'atr': float,
                'reasons': list,
                'is_toxic': bool
            }
        """
        reasons = []
        
        # 1. Detectar sesión actual
        session = self._get_current_session()
        
        # 2. Calcular ATR dinámico
        atr = self._calculate_atr(rates_m5)
        
        # 3. Clasificar estado del mercado
        market_state, state_confidence = self._classify_market_state(rates_m5)
        
        # 4. Verificar contexto tóxico (Expert rule)
        is_toxic = self.is_toxic(symbol, current_spread, rates_m5)
        
        # 5. Evaluar si se puede tradear
        can_trade = True
        
        if is_toxic:
            can_trade = False
            reasons.append("Contexto tóxico detectado (Spread/ATR o Estructura)")
        
        # Regla 1: ATR mínimo
        if atr < self.min_atr_threshold:
            can_trade = False
            reasons.append(f"ATR muy bajo ({atr:.5f} < {self.min_atr_threshold})")
        
        # Regla 2: Mercado caótico = NO TRADE
        if market_state == "chaotic":
            can_trade = False
            reasons.append("Mercado caótico - estructura no clara")
        
        # Regla 3: Fuera de sesiones principales (opcional)
        if session == "off_hours":
            can_trade = False
            reasons.append("Fuera de horario de sesiones principales")
        
        # Regla 4: Rango muy comprimido sin breakout potencial
        if market_state == "ranging" and state_confidence < 0.5:
            can_trade = False
            reasons.append("Rango comprimido sin señal de breakout")
        
        result = {
            'can_trade': can_trade,
            'market_state': market_state,
            'state_confidence': state_confidence,
            'session': session,
            'atr': atr,
            'is_toxic': is_toxic,
            'reasons': reasons if not can_trade else ["Contexto favorable para scalping"]
        }
        
        logger.debug(f"[ContextAgent] {symbol}: {market_state} | ATR:{atr:.5f} | Session:{session} | Toxic:{is_toxic} | Trade:{can_trade}")
        
        return result

    def is_toxic(self, symbol: str, current_spread: float, rates_m5: list) -> bool:
        """
        Determina si el contexto es tóxico para el scalping.
        Basado en feedback experto: Spread/ATR, Volatilidad muerta o extrema, Chop Index.
        """
        if not rates_m5 or len(rates_m5) < 14:
            return True
            
        atr = self._calculate_atr(rates_m5)
        
        # 1. Spread Relativo Alto: spread / ATR > 0.5 (el spread es media vela o más)
        if atr > 0:
            relative_spread = current_spread / atr
            if relative_spread > 0.5:
                logger.warning(f"[Context] Toxic: Spread Relativo Alto ({relative_spread:.2f} > 0.5)")
                return True
        
        # 2. Volatilidad muerta
        if atr < 0.0001: # 1 pip en FX o 10 puntos en GER40
            logger.warning(f"[Context] Toxic: Volatilidad Muerta (ATR: {atr:.6f})")
            return True

        # 3. Estructura caótica/Chop (ADX bajo + Pendiente plana)
        market_state, state_confidence = self._classify_market_state(rates_m5)
        if market_state == "chaotic" and state_confidence > 0.7:
             logger.warning(f"[Context] Toxic: Estructura Caótica Reconfirmada")
             return True
             
        return False
    
    def _get_current_session(self) -> str:
        """Detecta la sesión de trading actual"""
        now = datetime.utcnow()
        hour = now.hour
        
        # Verificar superposición London-NY (mejor momento)
        if 13 <= hour < 16:
            return "london_ny_overlap"
        elif self.sessions["london"]["start"] <= hour < self.sessions["london"]["end"]:
            return "london"
        elif self.sessions["ny"]["start"] <= hour < self.sessions["ny"]["end"]:
            return "ny"
        elif self.sessions["asia"]["start"] <= hour < self.sessions["asia"]["end"]:
            return "asia"
        else:
            return "off_hours"
    
    def _calculate_atr(self, rates: list, period: int = 14) -> float:
        """Calcula ATR dinámico de forma robusta"""
        if not rates or len(rates) < 2:
            return 0.0
        
        tr_values = []
        # Usar todos los datos disponibles hasta period o len(rates)
        count = min(len(rates), period + 1)
        
        for i in range(len(rates) - count + 1, len(rates)):
            high = rates[i]['high']
            low = rates[i]['low']
            prev_close = rates[i-1]['close']
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_values.append(tr)
        
        return np.mean(tr_values) if tr_values else 0.0
    
    def _classify_market_state(self, rates: list) -> Tuple[str, float]:
        """
        Clasifica el estado del mercado
        
        Returns:
            (state, confidence)
            - 'trending': tendencia clara
            - 'ranging': rango/consolidación
            - 'chaotic': sin estructura
        """
        if not rates or len(rates) < 20:
            return "chaotic", 0.0
        
        closes = [r['close'] for r in rates[-20:]]
        highs = [r['high'] for r in rates[-20:]]
        lows = [r['low'] for r in rates[-20:]]
        
        # Calcular pendiente de la regresión lineal
        x = np.arange(len(closes))
        slope = np.polyfit(x, closes, 1)[0]
        
        # Calcular rango promedio
        avg_range = np.mean([h - l for h, l in zip(highs, lows)])
        
        # Calcular desviación estándar
        std_dev = np.std(closes)
        
        # ADX simplificado (basado en movimiento direccional)
        dm_plus = sum(max(highs[i] - highs[i-1], 0) for i in range(1, len(highs)))
        dm_minus = sum(max(lows[i-1] - lows[i], 0) for i in range(1, len(lows)))
        
        directional_strength = abs(dm_plus - dm_minus) / (dm_plus + dm_minus + 0.0001)
        
        # Clasificación
        slope_normalized = abs(slope) / (avg_range + 0.0001)
        
        if slope_normalized > 0.1 and directional_strength > 0.3:
            # Tendencia clara
            return "trending", min(1.0, slope_normalized + directional_strength)
        elif std_dev < avg_range * 0.5:
            # Rango comprimido
            compression_score = 1 - (std_dev / (avg_range + 0.0001))
            return "ranging", compression_score
        else:
            # Caótico
            return "chaotic", 1 - directional_strength
    
    def get_session_bias(self, session: str) -> str:
        """Retorna el sesgo típico de cada sesión"""
        biases = {
            "asia": "range",  # Asia suele ser rango
            "london": "breakout",  # Londres suele tener breakouts
            "ny": "continuation",  # NY continúa tendencias
            "london_ny_overlap": "high_volatility",  # Mayor volatilidad
            "off_hours": "avoid"
        }
        return biases.get(session, "neutral")
