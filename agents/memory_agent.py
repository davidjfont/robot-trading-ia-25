"""
Memory Agent - Genera resúmenes diarios de actividad
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from loguru import logger
import json

from .base_agent import BaseAgent, AgentResult
from .llm_provider import get_llm
from scraping.storage import get_storage

class MemoryAgent(BaseAgent):
    """
    Agente encargado de revisar la actividad pasada y generar 
    una "memoria" o resumen para dar contexto al sistema.
    """
    
    def __init__(self):
        super().__init__("MemoryAgent")
        self.llm = get_llm()
        self.storage = get_storage()
        
    def execute(self, data: Optional[Dict] = None) -> AgentResult:
        """
        Genera un resumen del día anterior o de una fecha específica.
        Data puede contener: "date" (YYYY-MM-DD)
        """
        target_date_str = data.get("date") if data else None
        
        if not target_date_str:
            # Por defecto, ayer
            target_date = datetime.now() - timedelta(days=1)
            target_date_str = target_date.strftime("%Y-%m-%d")
            
        logger.info(f"Generando memoria para la fecha: {target_date_str}")
        
        try:
            # 1. Recolectar datos del día
            activity_data = self._gather_activity(target_date_str)
            
            if not activity_data["trades"] and not activity_data["signals"]:
                return AgentResult(
                    agent_name=self.name,
                    success=True,
                    data={"summary": "No hubo actividad significativa en esta fecha.", "stats": activity_data["stats"]}
                )
            
            # 2. Generar resumen con LLM
            summary = self._generate_summary(target_date_str, activity_data)
            
            # 3. Guardar en DB
            self.storage.save_daily_memory(target_date_str, summary, activity_data["stats"])
            
            # Guardar log en Consola
            self.storage.save_agent_log(
                self.name,
                f"Generar Memoria {target_date_str}",
                "Resumen generado exitosamente",
                True
            )

            
            return AgentResult(
                agent_name=self.name,
                success=True,
                data={"summary": summary, "stats": activity_data["stats"]}
            )
            
        except Exception as e:
            logger.error(f"Error en MemoryAgent: {e}")
            return AgentResult(agent_name=self.name, success=False, error=str(e))

    def _gather_activity(self, date_str: str) -> Dict[str, Any]:
        """Recolecta estadísticas y eventos de la DB"""
        # Simplificado: obtener trades y señales de las últimas 24h desde esa fecha
        # En una implementación real, filtraríamos por fecha exacta en SQL
        signals = self.storage.get_recent_signals(hours=24)
        trades = self.storage.get_trade_stats(days=1)
        
        return {
            "signals": [s.id for s in signals],
            "signals_count": len(signals),
            "trades": trades.get("total_trades", 0),
            "stats": trades
        }

    def _generate_summary(self, date: str, activity: Dict) -> str:
        """Usa el LLM para crear un texto narrativo"""
        prompt = f"""
        Eres la memoria central de un sistema de trading algorítmico con IA. 
        Tu tarea es resumir la actividad del día {date}.
        
        Datos de actividad:
        - Señales generadas: {activity['signals_count']}
        - Operaciones cerradas: {activity['trades']}
        - Profit total: {activity['stats'].get('total_profit', 0)}
        - Win Rate: {activity['stats'].get('win_rate', 0):.1%}
        
        Escribe un resumen ejecutivo breve (máximo 150 palabras) en español. 
        Incluye una sección de 'Lecciones Aprendidas' o 'Observaciones' basada en los datos.
        Sé profesional y analítico.
        """
        
        if self.llm.is_available():
            response = self.llm.generate(prompt)
            # Extraer contenido si es un objeto LLMResponse
            if hasattr(response, 'content'):
                return response.content
            return str(response)
        else:
            return f"Resumen manual (LLM no disponible): {activity['signals_count']} señales y {activity['trades']} trades."

def get_memory_agent() -> MemoryAgent:
    return MemoryAgent()
