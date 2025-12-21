"""
Base Agent - Clase abstracta base para todos los agentes del sistema
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from loguru import logger
import uuid


class AgentStatus(Enum):
    """Estados posibles de un agente"""
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class AgentResult:
    """Resultado de una ejecución de agente"""
    agent_name: str
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    execution_time_ms: float = 0.0


class BaseAgent(ABC):
    """
    Clase base abstracta para todos los agentes del sistema de trading.
    
    Cada agente tiene:
    - Un nombre único
    - Estado de ejecución
    - Logging integrado
    - Historial de resultados
    
    Uso:
        class MyAgent(BaseAgent):
            def execute(self, data):
                # Implementar lógica
                return AgentResult(...)
    """
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        """
        Inicializa el agente base
        
        Args:
            name: Nombre único del agente
            config: Configuración opcional
        """
        self.name = name
        self.id = str(uuid.uuid4())[:8]
        self.config = config or {}
        self.status = AgentStatus.IDLE
        self.created_at = datetime.now()
        self.last_run: Optional[datetime] = None
        self.run_count = 0
        self.error_count = 0
        self.results_history: list = []
        self.max_history = 100  # Máximo resultados a mantener
        
        logger.info(f"Agente {self.name} [{self.id}] inicializado")
    
    @abstractmethod
    def execute(self, data: Any) -> AgentResult:
        """
        Ejecuta la lógica principal del agente.
        Debe ser implementado por cada agente específico.
        
        Args:
            data: Datos de entrada para procesar
        
        Returns:
            AgentResult con el resultado de la ejecución
        """
        pass
    
    def run(self, data: Any) -> AgentResult:
        """
        Ejecuta el agente con manejo de errores y logging
        
        Args:
            data: Datos de entrada
        
        Returns:
            AgentResult con el resultado
        """
        start_time = datetime.now()
        self.status = AgentStatus.RUNNING
        self.last_run = start_time
        self.run_count += 1
        
        logger.info(f"[{self.name}] Iniciando ejecución #{self.run_count}")
        
        try:
            result = self.execute(data)
            result.execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            # Almacenar en historial
            self._add_to_history(result)
            
            if result.success:
                self.status = AgentStatus.IDLE
                logger.info(f"[{self.name}] Ejecución exitosa en {result.execution_time_ms:.2f}ms")
            else:
                self.status = AgentStatus.ERROR
                self.error_count += 1
                logger.warning(f"[{self.name}] Ejecución con error: {result.error}")
            
            return result
            
        except Exception as e:
            self.status = AgentStatus.ERROR
            self.error_count += 1
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            
            error_result = AgentResult(
                agent_name=self.name,
                success=False,
                error=str(e),
                execution_time_ms=execution_time
            )
            
            self._add_to_history(error_result)
            logger.error(f"[{self.name}] Excepción en ejecución: {e}")
            
            return error_result
    
    def _add_to_history(self, result: AgentResult):
        """Agrega resultado al historial, manteniendo el límite"""
        self.results_history.append(result)
        if len(self.results_history) > self.max_history:
            self.results_history = self.results_history[-self.max_history:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del agente"""
        success_count = sum(1 for r in self.results_history if r.success)
        avg_time = 0.0
        if self.results_history:
            avg_time = sum(r.execution_time_ms for r in self.results_history) / len(self.results_history)
        
        return {
            "name": self.name,
            "id": self.id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "run_count": self.run_count,
            "error_count": self.error_count,
            "success_rate": success_count / max(1, len(self.results_history)),
            "avg_execution_time_ms": avg_time,
            "history_size": len(self.results_history)
        }
    
    def stop(self):
        """Detiene el agente"""
        self.status = AgentStatus.STOPPED
        logger.info(f"[{self.name}] Agente detenido")
    
    def reset(self):
        """Reinicia estadísticas del agente"""
        self.run_count = 0
        self.error_count = 0
        self.results_history = []
        self.status = AgentStatus.IDLE
        logger.info(f"[{self.name}] Agente reiniciado")
    
    def __repr__(self):
        return f"<{self.__class__.__name__}(name={self.name}, status={self.status.value})>"
