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
        
        # Estado
        self.running = False
        self._shutdown_event = threading.Event()
        self.cycle_interval = scalp_config.get('cycle_interval_seconds', 10)
        self.symbols = self.config.get('trading', {}).get('symbols', ['EURUSD', 'GBPUSD'])
        
        # Estadísticas de sesión
        self.session_stats = {
            'trades_executed': 0,
            'trades_blocked': 0,
            'signals_detected': 0,
            'context_blocks': 0,
            'risk_blocks': 0,
            'technical_rejects': 0
        }
        
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
                
                # Obtener posiciones actuales una vez por ciclo
                positions = self.order_agent.get_open_positions()
                symbols_with_positions = {p.get('symbol') for p in positions} if positions else set()
                
                # AUTO-MAINTAIN: Asegurar al menos una posición por símbolo seleccionado
                for symbol in self.symbols:
                    if symbol not in symbols_with_positions:
                        logger.info(f"🤖 SCALPING AUTO-FIX: Forzando posición mínima en {symbol}")
                        # Usar dirección técnica o aleatoria para la entrada forzada
                        self._force_open_scalp(symbol)
                
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
        """Abre una posición de scalping forzada si no hay ninguna"""
        import random
        
        # Obtener datos rápidos para dirección
        rates = self._get_rates(symbol, "M1", 5)
        if rates and len(rates) >= 2:
            direction = "BUY" if rates[-1]['close'] > rates[0]['close'] else "SELL"
        else:
            direction = random.choice(["BUY", "SELL"])
            
        logger.info(f"⚡ Forzando entrada de scalping: {direction} {symbol}")
        
        # Ejecutar vía Execution Agent con confianza media para parámetros estándar
        self.execution_agent.execute(
            symbol=symbol,
            direction=direction,
            entry_type="MARKET",
            confidence=0.75
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
        rates_m15 = self._get_rates(symbol, "M15", 50)
        
        context = self.context_agent.analyze(symbol, rates_m5, rates_m15)
        
        if not context['can_trade']:
            self.session_stats['context_blocks'] += 1
            logger.debug(f"[Scalp] {symbol}: Contexto NO favorable - {context['reasons']}")
            self._log_decision(symbol, "CONTEXT_BLOCK", context['reasons'])
            return
        
        # ═══════════════════════════════════════════════════════════
        # CAPA 2: MICROESTRUCTURA - ¿Hay señal?
        # ═══════════════════════════════════════════════════════════
        rates_m1 = self._get_rates(symbol, "M1", 20)
        
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
                'consecutive_losses': self.risk_agent.consecutive_losses,
                'daily_pnl': self.risk_agent.daily_pnl,
                'blocked': self.risk_agent.blocked_until is not None
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
