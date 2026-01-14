
"""
Snake Agent - Temporal Outcome Control Loop
"""

from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger
from .swing_detector import SwingDetector
import math

class SnakeAction(Enum):
    HOLD = "HOLD"         # Mantener operación (hipótesis válida)
    CLOSE = "CLOSE"       # Cerrar inmediatamente (tiempo agotado o hipótesis fallida)
    PROTECT = "PROTECT"   # Mover a Break-Even o asegurar ganancia
    ADD = "ADD"           # Reforzar posición (momentum confirmado)
    RELEASE = "RELEASE"   # Soltar control (tiempo agotado en profit, devolver al usuario)

class SnakeStatus(Enum):
    VALID = "VALID"       # El precio se mueve a favor con velocidad adecuada
    WEAK = "WEAK"         # El precio duda o no avanza lo suficiente
    FAIL = "FAIL"         # El precio va en contra o estructura rota

class SnakeAgent:
    """
    Agente especialista en "Temporal Outcome Control Loop".
    No predice el futuro lejano.
    Gestiona una orden viva dentro de una ventana temporal estricta.
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.swing_detector = SwingDetector(lookback=self.config.get('swing_lookback', 50))
        self.zone_threshold_pct = self.config.get('zone_threshold_pct', 0.05)

    def evaluate(self, session: Any, ticket_info: Dict[str, Any], market_data: Dict[str, Any] = None, rates_m1: list = None) -> Dict[str, Any]:
        """
        Evalúa el estado de una sesión activa (Hypothesis Validation Logic).
        Ahora incluye análisis PPM (Price Proportional Movement).
        """
        
        # 1. Datos temporales
        now = datetime.now()
        start_time = session.start_time
        planned_end = session.end_time_planned
        total_duration = session.duration_seconds
        
        elapsed_seconds = (now - start_time).total_seconds()
        remaining_seconds = (planned_end - now).total_seconds()
        
        # Progreso temporal (0.0 a 1.0)
        time_progress = min(max(elapsed_seconds / total_duration, 0), 1)
        
        # 2. Datos de precio
        entry_price = session.entry_price
        current_price = ticket_info.get('current_price', entry_price)
        current_profit = ticket_info.get('profit', 0.0)
        
        # Dirección del trade
        is_buy = ticket_info.get('type') == 0 or ticket_info.get('type') == 'BUY'
        
        # Pips ganados/perdidos (estimación cruda si no tenemos point)
        diff = current_price - entry_price
        if not is_buy: diff = -diff
        
        # 3. Lógica de "Snake" (Time-Box Validation)
        
        # A. Chequeo de expiración
        if remaining_seconds <= 0:
            return self._decide_on_expiry(current_profit, diff)

        # B. Chequeo de "Muerte Súbita" (Hypothesis Invalidated)
        # Si en el primer 30% del tiempo ya perdemos significativamente -> Hipótesis nula
        if time_progress < 0.3 and current_profit < -5.0: 
             return {
                "action": SnakeAction.CLOSE,
                "status": SnakeStatus.FAIL,
                "reason": "Hypothesis Invalidated: Early Drawdown",
                "confidence": 1.0
            }

        # C. Momentum & Velocity Hypothesis
        velocity = diff / (elapsed_seconds + 0.1) # pips/sec (aprox)
        
        # D. Matriz de Decisión
        status = SnakeStatus.WEAK
        action = SnakeAction.HOLD
        confidence = 0.5
        reason = "Monitoring Hypothesis"
        
        if diff > 0:
            # EN PROFIT
            status = SnakeStatus.VALID
            confidence = 0.7 + (0.1 * velocity)
            
            # --- Regla de "Expectation First" ---
            # Si pasamos el 50% del tiempo y la velocidad es anémica -> Proteger
            if time_progress > 0.5 and velocity < 0.01 and current_profit > 2.0:
                 action = SnakeAction.PROTECT
                 reason = "Low Velocity - Securing Profit"
            
            # Si pasamos el 80% y estamos en profit -> RELEASE (Take the money? No, let it run)
            # CHANGE: If huge profit, maybe protect, but stick to plan of RELEASE on expiry.
            # But earlier logic said "Time-Box Limit: Securing Win". 
            # If we want to restart, we should just let it reach expiry OR Release here.
            # Let's keep existing logic but change CLOSE to RELEASE if it was "Securing Win" 
            # UNLESS the user explicitly wants Scalping behavior (Hit and Run).
            # The user asked: "Snake Agent deveria reiniciarse al acabar el ciclo".
            # So waiting for expiry is best.
            
            # 4. 🧠 PPM VISION: Probabilistic Exit Management
            # -----------------------------------------------
            if rates_m1:
                ppm_context = self.swing_detector.detect_last_swing(rates_m1)
                if ppm_context:
                    ppm_zone = self._detect_ppm_zone(current_price, ppm_context)
                    if ppm_zone:
                        # Analizar comportamiento en zona
                        # Usamos velocidad para decidir aceptación/rechazo
                        current_velocity = velocity
                        
                        if ppm_zone == "0.5R":
                            if current_velocity < 0.01: # Velocidad baja en 0.5R
                                return {
                                    "action": SnakeAction.PROTECT,
                                    "status": SnakeStatus.WEAK,
                                    "reason": "🧠 PPM 0.5R: Momentum Weakening (Protecting Partial)",
                                    "confidence": 0.85
                                }
                        elif ppm_zone == "1.0R":
                            if current_velocity < 0.02: # Reacción probable en igualdad
                                return {
                                    "action": SnakeAction.CLOSE,
                                    "status": SnakeStatus.VALID,
                                    "reason": "🧠 PPM 1.0R: Equality zone reached (Probabilistic Closure)",
                                    "confidence": 0.95
                                }
                            else:
                                reason = "🧠 PPM 1.0R: Expansion persistence (Trailing to 2.0R)"
                        elif ppm_zone == "2.0R":
                             return {
                                "action": SnakeAction.CLOSE,
                                "status": SnakeStatus.VALID,
                                "reason": "🧠 PPM 2.0R: Expansion limit reached (Full Exit)",
                                "confidence": 1.0
                            }

            if time_progress > 0.8:
                # Instead of closing, we just wait for expiry to RELEASE.
                # Or we can RELEASE early if it's very good.
                action = SnakeAction.HOLD # Let it reach expiry for RELEASE
                reason = "Time-Box Limit: Holding for Release"
                
            elif time_progress > 0.4 and current_profit > 10.0:
                 action = SnakeAction.PROTECT
                 reason = "Protecting Breakout"
            else:
                action = SnakeAction.HOLD
                reason = "Hypothesis Valid: Letting Run"

        else:
            # EN PÉRDIDA
            status = SnakeStatus.FAIL
            
            # --- Regla de "Hypothesis Check" ---
            # Si hemos pasado el 50% del tiempo y seguimos en negativo -> LA HIPÓTESIS FALLÓ.
            # No esperamos al SL. Cerramos ya.
            if time_progress > 0.5:
                action = SnakeAction.CLOSE
                reason = "Hypothesis Failed: No recovery by mid-time"
                confidence = 0.9
            
            # Si es el principio (<50%), damos margen si no es caída libre
            elif time_progress < 0.5:
                 action = SnakeAction.HOLD
                 reason = "Giving room for thesis"
                 status = SnakeStatus.WEAK
            else:
                 action = SnakeAction.CLOSE
                 reason = "Validation Failed"

        return {
            "action": action,
            "status": status,
            "reason": reason,
            "confidence": min(confidence, 1.0),
            "stats": {
                "velocity": velocity,
                "remaining": remaining_seconds,
                 "profit": current_profit
            }
        }

    def _detect_ppm_zone(self, price: float, ppm_context: Dict) -> Optional[str]:
        """Detecta si el precio está en una zona de decisión proporcional"""
        levels = ppm_context.get('levels', {})
        r_range = ppm_context.get('R', 0)
        threshold = r_range * self.zone_threshold_pct
        
        for name, level in levels.items():
            if abs(price - level) <= threshold:
                return name
        return None

    def _decide_on_expiry(self, current_profit: float, pips_diff: float) -> Dict[str, Any]:
        """Decisión cuando el tiempo se ha agotado"""
        if current_profit > 0:
            # CHANGE: Instead of CLOSE, we RELEASE functionality to user logic (or re-snake)
            return {
                "action": SnakeAction.RELEASE,
                "status": SnakeStatus.VALID,
                "reason": "Time expired (Profit) -> Released",
                "confidence": 1.0
            }
        else:
             # If loss, we stick to hypothesis failure -> CLOSE
             return {
                "action": SnakeAction.CLOSE,
                "status": SnakeStatus.FAIL,
                "reason": "Time expired (Loss)",
                "confidence": 1.0
            }
