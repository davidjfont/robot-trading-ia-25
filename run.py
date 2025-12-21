"""
Run - Orquestador principal del sistema de trading con IA
"""

import sys
import os
import time
import signal
import threading
from datetime import datetime
from typing import Optional
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
        
        # Importar módulos
        self._import_modules()
        
        logger.info("=" * 60)
        logger.info("🚀 Sistema de Trading con IA - Iniciando...")
        logger.info("=" * 60)
    
    def _load_config(self, config_path: str) -> dict:
        """Carga configuración"""
        full_path = os.path.join(BASE_DIR, config_path)
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error cargando config: {e}")
            return {}
    
    def _import_modules(self):
        """Importa módulos del sistema"""
        try:
            from agents.llm_provider import get_llm
            from agents.news_agent import NewsAgent
            from agents.sentiment_agent import SentimentAgent
            from agents.technical_agent import TechnicalAgent
            from agents.risk_agent import RiskAgent
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
                else:
                    sent_result = {"sentiment": "neutral", "score": 0, "confidence": 0}
            else:
                sent_result = {"sentiment": "neutral", "score": 0, "confidence": 0}
            
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
                    
                    # Ejecutar orden (COMENTADO PARA SEGURIDAD)
                    # Solo descomentar cuando esté listo para operar
                    logger.info(f"  ➡️ Señal válida para {decision.action} {symbol}")
                    logger.info(f"     Volume: {risk_check.data.get('max_volume')} | SL: {risk_check.data.get('recommended_sl')} pips | TP: {risk_check.data.get('recommended_tp')} pips")
                    
                    # DESCOMENTA LAS SIGUIENTES LÍNEAS PARA OPERAR EN REAL:
                    # order_result = self.order_agent.run({
                    #     "symbol": symbol,
                    #     "type": decision.action,
                    #     "volume": risk_check.data.get("max_volume"),
                    #     "sl_pips": risk_check.data.get("recommended_sl"),
                    #     "tp_pips": risk_check.data.get("recommended_tp"),
                    #     "signal_id": signal_id
                    # })
                else:
                    reasons = risk_check.data.get("reasons", []) if risk_check.success else []
                    logger.debug(f"  ⚠️ Trade rechazado por RiskAgent: {reasons}")
            
        except Exception as e:
            logger.error(f"Error procesando {symbol}: {e}")
    
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
        
        # Scraping según configuración
        schedule.every(interval).minutes.do(self.scraping_cycle)
        
        logger.info(f"📅 Ciclo de trading: cada 1 minuto")
        logger.info(f"📅 Ciclo de scraping: cada {interval} minutos")
        logger.info("")
        logger.info("🟢 Sistema iniciado. Presiona Ctrl+C para detener.")
        logger.info("")
        
        # Ejecutar primer ciclo inmediatamente
        self.scraping_cycle()
        self.trading_cycle()
        
        # Loop principal
        while self.running and not self._shutdown_event.is_set():
            schedule.run_pending()
            time.sleep(1)
        
        self.stop()
    
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
    """Función principal"""
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
