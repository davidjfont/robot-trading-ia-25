"""
Risk Agent - Agente de gestión de riesgo
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from loguru import logger
import yaml
import os

from .base_agent import BaseAgent, AgentResult
from scraping.storage import get_storage


@dataclass
class RiskAssessment:
    """Evaluación de riesgo para una operación"""
    approved: bool
    max_volume: float
    recommended_sl: float  # en pips
    recommended_tp: float  # en pips
    risk_score: float  # 0-1 donde 1 es máximo riesgo
    reasons: List[str]


class RiskAgent(BaseAgent):
    """
    Agente de control de riesgo que valida operaciones antes de ejecutarlas.
    
    Controles:
    - Límite de pérdida diaria
    - Tamaño máximo de posición
    - Número máximo de operaciones abiertas
    - Stop Loss y Take Profit automáticos
    - Evaluación de volatilidad
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        super().__init__("RiskAgent")
        self.config = self._load_config(config_path)
        self.storage = get_storage()
        
        # Configuración de riesgo
        risk_config = self.config.get("risk", {})
        self.max_daily_loss_pct = risk_config.get("max_daily_loss_percent", 2.0)
        self.max_position_size = risk_config.get("max_position_size", 0.1)
        self.max_open_positions = risk_config.get("max_open_positions", 3)
        self.default_sl_pips = risk_config.get("default_sl_pips", 50)
        self.default_tp_pips = risk_config.get("default_tp_pips", 100)
        self.risk_per_trade_pct = risk_config.get("risk_per_trade_percent", 1.0)
        
        # Estado interno
        self._daily_loss = 0.0
        self._daily_reset_date = datetime.now().date()
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Carga configuración"""
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            full_path = os.path.join(base_dir, config_path)
            
            with open(full_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception:
            return {}
    
    def execute(self, data: Any) -> AgentResult:
        """
        Evalúa una operación propuesta
        
        Args:
            data: Dict con detalles de la operación propuesta
                - symbol: Par de divisas
                - type: BUY/SELL
                - volume: Volumen propuesto
                - signal_strength: Fuerza de la señal (0-1)
                - balance: Balance actual de la cuenta
                - open_positions: Número de posiciones abiertas
        """
        if not data:
            return AgentResult(
                agent_name=self.name,
                success=False,
                error="No se proporcionaron datos de operación"
            )
        
        try:
            assessment = self.assess_trade(
                symbol=data.get("symbol"),
                trade_type=data.get("type"),
                proposed_volume=data.get("volume", 0.1),
                signal_strength=data.get("signal_strength", 0.5),
                balance=data.get("balance", 10000),
                open_positions=data.get("open_positions", 0)
            )
            
            return AgentResult(
                agent_name=self.name,
                success=True,
                data={
                    "approved": assessment.approved,
                    "max_volume": assessment.max_volume,
                    "recommended_sl": assessment.recommended_sl,
                    "recommended_tp": assessment.recommended_tp,
                    "risk_score": assessment.risk_score,
                    "reasons": assessment.reasons
                }
            )
            
        except Exception as e:
            logger.error(f"Error en RiskAgent: {e}")
            return AgentResult(
                agent_name=self.name,
                success=False,
                error=str(e)
            )
    
    def assess_trade(
        self,
        symbol: str,
        trade_type: str,
        proposed_volume: float,
        signal_strength: float,
        balance: float,
        open_positions: int
    ) -> RiskAssessment:
        """
        Evalúa si una operación cumple con los criterios de riesgo
        """
        reasons = []
        risk_score = 0.0
        approved = True
        
        # 1. Verificar número de posiciones abiertas
        if open_positions >= self.max_open_positions:
            approved = False
            reasons.append(f"Máximo de posiciones abiertas alcanzado ({self.max_open_positions})")
            risk_score += 0.3
        
        # 2. Verificar pérdida diaria
        self._check_daily_reset()
        daily_loss_pct = (self._daily_loss / balance) * 100 if balance > 0 else 0
        
        if daily_loss_pct >= self.max_daily_loss_pct:
            approved = False
            reasons.append(f"Límite de pérdida diaria alcanzado ({daily_loss_pct:.1f}%)")
            risk_score += 0.4
        
        # 3. Calcular volumen adecuado basado en riesgo
        max_risk_amount = balance * (self.risk_per_trade_pct / 100)
        sl_pips = self.default_sl_pips
        
        # Valor aproximado del pip (simplificado)
        pip_value = 10 if "JPY" not in symbol else 0.1
        max_volume_by_risk = max_risk_amount / (sl_pips * pip_value)
        
        # Ajustar por fuerza de señal
        signal_factor = 0.5 + (signal_strength * 0.5)  # Entre 0.5 y 1.0
        adjusted_volume = min(
            proposed_volume,
            max_volume_by_risk * signal_factor,
            self.max_position_size
        )
        adjusted_volume = round(max(adjusted_volume, 0.01), 2)
        
        if adjusted_volume < proposed_volume:
            reasons.append(f"Volumen reducido de {proposed_volume} a {adjusted_volume}")
        
        # 4. Ajustar SL/TP por fuerza de señal
        # Señales fuertes permiten TP más ambiciosos
        tp_multiplier = 1.5 + (signal_strength * 0.5)  # Entre 1.5 y 2.0
        recommended_tp = self.default_tp_pips * tp_multiplier
        
        # SL más ajustado para señales débiles
        sl_multiplier = 1.0 - (signal_strength * 0.2)  # Entre 0.8 y 1.0
        recommended_sl = self.default_sl_pips * sl_multiplier
        
        # 5. Evaluar riesgo por estadísticas históricas
        stats = self.storage.get_trade_stats(days=30)
        recent_win_rate = stats.get("win_rate", 0.5)
        
        if recent_win_rate < 0.4:
            risk_score += 0.2
            reasons.append(f"Win rate reciente bajo ({recent_win_rate:.1%})")
            # Reducir volumen si hay mala racha
            adjusted_volume = adjusted_volume * 0.7
        
        # 6. Señal muy débil
        if signal_strength < 0.3:
            risk_score += 0.2
            reasons.append(f"Señal débil ({signal_strength:.2f})")
            if signal_strength < 0.2:
                approved = False
                reasons.append("Señal demasiado débil para operar")
        
        # Normalizar risk_score
        risk_score = min(risk_score, 1.0)
        
        if not reasons:
            reasons.append("Operación dentro de parámetros de riesgo")
        
        return RiskAssessment(
            approved=approved,
            max_volume=adjusted_volume,
            recommended_sl=round(recommended_sl, 1),
            recommended_tp=round(recommended_tp, 1),
            risk_score=round(risk_score, 2),
            reasons=reasons
        )
    
    def _check_daily_reset(self):
        """Resetea contadores diarios si cambió el día"""
        today = datetime.now().date()
        if today != self._daily_reset_date:
            self._daily_loss = 0.0
            self._daily_reset_date = today
            logger.info("Contadores diarios de riesgo reseteados")
    
    def record_loss(self, amount: float):
        """Registra una pérdida para el control diario"""
        self._check_daily_reset()
        if amount > 0:
            self._daily_loss += amount
            logger.info(f"Pérdida registrada: {amount}. Total diario: {self._daily_loss}")
    
    def record_profit(self, amount: float):
        """Registra una ganancia (reduce la pérdida diaria)"""
        self._check_daily_reset()
        if amount > 0:
            self._daily_loss = max(0, self._daily_loss - amount)
    
    def get_daily_status(self, balance: float) -> Dict[str, Any]:
        """Obtiene estado de riesgo diario"""
        self._check_daily_reset()
        loss_pct = (self._daily_loss / balance) * 100 if balance > 0 else 0
        remaining = self.max_daily_loss_pct - loss_pct
        
        return {
            "daily_loss": self._daily_loss,
            "daily_loss_pct": round(loss_pct, 2),
            "max_allowed_pct": self.max_daily_loss_pct,
            "remaining_risk_pct": round(max(remaining, 0), 2),
            "can_trade": loss_pct < self.max_daily_loss_pct,
            "date": self._daily_reset_date.isoformat()
        }
    
    def calculate_position_size(
        self,
        balance: float,
        risk_pct: float,
        sl_pips: float,
        symbol: str
    ) -> float:
        """
        Calcula el tamaño de posición óptimo basado en riesgo
        
        Args:
            balance: Balance de la cuenta
            risk_pct: Porcentaje de riesgo por trade
            sl_pips: Stop loss en pips
            symbol: Par de divisas
        
        Returns:
            Volumen en lotes
        """
        risk_amount = balance * (risk_pct / 100)
        
        # Valor del pip por lote (aproximado)
        pip_value = 10 if "JPY" not in symbol else 1000 / 100  # Simplificado
        
        volume = risk_amount / (sl_pips * pip_value)
        volume = round(min(volume, self.max_position_size), 2)
        volume = max(volume, 0.01)
        
        return volume


if __name__ == "__main__":
    print("=" * 50)
    print("Test de RiskAgent")
    print("=" * 50)
    
    agent = RiskAgent()
    
    # Test evaluación de trade
    print("\n--- Evaluación de operación ---")
    result = agent.run({
        "symbol": "EURUSD",
        "type": "BUY",
        "volume": 0.1,
        "signal_strength": 0.75,
        "balance": 1000,
        "open_positions": 1
    })
    
    print(f"\nAprobado: {'✅' if result.data['approved'] else '❌'}")
    print(f"Volumen máximo: {result.data['max_volume']} lotes")
    print(f"SL recomendado: {result.data['recommended_sl']} pips")
    print(f"TP recomendado: {result.data['recommended_tp']} pips")
    print(f"Risk Score: {result.data['risk_score']}")
    print("Razones:")
    for reason in result.data['reasons']:
        print(f"  • {reason}")
    
    # Test estado diario
    print("\n--- Estado de riesgo diario ---")
    status = agent.get_daily_status(balance=1000)
    print(f"Pérdida diaria: {status['daily_loss_pct']}%")
    print(f"Riesgo restante: {status['remaining_risk_pct']}%")
    print(f"Puede operar: {'✅' if status['can_trade'] else '❌'}")
