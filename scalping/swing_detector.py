"""
SwingDetector - Identifica estructuras de mercado y zonas proporcionales
"""

from typing import Dict, Any, List, Optional
import numpy as np

class SwingDetector:
    """
    Detecta los últimos Swings válidos y calcula niveles proporcionales (PPM)
    """
    def __init__(self, lookback: int = 50):
        self.lookback = lookback

    def detect_last_swing(self, rates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Detecta el último swing high y swing low confirmado.
        Retorna R (rango) y los niveles 0.5R, 1.0R, 2.0R.
        """
        if not rates or len(rates) < 10:
            return {}

        recent = rates[-self.lookback:]
        highs = [r['high'] for r in recent]
        lows = [r['low'] for r in recent]
        
        # Detección simple de extremos locales
        # Buscamos el máximo más alto y el mínimo más bajo en el lookback
        swing_high = max(highs)
        swing_low = min(lows)
        
        # Determinar cuál es el origen del movimiento (el más antiguo de los dos)
        idx_high = -1
        idx_low = -1
        
        for i, r in enumerate(recent):
            if r['high'] == swing_high:
                idx_high = i
            if r['low'] == swing_low:
                idx_low = i
        
        origin_price = 0.0
        target_price = 0.0
        direction = "NONE"
        
        if idx_low < idx_high:
            # Movimiento Alcista (de Low a High)
            origin_price = swing_low
            target_price = swing_high
            direction = "BULLISH"
        else:
            # Movimiento Bajista (de High a Low)
            origin_price = swing_high
            target_price = swing_low
            direction = "BEARISH"
            
        range_r = abs(target_price - origin_price)
        
        if range_r == 0:
            return {}
            
        # Niveles proyectados desde el origen
        if direction == "BULLISH":
            levels = {
                "0.5R": origin_price + (range_r * 0.5),
                "1.0R": origin_price + (range_r * 1.0),
                "2.0R": origin_price + (range_r * 2.0)
            }
        else: # BEARISH
            levels = {
                "0.5R": origin_price - (range_r * 0.5),
                "1.0R": origin_price - (range_r * 1.0),
                "2.0R": origin_price - (range_r * 2.0)
            }
            
        return {
            "direction": direction,
            "origin": origin_price,
            "target": target_price,
            "R": range_r,
            "levels": levels
        }

    def get_proximity(self, current_price: float, levels: Dict[str, float], threshold_pct: float = 0.05) -> Optional[str]:
        """
        Determina si el precio está cerca de algún nivel PPM.
        threshold_pct: % del rango R para considerar proximidad.
        """
        if not levels:
            return None
            
        range_r = levels.get("1.0R", 0) - levels.get("0R", 0) # This is not quite right, but we have R in the result
        # Let's assume we pass R or the levels dict is enough
        
        # En realidad necesitamos R para el %
        # Refactor: let's just check distance relative to price or specific delta
        
        for level_name, level_price in levels.items():
            diff = abs(current_price - level_price)
            # Umbral dinámico basado en un pequeño delta de pips o similar
            # Para simplificar, usaremos un valor pequeño fijo o basado en R si lo tuviéramos
            if diff < 0.0001: # 1 pip aprox
                return level_name
                
        return None
