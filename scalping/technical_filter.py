"""
Technical Filter - Capa 3 del Sistema de Scalping
Confirma, nunca decide - Solo como filtro
"""

from typing import Dict, Any
from loguru import logger
import numpy as np


class TechnicalFilter:
    """
    Filtro Técnico (Confirmador, NO decisor)
    
    Indicadores solo como filtros, nunca como gatillo:
    - VWAP / VWAP bandas
    - EMA 20 / EMA 50 (pendiente, no cruce)
    - RSI solo para divergencia micro, no sobrecompra
    
    Si el técnico contradice al micro → NO SE ENTRA
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.ema_short_period = 20
        self.ema_long_period = 50
        self.rsi_period = 14
        
    def confirm(self, signal: str, rates: list) -> Dict[str, Any]:
        """
        Confirma o rechaza una señal del MicrostructureAgent
        
        Args:
            signal: 'BUY' o 'SELL' del agente de microestructura
            rates: Lista de velas (al menos 50)
            
        Returns:
            {
                'confirms': bool,
                'reason': str,
                'filters': dict con detalles
            }
        """
        if not rates or len(rates) < self.ema_long_period:
            return {
                'confirms': False,
                'reason': 'Datos insuficientes para análisis técnico',
                'filters': {}
            }
        
        closes = [r['close'] for r in rates]
        highs = [r['high'] for r in rates]
        lows = [r['low'] for r in rates]
        
        # 1. Calcular VWAP y posición del precio
        vwap, vwap_upper, vwap_lower = self._calculate_vwap(rates)
        current_price = closes[-1]
        vwap_position = self._get_vwap_position(current_price, vwap, vwap_upper, vwap_lower)
        
        # 2. Calcular EMAs y sus pendientes
        ema_short = self._ema(closes, self.ema_short_period)
        ema_long = self._ema(closes, self.ema_long_period)
        ema_short_slope = self._calculate_slope(ema_short[-5:])
        ema_long_slope = self._calculate_slope(ema_long[-5:])
        
        # 3. Calcular RSI y buscar divergencias
        rsi = self._calculate_rsi(closes, self.rsi_period)
        rsi_divergence = self._detect_divergence(closes[-10:], rsi[-10:] if len(rsi) >= 10 else rsi)
        
        # Evaluación
        confirmations = 0
        rejections = 0
        reasons = []
        
        if signal == "BUY":
            # BUY confirmado si:
            # - Precio cerca o debajo de VWAP
            # - EMAs con pendiente positiva o plana
            # - RSI no en sobreventa extrema sin divergencia
            
            if vwap_position in ["below", "at_vwap", "lower_band"]:
                confirmations += 1
                reasons.append("Precio en zona de valor (VWAP)")
            else:
                rejections += 1
                reasons.append("Precio muy por encima de VWAP")
            
            if ema_short_slope > -0.00001:  # Pendiente no muy negativa
                confirmations += 1
                reasons.append(f"EMA20 pendiente OK ({ema_short_slope:.6f})")
            else:
                rejections += 1
                reasons.append(f"EMA20 pendiente negativa")
            
            if rsi_divergence == "bullish" or (rsi[-1] > 30 if rsi else True):
                confirmations += 1
                if rsi_divergence == "bullish":
                    reasons.append("Divergencia alcista en RSI")
            else:
                rejections += 1
                reasons.append("RSI sin soporte")
                
        elif signal == "SELL":
            # SELL confirmado si:
            # - Precio cerca o encima de VWAP
            # - EMAs con pendiente negativa o plana
            # - RSI no en sobrecompra extrema sin divergencia
            
            if vwap_position in ["above", "at_vwap", "upper_band"]:
                confirmations += 1
                reasons.append("Precio en zona de sobrevaloración (VWAP)")
            else:
                rejections += 1
                reasons.append("Precio muy por debajo de VWAP")
            
            if ema_short_slope < 0.00001:  # Pendiente no muy positiva
                confirmations += 1
                reasons.append(f"EMA20 pendiente OK ({ema_short_slope:.6f})")
            else:
                rejections += 1
                reasons.append(f"EMA20 pendiente positiva")
            
            if rsi_divergence == "bearish" or (rsi[-1] < 70 if rsi else True):
                confirmations += 1
                if rsi_divergence == "bearish":
                    reasons.append("Divergencia bajista en RSI")
            else:
                rejections += 1
                reasons.append("RSI sin resistencia")
        
        # Decisión final
        confirms = confirmations >= 2 and rejections < 2
        
        result = {
            'confirms': confirms,
            'reason': " | ".join(reasons),
            'filters': {
                'vwap': vwap,
                'vwap_position': vwap_position,
                'ema_short': ema_short[-1] if ema_short else 0,
                'ema_long': ema_long[-1] if ema_long else 0,
                'ema_short_slope': ema_short_slope,
                'ema_long_slope': ema_long_slope,
                'rsi': rsi[-1] if rsi else 50,
                'rsi_divergence': rsi_divergence,
                'confirmations': confirmations,
                'rejections': rejections
            }
        }
        
        log_level = "info" if confirms else "debug"
        getattr(logger, log_level)(f"[TechnicalFilter] {signal}: {'✓ CONFIRMA' if confirms else '✗ RECHAZA'} | {result['reason']}")
        
        return result
    
    def _calculate_vwap(self, rates: list) -> tuple:
        """Calcula VWAP y bandas"""
        if not rates:
            return 0, 0, 0
        
        # VWAP simplificado (sin volumen real, usa rango como proxy)
        typical_prices = []
        volumes = []
        
        for r in rates:
            tp = (r['high'] + r['low'] + r['close']) / 3
            vol = r['high'] - r['low']  # Proxy de volumen
            typical_prices.append(tp)
            volumes.append(vol)
        
        total_vol = sum(volumes)
        if total_vol == 0:
            vwap = typical_prices[-1]
        else:
            vwap = sum(tp * v for tp, v in zip(typical_prices, volumes)) / total_vol
        
        # Bandas (1 desviación estándar)
        std = np.std(typical_prices)
        vwap_upper = vwap + std
        vwap_lower = vwap - std
        
        return vwap, vwap_upper, vwap_lower
    
    def _get_vwap_position(self, price: float, vwap: float, upper: float, lower: float) -> str:
        """Determina posición del precio respecto a VWAP"""
        if price > upper:
            return "above"
        elif price < lower:
            return "below"
        elif price > vwap + (upper - vwap) * 0.5:
            return "upper_band"
        elif price < vwap - (vwap - lower) * 0.5:
            return "lower_band"
        else:
            return "at_vwap"
    
    def _ema(self, data: list, period: int) -> list:
        """Calcula EMA"""
        if not data or len(data) < period:
            return []
        
        multiplier = 2 / (period + 1)
        ema = [sum(data[:period]) / period]  # SMA inicial
        
        for price in data[period:]:
            ema.append((price - ema[-1]) * multiplier + ema[-1])
        
        return ema
    
    def _calculate_slope(self, values: list) -> float:
        """Calcula pendiente de una serie"""
        if not values or len(values) < 2:
            return 0.0
        
        x = np.arange(len(values))
        slope = np.polyfit(x, values, 1)[0]
        return slope
    
    def _calculate_rsi(self, closes: list, period: int = 14) -> list:
        """Calcula RSI"""
        if len(closes) < period + 1:
            return []
        
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        rsi = []
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            
            if avg_loss == 0:
                rsi.append(100)
            else:
                rs = avg_gain / avg_loss
                rsi.append(100 - (100 / (1 + rs)))
        
        return rsi
    
    def _detect_divergence(self, prices: list, rsi: list) -> str:
        """Detecta divergencias entre precio y RSI"""
        if len(prices) < 5 or len(rsi) < 5:
            return "none"
        
        price_slope = self._calculate_slope(prices[-5:])
        rsi_slope = self._calculate_slope(rsi[-5:])
        
        # Divergencia alcista: precio baja, RSI sube
        if price_slope < -0.00001 and rsi_slope > 0.5:
            return "bullish"
        
        # Divergencia bajista: precio sube, RSI baja
        if price_slope > 0.00001 and rsi_slope < -0.5:
            return "bearish"
        
        return "none"
