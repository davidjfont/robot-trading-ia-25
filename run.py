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


class TradingOrchestrator:
    """
    Orquestador principal del sistema de trading.
    
    Coordina todos los agentes y módulos para ejecutar el ciclo de trading.
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """Inicializa el orquestador"""
        self.config = self._load_config(config_path)
        self.running = False
        self._shutdown_event = threading.Event()
        
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
    
    def _load_config(self, config_path: str) -> dict:
        """Carga configuración base y mezcla con la persistente del usuario"""
        import json
        full_path = os.path.join(BASE_DIR, config_path)
        config = {}
        
        # 1. Cargar config base (YAML)
        try:
            if os.path.exists(full_path):
                with open(full_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error cargando config YAML: {e}")
            
        # 2. Cargar config persistente de usuario (JSON)
        user_config_path = os.path.join(BASE_DIR, 'data', 'user_config.json')
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
                        config['risk']['max_open_positions'] = user_config['max_positions']
                    
                    # Actualizar modo de trading en el config interno
                    if 'trading_mode' in user_config:
                        config['trading_mode'] = user_config['trading_mode']
                        
                    logger.info("✅ Configuración persistente cargada desde user_config.json")
        except Exception as e:
            logger.warning(f"No se pudo cargar user_config.json (usando defaults): {e}")
            
        return config
    
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
        """Ejecuta un ciclo completo de trading"""
        if self._shutdown_event.is_set():
            return
        
        logger.info("-" * 40)
        logger.info(f"📊 Ciclo de trading - {datetime.now().strftime('%H:%M:%S')}")
        
        try:
            symbols = [s['symbol'] for s in self.config.get('symbols', []) if s.get('enabled', True)]
            
            for symbol in symbols:
                self._process_symbol(symbol)
            
        except Exception as e:
            logger.error(f"Error en ciclo de trading: {e}")
    
    def _process_symbol(self, symbol: str):
        """Procesa un símbolo específico"""
        logger.debug(f"Procesando {symbol}...")
        
        try:
            # 1. Obtener datos técnicos de MT5
            if self.mt5.connected:
                timeframe = self.config.get('strategy', {}).get('timeframe', 'M15')
                rates = self.mt5.get_rates(symbol, timeframe, 100)
                
                if rates is not None and len(rates) > 0:
                    # 2. Análisis técnico
                    tech_result = self.technical_agent.analyze_symbol(rates, symbol)
                else:
                    tech_result = {"combined_signal": "HOLD", "combined_score": 0}
            else:
                tech_result = {"combined_signal": "HOLD", "combined_score": 0}
            
            # 3. Análisis de sentimiento (si hay LLM)
            if self.llm.is_available():
                # Obtener noticias recientes de la base de datos
                news_list = self.storage.get_recent_news(hours=24, processed=True)
                news_texts = [n.title for n in news_list[:5]]
                
                if news_texts:
                    sent_result = self.sentiment_agent.analyze_for_symbol(news_texts, symbol)
                    self.storage.save_agent_log("SentimentAgent", f"Análisis {symbol}", 
                        f"sentiment={sent_result.get('sentiment', 'neutral')}", True, 0)
                else:
                    sent_result = {"sentiment": "neutral", "score": 0, "confidence": 0}
                    self.storage.save_agent_log("SentimentAgent", f"Sin noticias {symbol}", 
                        "No hay noticias para analizar", True, 0)
            else:
                sent_result = {"sentiment": "neutral", "score": 0, "confidence": 0}
                self.storage.save_agent_log("SentimentAgent", "LLM no disponible", 
                    "Ollama no está corriendo", False, 0)
            
            # 4. Datos de noticias del NewsAgent
            news_result = self.news_agent.get_market_sentiment(symbol[:3])
            
            # 5. Generar decisión combinada
            decision = self.combiner.make_decision(
                symbol=symbol,
                technical_result=tech_result,
                sentiment_result=sent_result,
                news_result=news_result
            )
            
            logger.info(f"  {symbol}: {decision.action} (confianza: {decision.confidence:.0%})")
            
            # 6. Si hay señal de trading...
            if decision.action in ["BUY", "SELL"] and decision.confidence > 0.5:
                # Verificar con RiskAgent
                risk_check = self.risk_agent.run({
                    "symbol": symbol,
                    "type": decision.action,
                    "volume": 0.01,
                    "signal_strength": decision.confidence,
                    "balance": self._get_balance(),
                    "open_positions": len(self.order_agent.get_open_positions())
                })
                
                if risk_check.success and risk_check.data.get("approved"):
                    # Guardar señal
                    if decision.signal:
                        signal_id = self.storage.save_signal(decision.signal.to_dict())
                    else:
                        signal_id = None
                    
                    # Log de señal válida
                    logger.info(f"  ➡️ Señal válida para {decision.action} {symbol}")
                    logger.info(f"     Volume: {risk_check.data.get('max_volume')} | SL: {risk_check.data.get('recommended_sl')} pips | TP: {risk_check.data.get('recommended_tp')} pips")
                    
                    self.storage.save_agent_log("RiskAgent", f"Aprobado {decision.action} {symbol}",
                        f"Vol:{risk_check.data.get('max_volume')} SL:{risk_check.data.get('recommended_sl')}", True, 0)
                    
                    # Ejecutar según modo
                    self._execute_trade(
                        symbol=symbol,
                        action=decision.action,
                        volume=risk_check.data.get("max_volume", 0.01),
                        sl_pips=risk_check.data.get("recommended_sl", 50),
                        tp_pips=risk_check.data.get("recommended_tp", 100),
                        signal_id=signal_id
                    )
                else:
                    reasons = risk_check.data.get("reasons", []) if risk_check.success else []
                    logger.debug(f"  ⚠️ Trade rechazado por RiskAgent: {reasons}")
                    self.storage.save_agent_log("RiskAgent", f"Rechazado {decision.action} {symbol}",
                        f"Razones: {', '.join(reasons) if reasons else 'No aprobado'}", True, 0)
            else:
                # No hay señal fuerte - registrar que RiskAgent está listo
                if decision.action == "HOLD":
                    self.storage.save_agent_log("RiskAgent", f"Sin señal {symbol}",
                        f"Esperando señales (HOLD)", True, 0)
            
        except Exception as e:
            logger.error(f"Error procesando {symbol}: {e}")
    
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
            
            # Configuración de trailing
            trailing_activation_pips = 30  # Activar trailing después de 30 pips
            trailing_distance_pips = 25    # Mantener 25 pips de distancia
            breakeven_activation_pips = 20 # Break-even después de 20 pips
            breakeven_buffer_pips = 2      # Buffer sobre entrada para BE
            
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
        logger.info("🔄 Reseteando contadores diarios...")
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


def load_unified_config():
    """Carga la configuración mezclando YAML y JSON persistente"""
    # Crear una instancia temporal solo para cargar config
    orch = TradingOrchestrator()
    return orch.config

def main():
    """Función principal"""
    
    # Cargar configuración unificada (YAML + Persistencia)
    config = load_unified_config()
    trading_mode = config.get('trading_mode', 'normal')
    
    logger.info(f"🎮 Modo de trading seleccionado: {trading_mode.upper()}")
    
    if trading_mode == 'scalping':
        # Modo Scalping - 6 capas de IA
        logger.info("⚡ Iniciando modo SCALPING...")
        
        from scalping.orchestrator import ScalpingOrchestrator
        from mt5.connector import MT5Connector
        from mt5.order_agent import OrderAgent
        from scraping.storage import get_storage
        
        # Inicializar componentes
        mt5 = MT5Connector()
        mt5.connect()
        
        order_agent = OrderAgent()
        storage = get_storage()
        
        # Crear orquestador de scalping
        scalping = ScalpingOrchestrator(
            mt5_connector=mt5,
            order_agent=order_agent,
            storage=storage,
            config=config
        )
        
        # Manejar señales
        def handle_signal(signum, frame):
            logger.info("\n⚠️ Señal de interrupción recibida")
            scalping.stop()
            mt5.disconnect()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
        
        try:
            scalping.start()
        except KeyboardInterrupt:
            scalping.stop()
            mt5.disconnect()
        except Exception as e:
            logger.error(f"Error fatal en scalping: {e}")
            scalping.stop()
            mt5.disconnect()
    
    else:
        # Modo Normal
        orchestrator = TradingOrchestrator()
        
        # Manejar Ctrl+C
        signal.signal(signal.SIGINT, orchestrator.handle_signal)
        signal.signal(signal.SIGTERM, orchestrator.handle_signal)
        
        try:
            orchestrator.start()
        except KeyboardInterrupt:
            orchestrator.stop()
        except Exception as e:
            logger.error(f"Error fatal: {e}")
            orchestrator.stop()


if __name__ == "__main__":
    main()
