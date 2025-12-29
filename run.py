"""
Run - Orquestador principal del sistema de trading con IA
"""

import sys
import os
import time
import signal
import threading
from datetime import datetime, timedelta
from enum import Enum

from typing import Optional, Dict
from loguru import logger
import yaml
import schedule

from core.states import TradingState

# Configurar path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Configurar logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
    level="INFO"
)
logger.add(
    "data/logs/trading.log",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG"
)


class ExecutionMode(Enum):
    """Modo de ejecución del sistema"""
    DEMO = "demo"           # Solo logging, sin órdenes reales
    SAFE_AUTO = "safe_auto" # Auto-ejecución con límites estrictos
    FULL_AUTO = "full_auto" # Auto-ejecución completa (usar con precaución)


def load_unified_config(config_path: str = "config.yaml") -> dict:
    """Carga la configuración mezclando YAML y JSON persistente"""
    import json
    config = {}
    
    # 1. Cargar config base (YAML)
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Error cargando config YAML: {e}")
        
    # 2. Cargar config persistente de usuario (JSON)
    user_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'user_config.json')
    try:
        if os.path.exists(user_config_path):
            with open(user_config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                
                # Mezclar parámetros principales
                if 'symbols' in user_config:
                    config['trading'] = config.get('trading', {})
                    config['trading']['symbols'] = user_config['symbols']
                
                if 'max_risk_percent' in user_config:
                    config['risk'] = config.get('risk', {})
                    config['risk']['max_allowed_risk_percent'] = user_config['max_risk_percent']
                    
                if 'max_positions' in user_config:
                    if 'risk' not in config: config['risk'] = {}
                    config['risk']['max_open_positions'] = user_config['max_positions']
                
                if 'trading_mode' in user_config:
                    config['trading_mode'] = user_config['trading_mode']
                    
                logger.info("✅ Configuración persistente cargada desde user_config.json")
    except Exception as e:
        logger.warning(f"No se pudo cargar user_config.json (usando defaults): {e}")
        
    return config


class TradingOrchestrator:
    """
    Orquestador principal del sistema de trading.
    
    Coordina todos los agentes y módulos para ejecutar el ciclo de trading.
    """
    
    def __init__(self, config: dict = None):
        """Inicializa el orquestador con una configuración ya cargada"""
        self.config = config or load_unified_config()
        self.running = False
        self._shutdown_event = threading.Event()
        self.state = TradingState.IDLE
        
        # Modo de ejecución (cambiar a SAFE_AUTO cuando esté listo)
        self.execution_mode = ExecutionMode.SAFE_AUTO
        
        # Control de trading
        self.last_trade_time: Dict[str, datetime] = {}  # Por símbolo
        self.daily_trades = 0
        self.max_daily_trades = self.config.get('risk', {}).get('max_daily_trades', 10)
        self.trade_cooldown_minutes = 15
        
        # Importar módulos
        self._import_modules()
        
        logger.info("=" * 60)
        logger.info("🚀 Sistema de Trading con IA - Iniciando...")
        logger.info(f"📋 Modo de ejecución: {self.execution_mode.value.upper()}")
        logger.info("=" * 60)
    
    def _import_modules(self):
        """Importa módulos del sistema"""
        try:
            from agents.llm_provider import get_llm
            from agents.news_agent import NewsAgent
            from agents.sentiment_agent import SentimentAgent
            from agents.technical_agent import TechnicalAgent
            from agents.risk_agent import RiskAgent
            from agents.memory_agent import MemoryAgent
            from mt5.order_agent import OrderAgent

            from mt5.connector import MT5Connector
            from strategies.signals import SignalGenerator
            from strategies.combiner import MultiAgentCombiner
            from scraping.storage import get_storage
            from scalping.snake_agent import SnakeAgent, SnakeAction, SnakeStatus
            
            # Inicializar componentes
            self.llm = get_llm()
            self.news_agent = NewsAgent()
            self.sentiment_agent = SentimentAgent()
            self.technical_agent = TechnicalAgent()
            self.risk_agent = RiskAgent()
            self.memory_agent = MemoryAgent()
            self.order_agent = OrderAgent()

            self.mt5 = MT5Connector()
            self.signal_generator = SignalGenerator()
            self.combiner = MultiAgentCombiner()
            self.storage = get_storage()
            self.snake_agent = SnakeAgent()
            
            logger.info("✅ Todos los módulos cargados correctamente")
            
        except ImportError as e:
            logger.error(f"Error importando módulos: {e}")
            raise
    
    def check_prerequisites(self) -> bool:
        """Verifica que todos los prerrequisitos estén listos"""
        logger.info("Verificando prerrequisitos...")
        
        checks = {
            "LLM disponible": self.llm.is_available(),
            "MT5 conectado": self.mt5.connect(),
        }
        
        all_ok = True
        for check, status in checks.items():
            icon = "✅" if status else "❌"
            logger.info(f"  {icon} {check}")
            if not status:
                all_ok = False
        
        if not all_ok:
            logger.warning("⚠️ Algunos prerrequisitos fallaron. El sistema funcionará con capacidad reducida.")
        
        return True  # Continuar incluso con advertencias
    
    def _can_trade(self, symbol: str) -> tuple[bool, str]:
        """Verifica si se puede ejecutar un trade para este símbolo"""
        now = datetime.now()
        
        # Verificar límite diario
        if self.daily_trades >= self.max_daily_trades:
            return False, f"Límite diario alcanzado ({self.max_daily_trades} trades)"
        
        # Verificar cooldown por símbolo
        if symbol in self.last_trade_time:
            elapsed = (now - self.last_trade_time[symbol]).total_seconds() / 60
            if elapsed < self.trade_cooldown_minutes:
                remaining = self.trade_cooldown_minutes - elapsed
                return False, f"Cooldown activo para {symbol} ({remaining:.0f} min restantes)"
        
        # Verificar horario de mercado (simplificado: lunes-viernes, 8:00-22:00)
        if now.weekday() >= 5:  # Sábado o domingo
            return False, "Mercado cerrado (fin de semana)"
        
        if now.hour < 8 or now.hour >= 22:
            return False, f"Fuera de horario de trading ({now.hour}:00)"
        
        return True, "OK"
    
    def _record_trade(self, symbol: str):
        """Registra un trade ejecutado"""
        self.last_trade_time[symbol] = datetime.now()
        self.daily_trades += 1
        logger.info(f"📝 Trades hoy: {self.daily_trades}/{self.max_daily_trades}")
    
    def trading_cycle(self):
        """
        Runs the full state machine lifecycle.
        IDLE -> OBSERVE -> READY -> EXECUTE (-> MANAGE)
        """
        if self._shutdown_event.is_set():
            return
            
        logger.info("-" * 40)
        logger.info(f"🔄 GLOBAL STATE: {self.state.name} | {datetime.now().strftime('%H:%M:%S')}")

        # 0. SNAKE MODE Check (Works in Normal Mode too)
        self._process_snake_sessions()
        
        # 1. State Transition: IDLE -> OBSERVE
        if self.state == TradingState.IDLE:
             self.state = TradingState.OBSERVE
             
        # 2. State: OBSERVE (Data Collection)
        if self.state == TradingState.OBSERVE:
            try:
                # Actualizar datos técnicos, noticias, etc.
                # Nota: El scraping pesado se mantiene en su propio schedule para no bloquear,
                # pero aquí verificamos que tenemos datos recientes.
                pass 
                self.state = TradingState.READY
            except Exception as e:
                logger.error(f"Error in OBSERVE state: {e}")
                self.state = TradingState.RECOVER

        # 3. State: READY (Analysis & Signal Generation)
        if self.state == TradingState.READY:
            try:
                symbols = [s['symbol'] for s in self.config.get('symbols', []) if s.get('enabled', True)]
                for symbol in symbols:
                    self._process_symbol_state_guided(symbol)
                
                # If all processed successfully
                self.state = TradingState.IDLE # Return to IDLE until next trigger
                
            except Exception as e:
                 logger.error(f"Error in READY/EXECUTE flow: {e}")
                 self.state = TradingState.RECOVER

        # 4. State: RECOVER
        if self.state == TradingState.RECOVER:
             logger.warning("🚑 Entering RECOVERY mode...")
             try:
                 if not self.mt5.ensure_connected():
                     self.mt5.connect()
                 self.state = TradingState.IDLE
                 logger.info("✅ Recovery successful -> IDLE")
             except Exception as e:
                 logger.error(f"Recovery failed: {e}")
                 
    def _process_snake_sessions(self):
        """Procesa las sesiones de control temporal activas (Snake Mode) - Ported to TradingOrchestrator"""
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
                    
                    # Evaluación del Snake Agent
                    evaluation = self.snake_agent.evaluate(session, pos_data)
                    
                    action = evaluation['action']
                    
                    # Ejecutar acción
                    if action == SnakeAction.CLOSE:
                        reason = evaluation['reason']
                        logger.info(f"🐍 Snake EXECUTE: Closing #{ticket} -> {reason}")
                        success = self.order_agent.close_position(ticket)
                        
                        if success:
                             # Importante: Trigger sync inmediata para que el dashboard lo vea
                            self.storage.update_snake_session(session.id, "COMPLETED", evaluation['status'].value, pos_data.get('profit', 0), reason)
                            logger.info(f"🐍 Snake Closed Successfully (#{ticket})")
                            self._trigger_fast_sync() 
                        else:
                            logger.error(f"⚠️ Snake Failed to close #{ticket}. Will retry next tick.")
                        
                    elif action == SnakeAction.PROTECT:
                        # Mover a Break-Even
                        current_sl = pos_data.get('sl', 0)
                        open_price = pos_data.get('open_price')
                        reason = evaluation['reason']
                        
                        # Chequear si ya está protegido para no spammear
                        is_protected = False
                        if pos_data['type'] == 0: # BUY
                            is_protected = current_sl >= open_price
                        else: # SELL
                             is_protected = current_sl <= open_price and current_sl > 0
                        
                        if not is_protected:
                            logger.info(f"🐍 Snake PROTECT: Break-Even #{ticket} -> {reason}")
                            new_sl = open_price
                            self.order_agent.modify_position(ticket, new_sl, pos_data.get('tp', 0))
                except Exception as e:
                    logger.error(f"Error processing individual Snake session #{session.ticket}: {e}")

        except Exception as e:
            logger.error(f"Error procesando ciclo Snake: {e}")

    def _trigger_fast_sync(self):
        """Fuerza una sincronización rápida del historial"""
        try:
             deals = self.mt5.get_history_deals(days=1)
             if deals:
                 self.storage.import_mt5_history(deals)
                 logger.info("⚡ Fast Sync activado por evento de cierre")
        except Exception as e:
            logger.error(f"Error en fast sync: {e}")
                 
    def _process_symbol_state_guided(self, symbol: str):
        """Procesa un símbolo específico bajo la máquina de estados"""
        
        # ... Logica de análisis (READY) ...
        # ... Si hay señal -> Cambiar a EXECUTE implícito para ese trade ...
        
        # (Reutilizamos la lógica existente pero mentalmente mapeada a READY -> EXECUTE)
        logger.debug(f"[{self.state.name}] Procesando {symbol}...")
        
        try:
            # READY: Analisis Tecnico
            if self.mt5.connected:
                timeframe = self.config.get('strategy', {}).get('timeframe', 'M15')
                rates = self.mt5.get_rates(symbol, timeframe, 100)
                if rates is not None and len(rates) > 0:
                    tech_result = self.technical_agent.analyze_symbol(rates, symbol)
                else:
                    tech_result = {"combined_signal": "HOLD", "combined_score": 0}
            else:
                tech_result = {"combined_signal": "HOLD", "combined_score": 0}
            
            # READY: Sentiment
            if self.llm.is_available():
                news_list = self.storage.get_recent_news(hours=24, processed=True)
                news_texts = [n.title for n in news_list[:5]]
                if news_texts:
                    sent_result = self.sentiment_agent.analyze_for_symbol(news_texts, symbol)
                else:
                    sent_result = {"sentiment": "neutral", "score": 0, "confidence": 0}
            else:
                 sent_result = {"sentiment": "neutral", "score": 0, "confidence": 0}

            news_result = self.news_agent.get_market_sentiment(symbol[:3])
            
            # READY: Combiner
            decision = self.combiner.make_decision(symbol, tech_result, sent_result, news_result)
            
            # EXECUTE Transition Check
            if decision.action in ["BUY", "SELL"] and decision.confidence > 0.5:
                # EXECUTE: Risk Check (Context Kill Switch + Core Position)
                 current_positions = self.order_agent.get_open_positions()
                 symbol_positions = [p for p in current_positions if p.get('symbol') == symbol]
                 
                 # 1. Kill Switch: Si la señal combinada es débil, abortar
                 if abs(decision.combined_score) < 0.2:
                      logger.warning(f"🚫 [Kill Switch] Señal débil ({decision.combined_score:.2f}) en {symbol}. Entradas bloqueadas.")
                      return

                 # 2. Core Position Rule: Máximo 1 posición "Core" por símbolo
                 # Solo permitimos añadir si la posición existente está en profit significativo (piramidación segura)
                 # o si la lógica de scalping (que gestiona sus propias IDs) lo permite.
                 if len(symbol_positions) >= 1:
                     # Verificar si es una posición ganadora para permitir add-on
                     # Por simplicidad y seguridad fase 3: Bloquear add-ons por ahora
                     logger.info(f"🛑 [Core Logic] Ya existe posición en {symbol}. Bloqueando nueva entrada (Regla: 1 Core).")
                     return

                 risk_check = self.risk_agent.run({
                    "symbol": symbol,
                    "type": decision.action,
                    "volume": 0.01,
                    "signal_strength": decision.confidence,
                    "balance": self._get_balance(),
                    "open_positions": len(current_positions)
                })
                
                 if risk_check.success and risk_check.data.get("approved"):
                    # EXECUTE: Send Order
                    tp_pips = risk_check.data.get("recommended_tp", 100)
                    sl_pips = risk_check.data.get("recommended_sl", 50)
                    
                    # Force R:R >= 2 (Ajuste 1: TP dinámico / ratio fijo mínimo)
                    if tp_pips < (sl_pips * 2):
                        tp_pips = sl_pips * 2
                        
                    logger.info(f"🚀 EXECUTE STATE: Sending order for {symbol} | R:R Planificado: {tp_pips/sl_pips:.1f}")
                    self._execute_trade(
                        symbol=symbol,
                        action=decision.action,
                        volume=risk_check.data.get("max_volume", 0.01),
                        sl_pips=sl_pips,
                        tp_pips=tp_pips,
                        signal_id=None
                    )
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
            raise e # Let the main loop handle transition to RECOVER
    
    def _execute_trade(self, symbol: str, action: str, volume: float, sl_pips: int, tp_pips: int, signal_id: Optional[int]):
        """Ejecuta una orden según el modo de ejecución"""
        
        # Verificar si podemos tradear
        can_trade, reason = self._can_trade(symbol)
        if not can_trade:
            logger.info(f"  ⏸️ Trade no ejecutado: {reason}")
            return
        
        if self.execution_mode == ExecutionMode.DEMO:
            # Solo logging
            logger.info(f"  🎭 [DEMO] Orden simulada: {action} {symbol} x{volume}")
            self._log_trade_decision(symbol, action, volume, sl_pips, tp_pips, "SIMULATED")
            
        elif self.execution_mode in [ExecutionMode.SAFE_AUTO, ExecutionMode.FULL_AUTO]:
            # Ejecución real
            logger.info(f"  🚀 [AUTO] Ejecutando: {action} {symbol} x{volume}")
            
            order_result = self.order_agent.run({
                "symbol": symbol,
                "type": action,
                "volume": volume,
                "sl_pips": sl_pips,
                "tp_pips": tp_pips,
                "signal_id": signal_id
            })
            
            if order_result.success:
                self._record_trade(symbol)
                logger.info(f"  ✅ Orden ejecutada: Ticket #{order_result.data.get('ticket', 'N/A')}")
                self._log_trade_decision(symbol, action, volume, sl_pips, tp_pips, "EXECUTED")
            else:
                logger.error(f"  ❌ Error en orden: {order_result.error}")
                self._log_trade_decision(symbol, action, volume, sl_pips, tp_pips, f"ERROR: {order_result.error}")
    
    def _log_trade_decision(self, symbol: str, action: str, volume: float, sl_pips: int, tp_pips: int, status: str):
        """Registra decisión de trade en storage"""
        self.storage.save_agent_log(
            agent_name="OrderAgent",
            action=f"{action} {symbol} x{volume}",
            result=f"SL:{sl_pips} TP:{tp_pips} - {status}",
            success=status in ["SIMULATED", "EXECUTED"],
            execution_time=0
        )
    
    def _get_balance(self) -> float:
        """Obtiene balance de la cuenta"""
        if self.mt5.connected:
            info = self.mt5.get_account_info()
            return info.get('balance', 1000) if info else 1000
        return 1000
    
    def scraping_cycle(self):
        """Ejecuta ciclo de scraping de noticias"""
        if self._shutdown_event.is_set():
            return
        
        logger.info("📰 Ejecutando ciclo de scraping...")
        
        try:
            result = self.news_agent.run(None)
            if result.success:
                logger.info(f"  Noticias: {result.data.get('news_saved', 0)} nuevas")
            else:
                logger.warning(f"  Error en scraping: {result.error}")
        except Exception as e:
            logger.error(f"Error en scraping: {e}")
    
    def position_monitoring_cycle(self):
        """Monitorea posiciones abiertas y aplica trailing stop/break-even"""
        if self._shutdown_event.is_set():
            return
        
        if self.execution_mode == ExecutionMode.DEMO:
            return  # No monitorear en modo demo
        
        try:
            positions = self.order_agent.get_open_positions()
            num_positions = len(positions) if positions else 0
            
            logger.debug(f"📍 Posiciones abiertas: {num_positions}")
            
            # AUTO-TRADE: Mantener mínimo 2 posiciones
            min_positions = 2
            if num_positions < min_positions:
                self._open_auto_trades(min_positions - num_positions, positions)
            
            # Gestionar posiciones existentes
            if positions:
                for pos in positions:
                    self._manage_position(pos)
            
            # CHECK PARA SYNC RÁPIDO DE ESTADÍSTICAS
            # Si teníamos más posiciones antes que ahora, significa que se cerró algo (manual o TP/SL)
            if hasattr(self, '_last_pos_count'):
                if num_positions < self._last_pos_count:
                    logger.info("📉 Detectado cierre de posición (count drop). Ejecutando Fast Sync...")
                    self._trigger_fast_sync()
            
            self._last_pos_count = num_positions
                    
        except Exception as e:
            logger.error(f"Error en monitoreo de posiciones: {e}")
    
    def _open_auto_trades(self, num_trades: int, existing_positions: list):
        """Abre trades automáticos para mantener mínimo de posiciones"""
        import random
        
        symbols = self.config.get('trading', {}).get('symbols', ['EURUSD', 'GBPUSD'])
        
        # Obtener símbolos que ya tienen posición
        existing_symbols = set()
        if existing_positions:
            for pos in existing_positions:
                existing_symbols.add(pos.get('symbol', ''))
        
        # Priorizar símbolos sin posición
        available_symbols = [s for s in symbols if s not in existing_symbols]
        if not available_symbols:
            available_symbols = symbols
        
        for i in range(num_trades):
            symbol = random.choice(available_symbols)
            
            # Decidir dirección basada en análisis técnico simple o aleatorio
            try:
                rates = self.mt5.get_symbol_data(symbol, "M15", 20)
                if rates is not None and len(rates) > 0:
                    # Tendencia simple: último precio vs promedio
                    last_close = rates[-1]['close']
                    avg_close = sum(r['close'] for r in rates) / len(rates)
                    action = "BUY" if last_close > avg_close else "SELL"
                else:
                    action = random.choice(["BUY", "SELL"])
            except:
                action = random.choice(["BUY", "SELL"])
            
            # Ejecutar trade con parámetros seguros
            volume = 0.01  # Volumen mínimo
            sl_pips = 50   # Stop loss conservador
            tp_pips = 100  # Take profit 2:1
            
            logger.info(f"🤖 AUTO-TRADE: Abriendo {action} {symbol} (manteniendo mín. posiciones)")
            
            order_result = self.order_agent.run({
                "symbol": symbol,
                "type": action,
                "volume": volume,
                "sl_pips": sl_pips,
                "tp_pips": tp_pips,
                "signal_id": None
            })
            
            if order_result.success:
                ticket = order_result.data.get('ticket', 'N/A')
                logger.info(f"  ✅ Auto-trade ejecutado: #{ticket}")
                self.storage.save_agent_log("OrderAgent", f"Auto {action} {symbol}",
                    f"Ticket #{ticket} - Manteniendo mín. posiciones", True, 0)
            else:
                logger.error(f"  ❌ Error auto-trade: {order_result.error}")
                self.storage.save_agent_log("OrderAgent", f"Auto {action} {symbol} FALLIDO",
                    f"Error: {order_result.error}", False, 0)
    
    def _manage_position(self, pos):
        """Gestiona una posición individual - trailing stop y break-even"""
        try:
            # pos es un diccionario, acceder con ['key']
            symbol = pos['symbol']
            ticket = pos['ticket']
            pos_type = pos['type']
            open_price = pos['open_price']
            current_price = pos['current_price']
            sl = pos['sl']
            tp = pos['tp']
            
            symbol_info = self.mt5.get_symbol_info(symbol)
            if not symbol_info:
                return
            
            point = symbol_info.point
            pip_value = point * 10
            
            # Calcular distancia en pips desde entrada
            if pos_type == 0 or pos_type == "BUY":  # 0 = BUY en MT5
                profit_pips = (current_price - open_price) / pip_value
            else:
                profit_pips = (open_price - current_price) / pip_value
            
            # Configuración de trailing (Ajuste 1: BE rápido)
            trailing_activation_pips = 30  
            trailing_distance_pips = 25    
            breakeven_activation_pips = 10 # Break-even RÁPIDO (antes 20)
            breakeven_buffer_pips = 2      
            
            # 1. Break-Even: Mover SL a entrada + buffer cuando profit > activación
            if profit_pips >= breakeven_activation_pips:
                if pos_type == 0 or pos_type == "BUY":
                    new_sl = open_price + (breakeven_buffer_pips * pip_value)
                    if sl < new_sl:
                        success = self.order_agent.modify_position(ticket, new_sl, tp)
                        if success:
                            logger.info(f"  🔒 Break-even aplicado: #{ticket} SL → {new_sl:.5f}")
                            self._log_position_management(ticket, "BREAKEVEN", new_sl)
                else:
                    new_sl = open_price - (breakeven_buffer_pips * pip_value)
                    if sl == 0 or sl > new_sl:
                        success = self.order_agent.modify_position(ticket, new_sl, tp)
                        if success:
                            logger.info(f"  🔒 Break-even aplicado: #{ticket} SL → {new_sl:.5f}")
                            self._log_position_management(ticket, "BREAKEVEN", new_sl)
            
            # 2. Trailing Stop: Mover SL siguiendo el precio
            if profit_pips >= trailing_activation_pips:
                if pos_type == 0 or pos_type == "BUY":
                    new_sl = current_price - (trailing_distance_pips * pip_value)
                    if new_sl > sl:
                        success = self.order_agent.modify_position(ticket, new_sl, tp)
                        if success:
                            logger.info(f"  📏 Trailing aplicado: #{ticket} SL → {new_sl:.5f}")
                            self._log_position_management(ticket, "TRAILING", new_sl)
                else:
                    new_sl = current_price + (trailing_distance_pips * pip_value)
                    if sl == 0 or new_sl < sl:
                        success = self.order_agent.modify_position(ticket, new_sl, tp)
                        if success:
                            logger.info(f"  📏 Trailing aplicado: #{ticket} SL → {new_sl:.5f}")
                            self._log_position_management(ticket, "TRAILING", new_sl)
                            
        except Exception as e:
            logger.error(f"Error gestionando posición #{pos.get('ticket', '?')}: {e}")
    
    def _log_position_management(self, ticket: int, action: str, new_sl: float):
        """Registra acción de gestión de posición"""
        self.storage.save_agent_log(
            agent_name="PositionManager",
            action=f"{action} #{ticket}",
            result=f"New SL: {new_sl:.5f}",
            success=True,
            execution_time=0
        )
    
    def health_check_cycle(self):
        """Verifica salud de conexiones MT5 y Ollama"""
        if self._shutdown_event.is_set():
            return
        
        health_status = {
            "mt5": False,
            "ollama": False,
            "timestamp": datetime.now().isoformat()
        }
        
        # Check MT5
        try:
            if not self.mt5.connected:
                logger.warning("🔌 MT5 desconectado, intentando reconectar...")
                if self.mt5.connect():
                    logger.info("✅ MT5 reconectado")
                    health_status["mt5"] = True
                else:
                    logger.error("❌ No se pudo reconectar a MT5")
            else:
                # Verificar que realmente responde
                account = self.mt5.get_account_info()
                health_status["mt5"] = account is not None
                if not health_status["mt5"]:
                    logger.warning("⚠️ MT5 conectado pero no responde")
        except Exception as e:
            logger.error(f"Error verificando MT5: {e}")
        
        # Check Ollama/LLM
        try:
            health_status["ollama"] = self.llm.is_available()
            if not health_status["ollama"]:
                logger.warning("⚠️ Ollama no disponible - análisis de sentimiento deshabilitado")
        except Exception as e:
            logger.error(f"Error verificando Ollama: {e}")
        
        # Registrar estado
        self.storage.save_agent_log(
            agent_name="HealthMonitor",
            action="health_check",
            result=f"MT5:{health_status['mt5']} LLM:{health_status['ollama']}",
            success=health_status["mt5"],  # MT5 es crítico
            execution_time=0
        )
        
        logger.debug(f"🏥 Health: MT5={'✅' if health_status['mt5'] else '❌'} | LLM={'✅' if health_status['ollama'] else '❌'}")
    
    def background_sync_cycle(self):
        """Sincroniza trades en segundo plano para mantener la DB actualizada"""
        if self._shutdown_event.is_set():
            return
            
        try:
            connector = self.mt5
            if connector.connected:
                # Sincronizar últimos 2 días cada 5 minutos
                deals = connector.get_history_deals(days=2)
                if deals:
                    self.storage.import_mt5_history(deals)
                    logger.debug(f"🔄 Sincronización en segundo plano completada ({len(deals)} deals)")
        except Exception as e:
            logger.error(f"Error en sincronización en segundo plano: {e}")

    def start(self):
        """Inicia el orquestador"""
        if not self.check_prerequisites():
            logger.error("Falló verificación de prerrequisitos")
            return
        
        self.running = True
        
        # Configurar schedule
        interval = self.config.get('scraping', {}).get('interval_minutes', 15)
        
        # Trading cada minuto
        schedule.every(1).minutes.do(self.trading_cycle)
        
        # Monitoreo de posiciones cada 30 segundos
        schedule.every(30).seconds.do(self.position_monitoring_cycle)
        
        # Sincronización de historial cada 5 minutos
        schedule.every(5).minutes.do(self.background_sync_cycle)
        
        # Scraping según configuración
        schedule.every(interval).minutes.do(self.scraping_cycle)
        
        # Health check cada minuto
        schedule.every(1).minutes.do(self.health_check_cycle)
        
        # Generar memoria diaria a medianoche
        schedule.every().day.at("00:01").do(self.generate_memory)
        
        # Reset contador diario a medianoche
        schedule.every().day.at("00:00").do(self._reset_daily_counters)
        
        logger.info(f"📅 Ciclo de trading: cada 1 minuto")
        logger.info(f"📅 Monitoreo posiciones: cada 30 segundos")
        logger.info(f"📅 Ciclo de scraping: cada {interval} minutos")
        logger.info(f"📅 Health check: cada 1 minuto")
        logger.info("")
        logger.info("🟢 Sistema iniciado. Presiona Ctrl+C para detener.")
        logger.info("")
        
        # Ejecutar primer ciclo inmediatamente
        self.health_check_cycle()
        self.scraping_cycle()
        self.trading_cycle()
        self.generate_memory()  # Verificar si falta la de ayer
        
        # Loop principal
        while self.running and not self._shutdown_event.is_set():
            schedule.run_pending()
            time.sleep(1)
        
        self.stop()
    
    def generate_memory(self):
        """Genera memoria del día anterior si no existe"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        existing = self.storage.get_memory_by_date(yesterday)
        
        if not existing:
            logger.info(f"🧠 Generando memoria faltante para {yesterday}...")
            self.memory_agent.execute({"date": yesterday})
        else:
            logger.debug(f"🧠 Memoria para {yesterday} ya existe.")
    
    def _reset_daily_counters(self):
        """Reset contador diario de trades a medianoche"""
        logger.info("🔄 Reseteando conatadores diarios...")
        self.daily_trades = 0
        self.last_trade_time = {}
        logger.info(f"✅ Contador de trades reseteado (máx: {self.max_daily_trades})")

    def stop(self):
        """Detiene el orquestador"""
        logger.info("")
        logger.info("🛑 Deteniendo sistema...")
        self.running = False
        self._shutdown_event.set()
        
        # Desconectar MT5
        if self.mt5:
            self.mt5.disconnect()
        
        logger.info("✅ Sistema detenido correctamente")
    
    def handle_signal(self, signum, frame):
        """Maneja señales de sistema (Ctrl+C)"""
        logger.info("\n⚠️ Señal de interrupción recibida")
        self.stop()


def main():
    """Función principal coordinada"""
    config = load_unified_config()
    trading_mode = config.get('trading_mode', 'normal')
    
    logger.info(f"🎮 Modo de trading seleccionado: {trading_mode.upper()}")
    
    instance = None
    mt5 = None
    
    try:
        if trading_mode == 'scalping':
            from scalping.orchestrator import ScalpingOrchestrator
            from mt5.connector import MT5Connector
            from mt5.order_agent import OrderAgent
            from scraping.storage import get_storage
            
            mt5 = MT5Connector()
            if not mt5.connect():
                logger.error("No se pudo conectar a MT5 para modo Scalping")
                return
                
            order_agent = OrderAgent()
            storage = get_storage()
            
            instance = ScalpingOrchestrator(
                mt5_connector=mt5,
                order_agent=order_agent,
                storage=storage,
                config=config
            )
        else:
            instance = TradingOrchestrator(config=config)
            mt5 = instance.mt5
        
        # Manejar señales de forma unificada
        def handle_exit(signum, frame):
            logger.info("\n⚠️ Señal de interrupción recibida")
            if instance:
                instance.stop()
            if mt5 and hasattr(mt5, 'disconnect'):
                mt5.disconnect()
            sys.exit(0)
            
        signal.signal(signal.SIGINT, handle_exit)
        signal.signal(signal.SIGTERM, handle_exit)
        
        # Iniciar ejecución
        instance.start()
        
    except KeyboardInterrupt:
        if instance: instance.stop()
    except Exception as e:
        logger.critical(f"💥 Error fatal en el sistema: {e}", exc_info=True)
        if instance: instance.stop()
    finally:
        if mt5 and hasattr(mt5, 'disconnect'):
            mt5.disconnect()


if __name__ == "__main__":
    main()
