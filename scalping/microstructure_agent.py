"""
Microstructure Agent - Capa 2 del Sistema de Scalping
El que manda - Observa precio en M1/M5, no indicadores
"""

from typing import Dict, Any, List
from loguru import logger
from .swing_detector import SwingDetector
import numpy as np
import pandas as pd


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
        
        # PPM Vision
        self.ppm_enabled = self.config.get('ppm_enabled', True)
        self.swing_detector = SwingDetector(lookback=self.config.get('swing_lookback', 50))
        self.zone_threshold_pct = self.config.get('zone_threshold_pct', 0.05)
        
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
        
        # 6. 💿 ESTRATEGIA CARGADA: Arafura Scalper (MQL5 Logic)
        # Se ejecuta en paralelo y tiene prioridad si detecta señal
        arafura_signal = self._analyze_arafura_strategy(rates_m1)
        
        # 7. 🧠 PPM VISION: Proportional Movement Analysis
        ppm_context = {}
        if self.ppm_enabled:
            ppm_context = self.swing_detector.detect_last_swing(rates_m1)
            if ppm_context:
                current_price = rates_m1[-1]['close']
                ppm_zone = self._detect_ppm_zone(current_price, ppm_context)
                if ppm_zone:
                    logger.info(f"👀 [PPM] High-Intensity Observation: Price at {ppm_zone} zone")
                    ppm_signal = self._analyze_ppm_behavior(rates_m1, ppm_zone, ppm_context)
                    if ppm_signal['signal'] != 'NONE':
                        return ppm_signal
        
        # Lógica de decisión
        signal = "NONE"
        confidence = 0.0
        entry_type = "MARKET"
        reasons = []
        
        # Prioridad 1: Estrategia Arafura (El "Diskette")
        if arafura_signal['signal'] != 'NONE':
            signal = arafura_signal['signal']
            confidence = arafura_signal['confidence']
            entry_type = "MARKET" # MQL5 logic uses Market execution mostly
            reasons.append(f"💿 Arafura: {arafura_signal['reason']}")
            
            return {
                'signal': signal,
                'confidence': confidence,
                'entry_type': entry_type,
                'reason': " | ".join(reasons),
                'velocity': velocity,
                'rejections': rejections,
                'absorption': absorption
            }
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

    # ════════════════════════════════════════════════════════════════
    # 💿 MÓDULO ESTRATEGIA CARGADA: Arafura Scalper
    # ════════════════════════════════════════════════════════════════
    def _analyze_arafura_strategy(self, rates_m1: list) -> Dict[str, Any]:
        """Implementación de la lógica del script MQL5"""
        if len(rates_m1) < 60: # Necesitamos 50 para EMA lenta + buffer
            return {'signal': 'NONE', 'confidence': 0, 'reason': ''}
            
        try:
            df = pd.DataFrame(rates_m1)
            
            # Parámetros (del input del EA)
            ema_fast_p = 20
            ema_slow_p = 50
            atr_p = 14
            impulse_atr_mult = 1.20
            breakout_lookback = 20
            breakout_buffer_pts = 0.0006 # 6 points aprox (ajustado para FX 5 digitos)
            pullback_ema_tol = 0.0010    # 10 points
            pinbar_wick_ratio = 1.6
            
            # Cálculo de indicadores
            df['ema_fast'] = df['close'].ewm(span=ema_fast_p, adjust=False).mean()
            df['ema_slow'] = df['close'].ewm(span=ema_slow_p, adjust=False).mean()
            
            # ATR manual
            df['tr0'] = abs(df['high'] - df['low'])
            df['tr1'] = abs(df['high'] - df['close'].shift(1))
            df['tr2'] = abs(df['low'] - df['close'].shift(1))
            df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
            df['atr'] = df['tr'].rolling(window=atr_p).mean()
            
            # Última vela cerrada (shift=1 en MT5 es iloc[-2] aquí)
            # iloc[-1] es la vela actual en formación
            if len(df) < 2: return {'signal': 'NONE'}
            
            curr = df.iloc[-1]   # Vela actual (no usada para señal confirmada)
            c1 = df.iloc[-2]     # Vela cerrada (shift 1)
            c2 = df.iloc[-3]     # Shift 2
            
            # Tendencia
            trend_bull = c1['ema_fast'] > c1['ema_slow']
            trend_bear = c1['ema_fast'] < c1['ema_slow']
            
            # 1. TRIGGER: IMPULSE BREAKOUT
            # ---------------------------
            atr_val = c1['atr']
            range_val = c1['high'] - c1['low']
            
            is_impulse = range_val >= (atr_val * impulse_atr_mult)
            
            if is_impulse:
                # Bullish Breakout
                if trend_bull:
                    # Close near high (upper 25%)
                    if (c1['high'] - c1['close']) <= (range_val * 0.25):
                        # Breakout check: High > Highest of last 20 (excluding c1)
                        # window [-22:-2] -> 20 barras antes de c1
                        hist_highs = df['high'].iloc[-22:-2] 
                        if not hist_highs.empty:
                            level = hist_highs.max()
                            if (c1['high'] - level) >= breakout_buffer_pts:
                                return {
                                    'signal': 'BUY',
                                    'confidence': 0.85,
                                    'reason': 'Impulse Breakout (Bull)'
                                }
                
                # Bearish Breakout
                if trend_bear:
                    # Close near low (lower 25%)
                    if (c1['close'] - c1['low']) <= (range_val * 0.25):
                        hist_lows = df['low'].iloc[-22:-2]
                        if not hist_lows.empty:
                            level = hist_lows.min()
                            if (level - c1['low']) >= breakout_buffer_pts:
                                return {
                                    'signal': 'SELL',
                                    'confidence': 0.85,
                                    'reason': 'Impulse Breakout (Bear)'
                                }

            # 2. TRIGGER: PULLBACK REJECTION
            # -----------------------------
            # Pullback to EMA Fast
            dist_to_ema = abs(c1['ema_fast'] - (c1['low'] if trend_bull else c1['high']))
            near_ema = dist_to_ema <= pullback_ema_tol
            
            if near_ema:
                body = abs(c1['close'] - c1['open'])
                total_range = c1['high'] - c1['low']
                
                if total_range > 0 and body > 0:
                    upper_wick = c1['high'] - max(c1['open'], c1['close'])
                    lower_wick = min(c1['open'], c1['close']) - c1['low']
                    
                    # Bull Pinbar
                    if trend_bull:
                        if (lower_wick / body) >= pinbar_wick_ratio and lower_wick > upper_wick:
                            return {
                                'signal': 'BUY',
                                'confidence': 0.75,
                                'reason': 'Pullback Rejection (Bull Pinbar)'
                            }
                    
                    # Bear Pinbar
                    if trend_bear:
                        if (upper_wick / body) >= pinbar_wick_ratio and upper_wick > lower_wick:
                            return {
                                'signal': 'SELL',
                                'confidence': 0.75,
                                'reason': 'Pullback Rejection (Bear Pinbar)'
                            }

        except Exception as e:
            logger.error(f"Error analizando estrategia Arafura: {e}")
            
        return {'signal': 'NONE', 'confidence': 0, 'reason': ''}

    def _detect_ppm_zone(self, price: float, ppm_context: Dict) -> Optional[str]:
        """Detecta si el precio está en una zona de decisión proporcional"""
        levels = ppm_context.get('levels', {})
        r_range = ppm_context.get('R', 0)
        threshold = r_range * self.zone_threshold_pct
        
        for name, level in levels.items():
            if abs(price - level) <= threshold:
                return name
        return None

    def _analyze_ppm_behavior(self, rates: list, zone: str, context: Dict) -> Dict[str, Any]:
        """Analiza el comportamiento micro en una zona PPM"""
        current_rates = rates[-5:]
        velocity, direction = self._analyze_velocity(current_rates)
        
        # Lógica simplificada de "Aceptación" vs "Rechazo"
        # Si el momentum es fuerte hacia el nivel, es continuación (Acceptance)
        # Si el momentum se debilita o hay mechas contrarias, es retroceso (Rejection)
        
        ppm_signal = "NONE"
        reason = ""
        
        if zone == "0.5R":
            # Si el precio llega a 0.5R y el momentum cae -> Retroceso
            if velocity < self.min_velocity_threshold:
                 # Retroceso probable
                 ppm_signal = "SELL" if context['direction'] == "BULLISH" else "BUY"
                 reason = "0.5R Zone: Momentum weakening (Retracement Scenario)"
            else:
                 reason = "0.5R Zone: Momentum holds (Continuation to 1.0R)"
                 
        elif zone == "1.0R":
            # Equality Zone - High probability of reaction
            if velocity < self.min_velocity_threshold:
                ppm_signal = "SELL" if context['direction'] == "BULLISH" else "BUY"
                reason = "1.0R Zone: High probability reaction (Equality Zone rejection)"
            else:
                reason = "1.0R Zone: Clean acceptance (Expansion potential to 2.0R)"
                
        elif zone == "2.0R":
            # Expansion Zone - Mature move
            ppm_signal = "SELL" if context['direction'] == "BULLISH" else "BUY"
            reason = "2.0R Zone: Move statistically mature (Expansion Zone closure)"

        return {
            'signal': ppm_signal,
            'confidence': 0.80 if ppm_signal != "NONE" else 0.0,
            'entry_type': 'MARKET',
            'reason': f"🧠 PPM: {reason}",
            'ppm_zone': zone
        }
