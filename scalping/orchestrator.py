"""
Scalping Orchestrator - Coordina las 6 capas del sistema de scalping
"""

from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger
import time
import threading

from .context_agent import ContextAgent
from .microstructure_agent import MicrostructureAgent
from .technical_filter import TechnicalFilter
from .execution_agent import ScalpExecutionAgent
from .risk_agent import ScalpRiskAgent
from .learning_agent import LearningAgent
from .snake_agent import SnakeAgent, SnakeAction


class ScalpingOrchestrator:
    """
    Orquestador del Sistema de Scalping
    
    Coordina las 6 capas en secuencia:
    1. Context → ¿Se puede tradear hoy?
    2. Microstructure → ¿Hay señal?
    3. Technical → ¿Se confirma?
    4. Risk → ¿Se permite?
    5. Execution → Ejecutar
    6. Learning → Aprender
    
    Ciclo rápido: cada 5-10 segundos
    """
    
    def __init__(self, 
                 mt5_connector, 
                 order_agent,
                 storage,
                 config: dict = None):
        self.mt5 = mt5_connector
        self.order_agent = order_agent
        self.storage = storage
        self.config = config or {}
        
        # Configuración de scalping
        scalp_config = self.config.get('scalping', {})
        
        # Inicializar agentes
        self.context_agent = ContextAgent(scalp_config)
        self.micro_agent = MicrostructureAgent(scalp_config)
        self.tech_filter = TechnicalFilter(scalp_config)
        self.execution_agent = ScalpExecutionAgent(order_agent, mt5_connector, scalp_config)
        self.risk_agent = ScalpRiskAgent(storage, mt5_connector, scalp_config)
        self.learning_agent = LearningAgent(storage, scalp_config)
        self.snake_agent = SnakeAgent()
        
        # Estado
        self.running = False
        self._shutdown_event = threading.Event()
        self.cycle_interval = scalp_config.get('cycle_interval_seconds', 10)
        self.max_positions = scalp_config.get('max_positions', 3)
        self.symbols = self.config.get('trading', {}).get('symbols', ['EURUSD', 'GBPUSD'])
        
        # Estadísticas de sesión
        self.session_stats = {
            'trades_executed': 0,
            'trades_blocked': 0,
            'signals_detected': 0,
            'context_blocks': 0,
            'risk_blocks': 0,
            'technical_rejects': 0,
            'snake_interventions': 0,
            'toxic_context_blocks': 0,
            'pacing_blocks': 0
        }
        
        # Trade Pacing Control
        self.last_trade_times = {} # symbol -> timestamp
        self.hourly_trade_counts = {} # symbol -> {hour: count}
        self.min_seconds_between_trades = scalp_config.get('min_seconds_between_trades', 300) # 5 min default
        self.max_trades_per_hour = scalp_config.get('max_trades_per_hour', 3)
        self.auto_maintain_positions = scalp_config.get('auto_maintain_positions', False) # Desactivado por defecto
        
        # Historial para detección de cierre
        self._last_pos_count = 0
        self._last_bg_sync = 0
        self._bg_sync_interval = 300 # 5 minutos
        
        logger.info("🧠 ScalpingOrchestrator inicializado")
        logger.info(f"   Símbolos: {self.symbols}")
        logger.info(f"   Ciclo: cada {self.cycle_interval}s")
    
    def start(self):
        """Inicia el ciclo de scalping"""
        self.running = True
        self._shutdown_event.clear()
        
        logger.info("⚡ Iniciando modo SCALPING")
        
        # Reset de sesión
        self.risk_agent.reset_session()
        
        while self.running and not self._shutdown_event.is_set():
            try:
                cycle_start = time.time()
                
                # 0. SNAKE MODE: Temporal Outcome Control Loop
                # (Procesar sesiones activas antes de cualquier otra cosa)
                # 0. REFRESH CONFIG: Cargar cambios desde la UI/JSON
                try:
                    import json
                    user_config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'user_config.json')
                    
                    # Revision de trades cerrados para el bandit
                    elapsed = time.time() - cycle_start # Use current elapsed time for this check
                    if elapsed >= 30: # Revision cada 30s aprox
                        p_count = len(self.order_agent.get_open_positions())
                        if p_count < self._last_pos_count:
                            logger.info("📉 Detectado cierre de posición. Sincronizando...")
                            recent_trades = self.storage.get_all_trade_results(limit=5)
                            for trade in recent_trades:
                                # Si el trade no ha sido procesado por el bandit
                                if trade.ticket not in self._processed_tickets:
                                    # Intentar recuperar qué preset se usó
                                    preset = trade.comment.split('|')[-1] if '|' in trade.comment else "balanced"
                                    self.learning_agent.register_trade_result(trade.__dict__, preset)
                                    self._processed_tickets.add(trade.ticket)

                            # Esto parece ser un análisis general, no ligado a un trade específico
                            # self.learning_agent.analyze_trade(recent_trades[0].__dict__ if recent_trades else {})
                        self._last_pos_count = p_count

                    if os.path.exists(user_config_path):
                        with open(user_config_path, 'r', encoding='utf-8') as f:
                            user_config = json.load(f)
                            if 'max_risk_percent' in user_config:
                                val = user_config['max_risk_percent']
                                self.risk_agent.max_daily_loss_percent = val
                                self.execution_agent.risk_per_trade_percent = val
                            if 'max_positions' in user_config:
                                val = user_config['max_positions']
                                self.max_positions = val
                                self.risk_agent.max_positions = val
                            if 'symbols' in user_config:
                                self.symbols = user_config['symbols']
                except Exception as config_err:
                    logger.debug(f"Error recargando config en scalper: {config_err}")

                self._process_snake_sessions()
                
                # ═══════════════════════════════════════════════════════════
                # AUTO-MAINTAIN: Asegurar al menos una posición por símbolo seleccionado
                # ═══════════════════════════════════════════════════════════
                if self.auto_maintain_positions:
                    positions = self.order_agent.get_open_positions()
                    symbols_with_positions = {p.get('symbol') for p in positions} if positions else set()
                    
                    # Combinar con trades que acabamos de abrir pero MT5 aún no reporta
                    pending_symbols = {t['symbol'] for t in self.execution_agent.active_scalp_trades.values()}
                    all_active_symbols = symbols_with_positions.union(pending_symbols)
                    
                    for symbol in self.symbols:
                        if symbol not in all_active_symbols:
                            logger.info(f"🤖 SCALPING AUTO-FIX: Forzando posición mínima en {symbol}")
                            # Usar dirección técnica o aleatoria para la entrada forzada
                            self._force_open_scalp(symbol)
                else:
                    logger.debug("🤖 AUTO-MAINTAIN desactivado por política de ruido.")
                
                # ═══════════════════════════════════════════════════════════
                # SYNC: Detectar cierres y sincronizar historial
                # ═══════════════════════════════════════════════════════════
                # num_positions = len(positions) if positions else 0 # positions might not be defined here
                # if num_positions < self._last_pos_count:
                #     logger.info("📉 SCALPING: Detectado cierre de posición. Sincronizando...")
                #     self._trigger_fast_sync()
                # self._last_pos_count = num_positions
                
                # BG Sync cada 5 mins
                now = time.time()
                if now - self._last_bg_sync > self._bg_sync_interval:
                    self._background_sync_cycle()
                    self._last_bg_sync = now
                
                # Ejecutar ciclo normal para cada símbolo
                for symbol in self.symbols:
                    if self._shutdown_event.is_set():
                        break
                    
                    self._process_symbol(symbol)
                
                # Esperar hasta próximo ciclo
                elapsed = time.time() - cycle_start
                sleep_time = max(0, self.cycle_interval - elapsed)
                
                if sleep_time > 0:
                    self._shutdown_event.wait(sleep_time)
                    
            except Exception as e:
                logger.error(f"Error en ciclo de scalping: {e}")
                time.sleep(5)
    
    def _force_open_scalp(self, symbol: str):
        """Abre una posición de scalping forzada si no hay ninguna, con chequeos de seguridad mínimos"""
        import random
        
        # 1. Chequeo de contexto mínimo
        rates_m5 = self._get_rates(symbol, "M5", 20)
        rates_m15 = self._get_rates(symbol, "M15", 20)
        context = self.context_agent.analyze(symbol, rates_m5, rates_m15)
        
        if not context['can_trade']:
            logger.warning(f"[Scalp] {symbol}: No se puede forzar entrada - Contexto bloqueado: {context['reasons']}")
            return

        # 2. Chequeo de riesgo
        risk = self.risk_agent.can_trade(symbol)
        if not risk['allowed']:
            logger.warning(f"[Scalp] {symbol}: No se puede forzar entrada - Riesgo bloqueado: {risk['reason']}")
            return

        # 3. Decidir dirección basada en micro-tendencia
        rates_m1 = self._get_rates(symbol, "M1", 5)
        if rates_m1 and len(rates_m1) >= 2:
            direction = "BUY" if rates_m1[-1]['close'] > rates_m1[0]['close'] else "SELL"
        else:
            direction = random.choice(["BUY", "SELL"])
            
        logger.info(f"⚡ Ejecutando entrada de scalping forzada (auto-fix): {direction} {symbol}")
        
        # 4. Ejecutar vía Execution Agent
        self.execution_agent.execute(
            symbol=symbol,
            direction=direction,
            entry_type="MARKET",
            confidence=0.70  # Confianza base para entradas forzadas
        )
    
    def stop(self):
        """Detiene el ciclo de scalping"""
        self.running = False
        self._shutdown_event.set()
    
    def _process_symbol(self, symbol: str):
        """Procesa un símbolo a través de las 6 capas"""
        
        logger.debug(f"[Scalp] Procesando {symbol}...")
        
        # ═══════════════════════════════════════════════════════════
        # CAPA 1: CONTEXTO - ¿Se puede tradear?
        # ═══════════════════════════════════════════════════════════
        rates_m5 = self._get_rates(symbol, "M5", 50)
        rates_h4 = self._get_rates(symbol, "H4", 50) # Nueva columna macro
        
        # Obtener experiencia de este símbolo
        experience = self.learning_agent.get_symbol_experience(symbol)
        logger.info(f"[Scalp] {symbol}: {experience.get('msg', 'Analiando memoria...')}")
        
        # Obtener spread actual para el filtro de contexto tóxico
        tick = self.mt5.get_tick(symbol)
        current_spread = (tick.ask - tick.bid) if tick else 0.0
        
        context = self.context_agent.analyze(symbol, rates_m5, rates_h4=rates_h4, current_spread=current_spread)
        
        # Log de sesgo macro
        if context.get('h4_bias'):
            logger.info(f"[Scalp] {symbol}: Bias H4 {context['h4_bias']} (Strength: {context['h4_strength']:.2f})")
        
        # Pasar ATR actual al execution agent para sus cálculos de SL/TP
        self.execution_agent.config['last_atr'] = context.get('atr', 0.0005)
        
        if not context['can_trade']:
            if context.get('is_toxic'):
                self.session_stats['toxic_context_blocks'] += 1
                logger.warning(f"[Scalp] {symbol}: Contexto TÓXICO (Spread/Volatilidad) - Omitiendo.")
            else:
                self.session_stats['context_blocks'] += 1
                logger.debug(f"[Scalp] {symbol}: Contexto NO favorable - {context['reasons']}")
            
            self._log_decision(symbol, "CONTEXT_BLOCK", context['reasons'])
            return
        
        # ═══════════════════════════════════════════════════════════
        # PACING: Control de frecuencia por símbolo
        # ═══════════════════════════════════════════════════════════
        if not self._check_pacing(symbol):
            self.session_stats['pacing_blocks'] += 1
            return
        
        # ═══════════════════════════════════════════════════════════
        # CAPA 2: MICROESTRUCTURA - ¿Hay señal?
        # ═══════════════════════════════════════════════════════════
        rates_m1 = self._get_rates(symbol, "M1", 100)
        
        micro = self.micro_agent.analyze(rates_m1, rates_m5)
        
        if micro['signal'] == 'NONE':
            logger.debug(f"[Scalp] {symbol}: Sin señal de microestructura")
            return
        
        self.session_stats['signals_detected'] += 1
        signal = micro['signal']
        confidence = micro['confidence']
        entry_type = micro['entry_type']
        
        logger.info(f"[Scalp] {symbol}: 📊 Señal {signal} detectada (conf: {confidence:.0%})")
        
        # ═══════════════════════════════════════════════════════════
        # PRESET SELECTION: Elegir política por símbolo (Fase 2)
        # ═══════════════════════════════════════════════════════════
        preset_name = self.learning_agent.bandit.select_preset(symbol, context)
        preset_params = self.learning_agent.bandit.get_params(preset_name)
        
        # Aplicar multiplicadores del preset al ATR
        k_sl = preset_params.get('k_sl', 1.5)
        k_tp = preset_params.get('k_tp', 2.5)
        
        logger.info(f"[Scalp] {symbol}: Usando preset '{preset_name}' (K_SL:{k_sl}, K_TP:{k_tp})")
        
        # Inyectar en config temporal para execution_agent
        self.execution_agent.config['current_k_sl'] = k_sl
        self.execution_agent.config['current_k_tp'] = k_tp
        self.execution_agent.config['current_preset'] = preset_name
        
        # ═══════════════════════════════════════════════════════════
        # CAPA 3: TÉCNICO - ¿Se confirma la señal?
        # ═══════════════════════════════════════════════════════════
        tech = self.tech_filter.confirm(signal, rates_m5)
        
        if not tech['confirms']:
            self.session_stats['technical_rejects'] += 1
            logger.info(f"[Scalp] {symbol}: ❌ Técnico rechaza señal - {tech['reason']}")
            self._log_decision(symbol, "TECH_REJECT", tech['reason'])
            return
        
        logger.info(f"[Scalp] {symbol}: ✓ Técnico confirma")
        
        # ═══════════════════════════════════════════════════════════
        # CAPA 5: RIESGO - ¿Se permite el trade?
        # ═══════════════════════════════════════════════════════════
        risk = self.risk_agent.can_trade(symbol)
        
        if not risk['allowed']:
            self.session_stats['risk_blocks'] += 1
            logger.warning(f"[Scalp] {symbol}: 🛡️ Riesgo bloquea - {risk['reason']}")
            self._log_decision(symbol, "RISK_BLOCK", risk['reason'])
            return
        
        logger.info(f"[Scalp] {symbol}: ✓ Riesgo permite (nivel: {risk['risk_level']})")
        
        # ═══════════════════════════════════════════════════════════
        # CAPA 4: EJECUCIÓN - Ejecutar trade
        # ═══════════════════════════════════════════════════════════
        logger.info(f"[Scalp] {symbol}: 🚀 EJECUTANDO {signal} {entry_type}")
        
        result = self.execution_agent.execute(
            symbol=symbol,
            direction=signal,
            entry_type=entry_type,
            confidence=confidence
        )
        
        if result['success']:
            self.session_stats['trades_executed'] += 1
            # Registrar tiempo del último trade para Pacing
            self.last_trade_times[symbol] = time.time()
            # Incrementar contador horario
            current_hour = datetime.now().hour
            if symbol not in self.hourly_trade_counts: self.hourly_trade_counts[symbol] = {}
            self.hourly_trade_counts[symbol][current_hour] = self.hourly_trade_counts[symbol].get(current_hour, 0) + 1
            
            logger.info(f"[Scalp] {symbol}: ✅ Trade ejecutado #{result['ticket']}")
            
            self._log_decision(symbol, "EXECUTED", f"#{result['ticket']} @ {result['entry_price']}")
            
            # Registrar trade abierto para seguimiento de aprendizaje
            if hasattr(self.learning_agent, 'register_opened_trade'):
                self.learning_agent.register_opened_trade(
                    ticket=result['ticket'],
                    symbol=symbol,
                    direction=signal,
                    entry_price=result['entry_price'],
                    confidence=confidence,
                    time=datetime.now()
                )
            
        else:
            self.session_stats['trades_blocked'] += 1
            logger.error(f"[Scalp] {symbol}: ❌ Error en ejecución - {result['error']}")
            self._log_decision(symbol, "EXEC_ERROR", result['error'])

    def _trigger_fast_sync(self):
        """Sincronización rápida por evento"""
        try:
            deals = self.mt5.get_history_deals(days=1)
            if deals:
                self.storage.import_mt5_history(deals, connector=self.mt5)
                logger.info("⚡ SCALPING: Fast Sync completado")
        except Exception as e:
            logger.error(f"Error en fast sync (Scalp): {e}")

    def _background_sync_cycle(self):
        """Sincronización profunda periódica"""
        try:
            # Sincronizar últimos 15 días
            deals = self.mt5.get_history_deals(days=15)
            if deals:
                self.storage.import_mt5_history(deals, connector=self.mt5)
                logger.debug(f"🔄 SCALPING: BG Sync completado ({len(deals)} deals)")
        except Exception as e:
            logger.error(f"Error en bg sync (Scalp): {e}")
    
    def _get_rates(self, symbol: str, timeframe: str, count: int) -> list:
        """Obtiene datos de velas"""
        try:
            rates = self.mt5.get_symbol_data(symbol, timeframe, count)
            if rates is not None:
                return rates
        except Exception as e:
            logger.error(f"Error obteniendo datos {symbol} {timeframe}: {e}")
        return []
    
    def _log_decision(self, symbol: str, decision: str, details: str):
        """Registra decisión en storage"""
        try:
            if self.storage:
                self.storage.save_agent_log(
                    agent_name="ScalpOrchestrator",
                    action=f"{decision} {symbol}",
                    result=details[:200],  # Limitar longitud
                    success=decision in ["EXECUTED"],
                    execution_time=0
                )
        except Exception as e:
            logger.debug(f"Error logging decision: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas de la sesión"""
        return {
            **self.session_stats,
            'risk_status': {
                'session_trades': self.risk_agent.session_trades,
                'streak_count': self.risk_agent.streak_count,
                'daily_pnl': self.risk_agent.daily_pnl,
                'is_in_cooldown': self.risk_agent.cooldown_until is not None
            },
            'learning_profile': self.learning_agent.get_trading_profile()
        }
    
    def process_closed_trade(self, trade_data: Dict[str, Any]):
        """Procesa un trade cerrado para aprendizaje"""
        
        # Registrar resultado en risk agent
        self.risk_agent.register_trade_result(
            profit=trade_data.get('profit', 0),
            ticket=trade_data.get('ticket', 0)
        )
        
        # Analizar con learning agent
        analysis = self.learning_agent.analyze_trade(trade_data)
        
        logger.info(f"[Scalp] Learning: {analysis['analysis']}")
        
        if analysis['recommendations']:
            for rec in analysis['recommendations']:
                logger.info(f"[Scalp] 💡 Recomendación: {rec}")

    def _check_pacing(self, symbol: str) -> bool:
        """Verifica los límites de frecuencia de trading (Trade Pacing)"""
        now = time.time()
        
        # 1. Cooldown entre trades
        last_time = self.last_trade_times.get(symbol, 0)
        elapsed = now - last_time
        if elapsed < self.min_seconds_between_trades:
            wait_needed = self.min_seconds_between_trades - elapsed
            logger.debug(f"[Scalp] {symbol}: Pacing Cooldown ({int(wait_needed)}s restantes)")
            return False
            
        # 2. Máximo trades por hora
        current_hour = datetime.now().hour
        counts = self.hourly_trade_counts.get(symbol, {}).get(current_hour, 0)
        if counts >= self.max_trades_per_hour:
             logger.warning(f"[Scalp] {symbol}: Límite horario de trades alcanzado ({counts}/{self.max_trades_per_hour})")
             return False
             
        return True

    def _process_snake_sessions(self):
        """Procesa las sesiones de control temporal activas (Snake Mode)"""
        try:
            active_sessions = self.storage.get_active_snake_sessions()
            if not active_sessions:
                return

            # Obtener datos de MT5
            positions = self.order_agent.get_open_positions()
            positions_map = {p['ticket']: p for p in positions}
            
            for session in active_sessions:
                try:
                    ticket = session.ticket
                    pos_data = positions_map.get(ticket)
                    
                    if not pos_data:
                        # La posición ya no existe, cerrar sesión como completada (o fallida)
                        logger.warning(f"🐍 Posición #{ticket} no encontrada. Cerrando sesión Snake.")
                        self.storage.update_snake_session(session.id, "COMPLETED", "NEUTRAL", 0, "Position closed manually or by SL/TP")
                        continue
                    
                    # Obtener rates_m1 para análisis PPM si es necesario
                    symbol = pos_data.get('symbol')
                    rates_m1 = self._get_rates(symbol, "M1", 50) if symbol else None
                    
                    # Evaluación del Snake Agent
                    evaluation = self.snake_agent.evaluate(session, pos_data, rates_m1=rates_m1)
                    
                    action = evaluation['action']
                    status = evaluation['status']
                    confidence = evaluation['confidence']
                    reason = evaluation['reason']
                    
                    # Ejecutar acción
                    if action == SnakeAction.CLOSE:
                        logger.info(f"🐍 Snake EXECUTE: Closing #{ticket} -> {reason}")
                        success = self.order_agent.close_position(ticket)
                        
                        if success:
                            self.storage.update_snake_session(session.id, "COMPLETED", status.value, pos_data.get('profit', 0), reason)
                            self.session_stats['snake_interventions'] += 1
                            logger.info(f"🐍 Snake Closed Successfully (#{ticket})")
                        else:
                            logger.error(f"⚠️ Snake Failed to close #{ticket}. Will retry next tick.")
                        
                    elif action == SnakeAction.PROTECT:
                        # Mover a Break-Even
                        current_sl = pos_data.get('sl', 0)
                        open_price = pos_data.get('open_price')
                        
                        # Chequear si ya está protegido para no spammear
                        is_protected = False
                        if pos_data['type'] == 0: # BUY
                            is_protected = current_sl >= open_price
                        else: # SELL
                             is_protected = current_sl <= open_price and current_sl > 0
                        
                        if not is_protected:
                            logger.info(f"🐍 Snake PROTECT: Break-Even #{ticket} -> {reason}")
                            # Usar lógica de modify del order agent
                            new_sl = open_price
                            self.order_agent.modify_position(ticket, new_sl, pos_data.get('tp', 0))

                    elif action == SnakeAction.RELEASE:
                        logger.info(f"🐍 Snake RELEASE: Releasing control of #{ticket} -> {reason}")
                        # Mark session as completed but DO NOT close position
                        self.storage.update_snake_session(session.id, "COMPLETED", status.value, pos_data.get('profit', 0), reason)
                        # We don't increment interventions or maybe we do to show activity? 
                        # Let's count it as a positive intervention (it managed it to safety)
                        self.session_stats['snake_interventions'] += 1
                        logger.info(f"🐍 Snake Released Successfully (#{ticket})")
                except Exception as e:
                    logger.error(f"Error processing individual Snake session #{session.ticket}: {e}")

        except Exception as e:
            logger.error(f"Error procesando ciclo Snake: {e}")
