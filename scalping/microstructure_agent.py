"""
Microstructure Agent - Capa 2 del Sistema de Scalping
El que manda - Observa precio en M1/M5, no indicadores
"""

from typing import Dict, Any, List
from loguru import logger
import numpy as np


class MicrostructureAgent:
    """
    Agente de Microestructura - EL QUE MANDA
    
    Observa en M1/M5:
    - Velocidad del precio (no indicadores lentos)
    - Rechazos repetidos en el mismo nivel
    - Micro-impulsos + absorción
    - Velas "intención" (cuerpo dominante + cierre limpio)
    
    Este agente NO predice, REACCIONA
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.min_velocity_threshold = 0.0002  # Movimiento mínimo por vela
        self.rejection_count_threshold = 2  # Mínimo rechazos para nivel
        self.intention_body_ratio = 0.7  # Cuerpo > 70% del rango
        
    def analyze(self, rates_m1: list, rates_m5: list) -> Dict[str, Any]:
        """
        Analiza microestructura para detectar oportunidades de scalping
        
        Returns:
            {
                'signal': 'BUY' | 'SELL' | 'NONE',
                'confidence': float,
                'entry_type': 'MARKET' | 'LIMIT',
                'reason': str,
                'velocity': float,
                'rejections': int,
                'absorption': bool
            }
        """
        if not rates_m1 or len(rates_m1) < 10:
            return self._no_signal("Datos M1 insuficientes")
        
        # 1. Analizar velocidad del precio
        velocity, velocity_direction = self._analyze_velocity(rates_m1)
        
        # 2. Detectar rechazos en niveles
        rejections, rejection_level, rejection_direction = self._detect_rejections(rates_m1)
        
        # 3. Detectar absorción
        absorption, absorption_direction = self._detect_absorption(rates_m1)
        
        # 4. Detectar velas de intención
        intention, intention_direction = self._detect_intention_candle(rates_m1)
        
        # 5. Analizar micro-impulsos
        impulse, impulse_direction = self._detect_micro_impulse(rates_m1)
        
        # Lógica de decisión
        signal = "NONE"
        confidence = 0.0
        entry_type = "MARKET"
        reasons = []
        
        # Señal por velocidad + impulso (entrada agresiva)
        if velocity > self.min_velocity_threshold and impulse:
            if velocity_direction == impulse_direction:
                signal = impulse_direction
                confidence = min(0.9, velocity / self.min_velocity_threshold * 0.3 + 0.5)
                entry_type = "MARKET"
                reasons.append(f"Velocidad alta + Impulso {impulse_direction}")
        
        # Señal por rechazos + absorción (entrada en nivel)
        if rejections >= self.rejection_count_threshold and absorption:
            if rejection_direction == absorption_direction:
                signal = rejection_direction
                confidence = max(confidence, 0.75)
                entry_type = "LIMIT"
                reasons.append(f"{rejections} rechazos + absorción en {rejection_level:.5f}")
        
        # Señal por vela de intención (confirmación)
        if intention and signal != "NONE":
            if intention_direction == signal:
                confidence = min(1.0, confidence + 0.15)
                reasons.append("Vela de intención confirma")
            else:
                confidence *= 0.5  # Contradice
                reasons.append("Vela de intención contradice")
        
        # Si hay intención fuerte sin otras señales
        if intention and signal == "NONE" and velocity > self.min_velocity_threshold * 0.5:
            signal = intention_direction
            confidence = 0.6
            entry_type = "MARKET"
            reasons.append(f"Vela de intención {intention_direction}")
        
        result = {
            'signal': signal,
            'confidence': round(confidence, 2),
            'entry_type': entry_type,
            'reason': " | ".join(reasons) if reasons else "Sin señal clara",
            'velocity': velocity,
            'velocity_direction': velocity_direction,
            'rejections': rejections,
            'rejection_level': rejection_level,
            'absorption': absorption,
            'impulse': impulse
        }
        
        if signal != "NONE":
            logger.info(f"[MicrostructureAgent] Señal: {signal} | Conf: {confidence:.0%} | {result['reason']}")
        
        return result
    
    def _no_signal(self, reason: str) -> Dict[str, Any]:
        return {
            'signal': 'NONE',
            'confidence': 0.0,
            'entry_type': 'MARKET',
            'reason': reason,
            'velocity': 0.0,
            'rejections': 0,
            'absorption': False
        }
    
    def _analyze_velocity(self, rates: list) -> tuple:
        """Analiza velocidad del precio (delta por vela)"""
        if len(rates) < 5:
            return 0.0, "NONE"
        
        # Últimas 5 velas
        recent = rates[-5:]
        deltas = [r['close'] - r['open'] for r in recent]
        
        # Velocidad = promedio de movimiento absoluto
        velocity = np.mean([abs(d) for d in deltas])
        
        # Dirección = suma de deltas
        direction_sum = sum(deltas)
        direction = "BUY" if direction_sum > 0 else "SELL"
        
        return velocity, direction
    
    def _detect_rejections(self, rates: list) -> tuple:
        """Detecta rechazos repetidos en un nivel"""
        if len(rates) < 10:
            return 0, 0.0, "NONE"
        
        recent = rates[-10:]
        highs = [r['high'] for r in recent]
        lows = [r['low'] for r in recent]
        
        # Buscar nivel de resistencia (rechazos de máximos)
        max_high = max(highs)
        resistance_rejections = sum(1 for h in highs if abs(h - max_high) < 0.0003)
        
        # Buscar nivel de soporte (rechazos de mínimos)
        min_low = min(lows)
        support_rejections = sum(1 for l in lows if abs(l - min_low) < 0.0003)
        
        if resistance_rejections >= support_rejections:
            return resistance_rejections, max_high, "SELL"  # Rechaza arriba = SELL
        else:
            return support_rejections, min_low, "BUY"  # Rechaza abajo = BUY
    
    def _detect_absorption(self, rates: list) -> tuple:
        """Detecta absorción (volumen alto sin movimiento)"""
        if len(rates) < 5:
            return False, "NONE"
        
        recent = rates[-5:]
        
        # Absorción = velas con mechas largas pero cuerpos pequeños
        absorptions = 0
        direction_hints = []
        
        for r in recent:
            body = abs(r['close'] - r['open'])
            total_range = r['high'] - r['low']
            
            if total_range > 0:
                body_ratio = body / total_range
                
                # Absorción: cuerpo pequeño, rango grande
                if body_ratio < 0.3 and total_range > 0.0002:
                    absorptions += 1
                    
                    # Determinar dirección por posición del cuerpo
                    upper_wick = r['high'] - max(r['open'], r['close'])
                    lower_wick = min(r['open'], r['close']) - r['low']
                    
                    if upper_wick > lower_wick:
                        direction_hints.append("SELL")  # Rechazo arriba
                    else:
                        direction_hints.append("BUY")  # Rechazo abajo
        
        if absorptions >= 2:
            direction = max(set(direction_hints), key=direction_hints.count) if direction_hints else "NONE"
            return True, direction
        
        return False, "NONE"
    
    def _detect_intention_candle(self, rates: list) -> tuple:
        """Detecta velas de intención (cuerpo > 70% del rango)"""
        if len(rates) < 3:
            return False, "NONE"
        
        last = rates[-1]
        
        body = abs(last['close'] - last['open'])
        total_range = last['high'] - last['low']
        
        if total_range > 0:
            body_ratio = body / total_range
            
            if body_ratio >= self.intention_body_ratio:
                direction = "BUY" if last['close'] > last['open'] else "SELL"
                return True, direction
        
        return False, "NONE"
    
    def _detect_micro_impulse(self, rates: list) -> tuple:
        """Detecta micro-impulso (3+ velas consecutivas en misma dirección)"""
        if len(rates) < 5:
            return False, "NONE"
        
        recent = rates[-5:]
        directions = []
        
        for r in recent:
            if r['close'] > r['open']:
                directions.append("BUY")
            elif r['close'] < r['open']:
                directions.append("SELL")
            else:
                directions.append("NONE")
        
        # Contar consecutivas
        buy_consecutive = 0
        sell_consecutive = 0
        
        for d in reversed(directions):
            if d == "BUY":
                buy_consecutive += 1
                if d != "BUY":
                    break
            elif d == "SELL":
                sell_consecutive += 1
                if d != "SELL":
                    break
            else:
                break
        
        if buy_consecutive >= 3:
            return True, "BUY"
        elif sell_consecutive >= 3:
            return True, "SELL"
        
        return False, "NONE"
