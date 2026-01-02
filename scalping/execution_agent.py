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
        self.risk_per_trade_percent = self.config.get('risk_per_trade_percent', 1.0)
        self.max_margin_percent_per_trade = self.config.get('max_margin_percent_per_trade', 15.0) # Máximo 15% de equity en margen
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
            # 1. Identificar símbolo y obtener tick actual para spread
            tick = self.mt5.get_tick(symbol)
            current_spread = (tick.ask - tick.bid) if tick else 0.0
            is_gold = "GOLD" in symbol.upper() or "XAUUSD" in symbol.upper()
            is_ger40 = "GER40" in symbol.upper() or "DE40" in symbol.upper()
            
            # 2. Ajustar volumen según confianza y margen
            adjusted_volume = self._adjust_volume(symbol, direction, confidence)
            
            # Forzar volumen mínimo de 0.1 para GOLD en Admirals
            if is_gold and adjusted_volume < 0.1:
                adjusted_volume = 0.1
                
            # 3. Cálculo de SL/TP dinámico por ATR
            # Intentar obtener ATR de la config si se pasó, si no usar default
            atr = self.config.get('last_atr', 0.0005) 
            
            # Factores K (vienen del bandit vía config del orchestrator)
            k_sl = self.config.get('current_k_sl', 1.5)
            k_tp = self.config.get('current_k_tp', 2.5)
            preset_name = self.config.get('current_preset', 'default')
            
            # Convertir ATR a pips/puntos (aproximado)
            # FX: 0.0001 = 1 pip
            # GER40: 0.1 = 1 point
            # GOLD: 0.1 = 1 point
            
            if is_gold or is_ger40:
                atr_points = atr * 10 # Si ATR es 0.5 -> 5 puntos
                # Mínimos absolutos (Expert suggestion)
                min_sl = 15.0 if is_ger40 else 2.0
                min_tp = 30.0 if is_ger40 else 5.0
                
                sl_points = max(atr_points * k_sl, min_sl)
                tp_points = max(atr_points * k_tp, min_tp)
                
                # Para GOLD en Admirals, el connector espera pips (que multiplica por 10 internamente para puntos)
                # Así que si queremos 20 puntos, pasamos 2.0 pips.
                adjusted_sl = sl_points / 10.0
                adjusted_tp = tp_points / 10.0
            else:
                # Forex estándar
                atr_pips = atr * 10000
                min_sl = 5.0
                min_tp = 10.0
                
                adjusted_sl = max(atr_pips * k_sl, min_sl)
                adjusted_tp = max(atr_pips * k_tp, min_tp)

            logger.info(f"[ScalpExecution] {symbol} | Vol:{adjusted_volume} SL:{adjusted_sl:.1f} TP:{adjusted_tp:.1f} (ATR: {atr:.6f})")
            
            # 4. Ejecutar orden
            comment = f"ARAFURA|{preset_name}"
            if entry_type == "MARKET":
                result = self.order_agent.run({
                    "symbol": symbol,
                    "type": direction,
                    "volume": adjusted_volume,
                    "sl_pips": adjusted_sl,
                    "tp_pips": adjusted_tp,
                    "comment": comment,
                    "signal_id": None
                })
            else:
                # Para LIMIT, obtener precio actual y calcular precio de entrada
                current_price = tick.ask if direction == "BUY" else tick.bid if tick else None
                if current_price:
                    # Limit a una distancia mínima razonable
                    offset_val = 1.0 if (is_gold or is_ger40) else 0.0002
                    offset = -offset_val if direction == "BUY" else offset_val # BUY LIMIT abajo, SELL LIMIT arriba
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
    
    def _adjust_volume(self, symbol: str, direction: str, confidence: float) -> float:
        """Ajusta volumen según riesgo (%), margen y confianza"""
        try:
            # 1. Obtener balance y equity
            account_info = self.mt5.get_account_info()
            if not account_info:
                return 0.01
                
            balance = account_info.get('balance', 1000)
            equity = account_info.get('equity', balance)
            
            # 2. Calcular monto a arriesgar financieramente ($)
            risk_amount = balance * (self.risk_per_trade_percent / 100)
            
            # 3. Calcular volumen teórico por Stop Loss
            risk_per_pip = risk_amount / max(1, self.stop_loss_pips)
            pip_value_std = 10.0 # Aproximado para majors
            calculated_volume = risk_per_pip / pip_value_std
            
            # 4. Ajustar por confianza
            if confidence >= 0.9: calculated_volume *= 1.2
            elif confidence < 0.5: calculated_volume *= 0.5
            
            # 5. --- CONTROL DE MARGEN ---
            max_margin_allowed = equity * (self.max_margin_percent_per_trade / 100)
            
            # Calcular margen requerido para el volumen propuesto
            required_margin = self.mt5.get_order_margin(symbol, direction, calculated_volume)
            
            if required_margin > max_margin_allowed and required_margin > 0:
                reduction_factor = max_margin_allowed / required_margin
                new_volume = calculated_volume * reduction_factor
                logger.warning(f"[ScalpMargin] Sugerida reducción por margen: {calculated_volume:.2f} -> {new_volume:.2f} (Req:{required_margin:.2f} | Max:{max_margin_allowed:.2f})")
                calculated_volume = new_volume

            # 6. --- RESPETAR MÍNIMOS DEL BROKER (Petición usuario) ---
            # Asegurar que no bajamos del mínimo permitido por el broker para este símbolo
            symbol_info = self.mt5.get_symbol_info(symbol)
            min_vol = symbol_info.volume_min if symbol_info else 0.01
            
            # El volumen final es el calculado, pero nunca menos que el mínimo del símbolo
            final_volume = max(min_vol, round(calculated_volume, 2))
            
            # Log para debug
            logger.debug(f"[ScalpVolume] {symbol}: Risk$: {risk_amount:.2f} | Margin Limit: {max_margin_allowed:.2f} | Min Vol: {min_vol} | Vol final: {final_volume}")
            
            return min(final_volume, 1.0) # Cap at 1.0 lot for safety
            
        except Exception as e:
            logger.error(f"Error calculando volumen dinámico: {e}")
            return 0.01
    
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
        """Monitorea trades activos y cierra por tiempo con validación de existencia"""
        while not self._stop_monitoring.is_set():
            try:
                now = datetime.now()
                tickets_to_remove = []
                
                # Sincronizar con MT5 ocasionalmente para limpiar tickets cerrados manualmente o por SL/TP
                try:
                    mt5_positions = self.order_agent.get_open_positions()
                    active_tickets = {pos.get('ticket') for pos in mt5_positions}
                    
                    # Si un ticket está en nuestra lista pero no en MT5, marcar para remover
                    for ticket in list(self.active_scalp_trades.keys()):
                        if ticket not in active_tickets:
                            tickets_to_remove.append(ticket)
                except Exception as e:
                    logger.debug(f"Error sincronizando monitoreo con MT5: {e}")

                for ticket, trade_info in list(self.active_scalp_trades.items()):
                    if ticket in tickets_to_remove:
                        continue
                        
                    elapsed = (now - trade_info['open_time']).total_seconds()
                    
                    # Cerrar si excede tiempo máximo
                    if elapsed >= self.max_trade_duration:
                        # Doble verificación de que todavía existe antes de avisar
                        exists = False
                        try:
                            positions = self.order_agent.get_open_positions()
                            exists = any(p.get('ticket') == ticket for p in positions)
                        except:
                            exists = True # Ante la duda, intentamos cerrar
                            
                        if exists:
                            logger.warning(f"[ScalpExecution] ⏱️ Tiempo máximo alcanzado para #{ticket}")
                            self._close_trade(ticket, "TIMEOUT")
                        
                        tickets_to_remove.append(ticket)
                    
                    # Verificar BE+1 cuando esté en profit
                    elif elapsed >= 30:  # Después de 30 segundos
                        self._check_breakeven(ticket, trade_info)
                
                for ticket in set(tickets_to_remove):
                    if ticket in self.active_scalp_trades:
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
