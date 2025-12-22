"""
Scalp Execution Agent - Capa 4 del Sistema de Scalping
Ejecución quirúrgica - Solo sabe ejecutar, no pensar
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger
import threading
import time


class ScalpExecutionAgent:
    """
    Agente de Ejecución Quirúrgico
    
    Este agente SOLO sabe ejecutar, no pensar.
    
    Entrada:
    - Market si hay velocidad
    - Limit si hay absorción clara
    
    Stop:
    - Fijo y muy corto (1-3 pips/ticks)
    
    TP:
    - Parcial rápido
    - Runner protegido a BE+1
    
    Tiempo máximo en mercado: 30-120 segundos
    """
    
    def __init__(self, order_agent, mt5_connector, config: dict = None):
        self.order_agent = order_agent
        self.mt5 = mt5_connector
        self.config = config or {}
        
        # Parámetros de scalping
        self.stop_loss_pips = self.config.get('stop_loss_pips', 3)
        self.take_profit_pips = self.config.get('take_profit_pips', 6)
        self.volume = self.config.get('volume', 0.01)
        self.max_trade_duration = self.config.get('max_trade_duration_seconds', 120)
        
        # Control de trades activos
        self.active_scalp_trades = {}  # ticket -> {open_time, entry_price, direction}
        self._monitor_thread = None
        self._stop_monitoring = threading.Event()
        
    def execute(self, 
                symbol: str, 
                direction: str, 
                entry_type: str,
                confidence: float) -> Dict[str, Any]:
        """
        Ejecuta una orden de scalping
        
        Args:
            symbol: Par de divisas
            direction: 'BUY' o 'SELL'
            entry_type: 'MARKET' o 'LIMIT'
            confidence: Confianza de la señal (0-1)
            
        Returns:
            {
                'success': bool,
                'ticket': int,
                'entry_price': float,
                'sl': float,
                'tp': float,
                'error': str
            }
        """
        try:
            # Identificar si es GOLD para ajustes especiales (Admirals)
            is_gold = "GOLD" in symbol.upper() or "XAUUSD" in symbol.upper()
            
            # Ajustar parámetros según confianza y símbolo
            adjusted_volume = self._adjust_volume(confidence)
            
            # Forzar volumen mínimo de 0.1 para GOLD en Admirals
            if is_gold and adjusted_volume < 0.1:
                adjusted_volume = 0.1
                
            adjusted_sl = self.stop_loss_pips
            adjusted_tp = self.take_profit_pips
            
            # Para GOLD en Admirals, los pips suelen ser x100 del point (1 pip = 1.00)
            # El connector usa x10 por defecto, así que multiplicamos por 10 aquí 
            # para que el connector aplique x100 en total.
            if is_gold:
                adjusted_sl *= 10
                adjusted_tp *= 10
            
            logger.info(f"[ScalpExecution] Ejecutando {direction} {symbol} | Vol:{adjusted_volume} SL:{adjusted_sl} TP:{adjusted_tp}")
            
            # Ejecutar orden
            if entry_type == "MARKET":
                result = self.order_agent.run({
                    "symbol": symbol,
                    "type": direction,
                    "volume": adjusted_volume,
                    "sl_pips": adjusted_sl,
                    "tp_pips": adjusted_tp,
                    "signal_id": None
                })
            else:
                # Para LIMIT, obtener precio actual y calcular precio de entrada
                current_price = self._get_current_price(symbol, direction)
                if current_price:
                    # Limit a 1 o 10 puntos según símbolo
                    offset_val = 0.1 if is_gold else 0.0001
                    offset = offset_val if direction == "BUY" else -offset_val
                    limit_price = current_price + offset
                    
                    result = self.order_agent.run({
                        "symbol": symbol,
                        "type": direction,
                        "volume": adjusted_volume,
                        "sl_pips": adjusted_sl,
                        "tp_pips": adjusted_tp,
                        "price": limit_price,
                        "signal_id": None
                    })
                else:
                    result = self.order_agent.run({
                        "symbol": symbol,
                        "type": direction,
                        "volume": adjusted_volume,
                        "sl_pips": adjusted_sl,
                        "tp_pips": adjusted_tp,
                        "signal_id": None
                    })
            
            if result.success:
                ticket = result.data.get('ticket', 0)
                entry_price = result.data.get('price', 0)
                
                # Registrar trade activo para monitoreo
                self.active_scalp_trades[ticket] = {
                    'open_time': datetime.now(),
                    'entry_price': entry_price,
                    'direction': direction,
                    'symbol': symbol,
                    'sl_pips': adjusted_sl,
                    'tp_pips': adjusted_tp
                }
                
                # Iniciar monitoreo si no está corriendo
                self._start_monitoring()
                
                logger.info(f"[ScalpExecution] ✅ Orden ejecutada #{ticket} @ {entry_price}")
                
                return {
                    'success': True,
                    'ticket': ticket,
                    'entry_price': entry_price,
                    'sl': result.data.get('sl', 0),
                    'tp': result.data.get('tp', 0),
                    'error': None
                }
            else:
                logger.error(f"[ScalpExecution] ❌ Error: {result.error}")
                return {
                    'success': False,
                    'ticket': None,
                    'entry_price': None,
                    'error': result.error
                }
                
        except Exception as e:
            logger.error(f"[ScalpExecution] Excepción: {e}")
            return {
                'success': False,
                'ticket': None,
                'entry_price': None,
                'error': str(e)
            }
    
    def _adjust_volume(self, confidence: float) -> float:
        """Ajusta volumen según confianza"""
        base_volume = self.volume
        
        if confidence >= 0.9:
            return base_volume * 1.5
        elif confidence >= 0.75:
            return base_volume
        else:
            return base_volume * 0.5
    
    def _get_current_price(self, symbol: str, direction: str) -> Optional[float]:
        """Obtiene precio actual"""
        try:
            tick = self.mt5.get_tick(symbol)
            if tick:
                return tick.ask if direction == "BUY" else tick.bid
        except:
            pass
        return None
    
    def _start_monitoring(self):
        """Inicia thread de monitoreo de trades"""
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            self._stop_monitoring.clear()
            self._monitor_thread = threading.Thread(target=self._monitor_trades, daemon=True)
            self._monitor_thread.start()
    
    def _monitor_trades(self):
        """Monitorea trades activos y cierra por tiempo"""
        while not self._stop_monitoring.is_set():
            try:
                now = datetime.now()
                tickets_to_remove = []
                
                for ticket, trade_info in list(self.active_scalp_trades.items()):
                    elapsed = (now - trade_info['open_time']).total_seconds()
                    
                    # Cerrar si excede tiempo máximo
                    if elapsed >= self.max_trade_duration:
                        logger.warning(f"[ScalpExecution] ⏱️ Tiempo máximo alcanzado para #{ticket}")
                        self._close_trade(ticket, "TIMEOUT")
                        tickets_to_remove.append(ticket)
                    
                    # Verificar BE+1 cuando esté en profit
                    elif elapsed >= 30:  # Después de 30 segundos
                        self._check_breakeven(ticket, trade_info)
                
                for ticket in tickets_to_remove:
                    del self.active_scalp_trades[ticket]
                
                # Si no hay trades activos, detener monitoreo
                if not self.active_scalp_trades:
                    break
                    
            except Exception as e:
                logger.error(f"[ScalpExecution] Error en monitoreo: {e}")
            
            time.sleep(5)  # Revisar cada 5 segundos
    
    def _close_trade(self, ticket: int, reason: str):
        """Cierra un trade"""
        try:
            result = self.order_agent.close_position(ticket)
            if result:
                logger.info(f"[ScalpExecution] Trade #{ticket} cerrado - {reason}")
            else:
                logger.error(f"[ScalpExecution] Error cerrando #{ticket}")
        except Exception as e:
            logger.error(f"[ScalpExecution] Error cerrando trade: {e}")
    
    def _check_breakeven(self, ticket: int, trade_info: dict):
        """Mueve SL a BE+1 cuando hay profit suficiente"""
        try:
            positions = self.order_agent.get_open_positions()
            for pos in positions:
                if pos.get('ticket') == ticket:
                    profit_pips = pos.get('profit', 0) / (self.volume * 10)  # Aproximado
                    
                    # Si tiene más de 2 pips de profit, mover a BE+1
                    if profit_pips >= 2:
                        entry = trade_info['entry_price']
                        direction = trade_info['direction']
                        
                        if direction == "BUY":
                            new_sl = entry + 0.0001  # BE + 1 pip
                        else:
                            new_sl = entry - 0.0001
                        
                        current_sl = pos.get('sl', 0)
                        
                        # Solo mover si mejora
                        if (direction == "BUY" and new_sl > current_sl) or \
                           (direction == "SELL" and (current_sl == 0 or new_sl < current_sl)):
                            self.order_agent.modify_position(ticket, new_sl, pos.get('tp'))
                            logger.info(f"[ScalpExecution] 🔒 BE+1 aplicado a #{ticket}")
                    break
        except Exception as e:
            logger.debug(f"Error en BE check: {e}")
    
    def stop(self):
        """Detiene el agente"""
        self._stop_monitoring.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
