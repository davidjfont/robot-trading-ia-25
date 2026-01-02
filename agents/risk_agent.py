"""
Risk Agent - Agente de gestión de riesgo con REGLAS DURAS
Versión 2.0 - Production Ready
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from loguru import logger
from enum import Enum
import yaml
import os
import json

from .base_agent import BaseAgent, AgentResult
from scraping.storage import get_storage

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False


class RiskStatus(Enum):
    """Estados de riesgo"""
    NORMAL = "normal"           # Todo OK
    CAUTION = "caution"         # Precaución
    WARNING = "warning"         # Alerta
    BLOCKED = "blocked"         # Bloqueado
    EMERGENCY = "emergency"     # Emergencia


@dataclass
class RiskAssessment:
    """Evaluación de riesgo para una operación"""
    approved: bool
    max_volume: float
    recommended_sl: float  # en pips
    recommended_tp: float  # en pips
    risk_score: float  # 0-1 donde 1 es máximo riesgo
    reasons: List[str]
    status: RiskStatus = RiskStatus.NORMAL
    risk_budget_remaining: float = 1.0


@dataclass
class RiskDecision:
    """Registro de decisión de riesgo para auditoría"""
    timestamp: datetime
    action: str
    symbol: str
    approved: bool
    reasons: List[str]
    risk_score: float
    balance: float
    daily_loss: float


class RiskAgent(BaseAgent):
    """
    Agente de control de riesgo con REGLAS DURAS.
    
    REGLAS DE BLOQUEO:
    1. Pérdida diaria ≥ 2% → BLOQUEAR trading
    2. Margen libre < 30% → Solo cerrar, no abrir
    3. 3 pérdidas consecutivas → Pausa 1 hora
    4. Correlación entre pares → No duplicar dirección
    5. Drawdown > 5% → BLOQUEAR hasta revisión
    """
    
    # Correlaciones conocidas entre pares
    CORRELATIONS = {
        ("EURUSD", "GBPUSD"): 0.85,
        ("EURUSD", "USDCHF"): -0.92,
        ("GBPUSD", "USDCHF"): -0.80,
        ("AUDUSD", "NZDUSD"): 0.88,
        ("USDJPY", "EURJPY"): 0.75,
    }
    
    def __init__(self, config: Optional[Dict] = None, config_path: str = "config.yaml"):
        super().__init__("RiskAgent", config=config)
        if not config:
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
        
        # Límites DUROS
        self.max_drawdown_pct = 5.0           # Drawdown máximo
        self.min_margin_free_pct = 30.0       # Margen mínimo
        self.max_consecutive_losses = 3       # Pérdidas seguidas
        self.pause_after_losses_minutes = 60  # Pausa tras pérdidas
        self.correlation_threshold = 0.75     # Umbral correlación
        
        # Estado interno (Gobernanza)
        self._daily_loss = 0.0
        self._daily_profit = 0.0
        self._daily_reset_date = datetime.now().date()
        self._streak_count = 0  # Antes _consecutive_losses
        self._last_loss_time: Optional[datetime] = None
        self._cooldown_until: Optional[datetime] = None  # Antes _blocked_until
        self._current_status = RiskStatus.NORMAL
        self._decisions_log: List[RiskDecision] = []
        self._open_positions: Dict[str, str] = {}  # symbol: direction
        
        logger.info("RiskAgent v2.0 inicializado con reglas duras")
    
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
                - equity: Equity actual
                - margin_free: Margen libre
                - open_positions: Lista de posiciones abiertas
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
                equity=data.get("equity", 10000),
                margin_free=data.get("margin_free", 10000),
                open_positions=data.get("open_positions", [])
            )
            
            # Log de decisión
            self._log_decision(
                action="ASSESS_TRADE",
                symbol=data.get("symbol", "N/A"),
                approved=assessment.approved,
                reasons=assessment.reasons,
                risk_score=assessment.risk_score,
                balance=data.get("balance", 0),
                daily_loss=self._daily_loss
            )
            
            # Guardar en Logs de Sistema para Consola
            self.storage.save_agent_log(
                self.name,
                f"Validación {data.get('symbol')}",
                f"{'Aprobado' if assessment.approved else 'Rechazado'} (Score: {assessment.risk_score})",
                assessment.approved
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
                    "reasons": assessment.reasons,
                    "status": assessment.status.value
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
        equity: float,
        margin_free: float,
        open_positions: List[Dict] = None
    ) -> RiskAssessment:
        """
        Evalúa si una operación cumple con los criterios de riesgo DUROS
        """
        reasons = []
        risk_score = 0.0
        approved = True
        status = RiskStatus.NORMAL
        
        self._check_daily_reset()
        
        # ═══════════════════════════════════════════════════════════
        # REGLA 1: COOLDOWN / STREAK PROTECTION
        # ═══════════════════════════════════════════════════════════
        if self._is_in_cooldown():
            approved = False
            status = RiskStatus.BLOCKED
            remaining = (self._cooldown_until - datetime.now()).seconds // 60
            reasons.append(f"⏳ COOLDOWN: {remaining} min restantes (Streak Protection: {self._streak_count} pérdidas)")
            return RiskAssessment(
                approved=False,
                max_volume=0,
                recommended_sl=0,
                recommended_tp=0,
                risk_score=1.0,
                reasons=reasons,
                status=status,
                risk_budget_remaining=0.0
            )
        
        # ═══════════════════════════════════════════════════════════
        # REGLA 2: PÉRDIDA DIARIA MÁXIMA
        # ═══════════════════════════════════════════════════════════
        daily_loss_pct = (self._daily_loss / balance) * 100 if balance > 0 else 0
        
        if daily_loss_pct >= self.max_daily_loss_pct:
            approved = False
            status = RiskStatus.BLOCKED
            reasons.append(f"🛑 BLOQUEADO: Pérdida diaria {daily_loss_pct:.1f}% ≥ {self.max_daily_loss_pct}% límite")
            risk_score = 1.0
            logger.warning(f"Trading bloqueado: pérdida diaria {daily_loss_pct:.1f}%")
        elif daily_loss_pct >= self.max_daily_loss_pct * 0.75:
            status = RiskStatus.WARNING
            reasons.append(f"⚠️ ALERTA: Pérdida diaria {daily_loss_pct:.1f}% cerca del límite")
            risk_score += 0.3
        
        # ═══════════════════════════════════════════════════════════
        # REGLA 3: DRAWDOWN MÁXIMO
        # ═══════════════════════════════════════════════════════════
        drawdown_pct = ((balance - equity) / balance) * 100 if balance > 0 else 0
        
        if drawdown_pct >= self.max_drawdown_pct:
            approved = False
            status = RiskStatus.EMERGENCY
            reasons.append(f"🚨 EMERGENCIA: Drawdown {drawdown_pct:.1f}% ≥ {self.max_drawdown_pct}% máximo")
            risk_score = 1.0
            logger.error(f"EMERGENCIA: Drawdown {drawdown_pct:.1f}%")
        
        # ═══════════════════════════════════════════════════════════
        # REGLA 4: MARGEN LIBRE MÍNIMO
        # ═══════════════════════════════════════════════════════════
        margin_free_pct = (margin_free / balance) * 100 if balance > 0 else 0
        
        if margin_free_pct < self.min_margin_free_pct:
            approved = False
            status = RiskStatus.WARNING if status != RiskStatus.EMERGENCY else status
            reasons.append(f"⚠️ Margen libre {margin_free_pct:.1f}% < {self.min_margin_free_pct}% mínimo")
            risk_score += 0.4
        
        # ═══════════════════════════════════════════════════════════
        # REGLA 5: MÁXIMO DE POSICIONES
        # ═══════════════════════════════════════════════════════════
        num_positions = len(open_positions) if open_positions else 0
        
        if num_positions >= self.max_open_positions:
            approved = False
            reasons.append(f"❌ Máximo de posiciones alcanzado ({num_positions}/{self.max_open_positions})")
            risk_score += 0.3
        
        # ═══════════════════════════════════════════════════════════
        # REGLA 6: CORRELACIÓN ENTRE PARES
        # ═══════════════════════════════════════════════════════════
        if open_positions and approved:
            correlation_issue = self._check_correlation(symbol, trade_type, open_positions)
            if correlation_issue:
                approved = False
                reasons.append(correlation_issue)
                risk_score += 0.25
        
        # ═══════════════════════════════════════════════════════════
        # REGLA 7: SEÑAL MÍNIMA
        # ═══════════════════════════════════════════════════════════
        if signal_strength < 0.3:
            approved = False
            reasons.append(f"❌ Señal demasiado débil: {signal_strength:.0%} < 30% mínimo")
            risk_score += 0.2
        elif signal_strength < 0.5:
            reasons.append(f"⚠️ Señal moderada: {signal_strength:.0%}")
            risk_score += 0.1
        
        # ═══════════════════════════════════════════════════════════
        # CÁLCULO DE VOLUMEN AJUSTADO (1% Risk Rule)
        # ═══════════════════════════════════════════════════════════
        if approved:
            # Primero intentamos calcular volumen basado en riesgo real (1% rule)
            # Usamos default_sl_pips para el cálculo base de riesgo
            sl_to_use = self.default_sl_pips
            
            # calculate_position_size ahora es más inteligente y usa MT5 si está disponible
            base_risk_volume = self.calculate_position_size(
                balance=balance,
                risk_pct=self.risk_per_trade_pct,
                sl_pips=sl_to_use,
                symbol=symbol
            )
            
            # Aplicamos factores adicionales (fuerza de señal, streak, etc.) en _calculate_adjusted_volume
            adjusted_volume = self._calculate_adjusted_volume(
                symbol, base_risk_volume, signal_strength, balance, daily_loss_pct
            )
            
            if adjusted_volume < proposed_volume:
                reasons.append(f"📉 Volumen optimizado por riesgo: {proposed_volume} → {adjusted_volume}")
                
            # ═══════════════════════════════════════════════════════════
            # CÁLCULO DE SL/TP ADAPTATIVO (ATR)
            # ═══════════════════════════════════════════════════════════
            technical_data = data.get("technical_data", {}) if isinstance(data, dict) else {}
            atr = technical_data.get("atr", 0)
            
            if atr > 0:
                # Convertir ATR a pips aproximados para la interfaz
                # ATR suele estar en precio (0.00015). En pips (5 dígitos), 0.0001 = 1 pip
                point = technical_data.get("point", 0.0001) # fallback
                pips_in_atr = atr / (point * 10) if point > 0 else 0
                
                if pips_in_atr > 0:
                    rec_sl = round(pips_in_atr * 1.5, 1) # SL = 1.5 * ATR
                    rec_tp = round(pips_in_atr * 3.0, 1) # TP = 3.0 * ATR
                    reasons.append(f"📏 Adaptativo (ATR): SL {rec_sl} / TP {rec_tp} pips")
                    # Podríamos sobreescribir los valores si quisiéramos automatizarlo al 100%
        else:
            adjusted_volume = 0
        
        # ═══════════════════════════════════════════════════════════
        # CÁLCULO DE SL/TP
        # ═══════════════════════════════════════════════════════════
        tp_multiplier = 1.5 + (signal_strength * 0.5)
        sl_multiplier = 1.0 - (signal_strength * 0.2)
        
        recommended_tp = self.default_tp_pips * tp_multiplier
        recommended_sl = self.default_sl_pips * sl_multiplier
        
        # Normalizar risk_score
        risk_score = min(risk_score, 1.0)
        
        if not reasons:
            reasons.append("✅ Operación aprobada - dentro de parámetros de riesgo")
        
        # Determinar status final
        if approved:
            if risk_score > 0.5:
                status = RiskStatus.CAUTION
            else:
                status = RiskStatus.NORMAL
        
        # Factores para risk_budget_remaining
        daily_fac = max(0, 1 - (daily_loss_pct / self.max_daily_loss_pct))
        streak_fac = max(0.2, 1 - (self._streak_count * 0.25))
        
        return RiskAssessment(
            approved=approved,
            max_volume=adjusted_volume,
            recommended_sl=round(recommended_sl, 1),
            recommended_tp=round(recommended_tp, 1),
            risk_score=round(risk_score, 2),
            reasons=reasons,
            status=status,
            risk_budget_remaining=round(daily_fac * streak_fac, 2)
        )
    
    def _check_correlation(
        self, 
        new_symbol: str, 
        new_direction: str, 
        open_positions: List[Dict]
    ) -> Optional[str]:
        """Verifica si hay conflicto de correlación"""
        
        for pos in open_positions:
            existing_symbol = pos.get("symbol", "")
            existing_direction = "BUY" if pos.get("type", 0) == 0 else "SELL"
            
            # Buscar correlación
            pair = tuple(sorted([new_symbol, existing_symbol]))
            correlation = self.CORRELATIONS.get(pair, 0)
            
            if abs(correlation) >= self.correlation_threshold:
                # Correlación positiva + misma dirección = riesgo
                if correlation > 0 and new_direction == existing_direction:
                    return f"🔗 Correlación: {new_symbol} y {existing_symbol} ({correlation:.0%}) en misma dirección"
                
                # Correlación negativa + dirección opuesta = riesgo
                if correlation < 0 and new_direction != existing_direction:
                    return f"🔗 Correlación inversa: {new_symbol} y {existing_symbol} ({correlation:.0%})"
        
        return None
    
    def _calculate_adjusted_volume(
        self,
        symbol: str,
        base_volume: float,
        signal_strength: float,
        balance: float,
        daily_loss_pct: float
    ) -> float:
        """Calcula volumen final ajustado por factores emocionales/mercado"""
        
        # Factor por fuerza de señal (0.7-1.0) - No queremos reducir demasiado si la señal es OK
        signal_factor = 0.7 + (signal_strength * 0.3)
        
        # Factor por pérdida diaria (reducir si hay pérdidas acumuladas)
        daily_factor = 1.0
        if daily_loss_pct > 0:
            daily_factor = max(0.4, 1 - (daily_loss_pct / self.max_daily_loss_pct))
        
        # Factor por pérdidas consecutivas (Streak Impact) - Penaliza fuertemente rachas malas
        consecutive_factor = 1.0
        if self._streak_count > 0:
            consecutive_factor = max(0.2, 1 - (self._streak_count * 0.25))
        
        final_volume = base_volume * signal_factor * daily_factor * consecutive_factor
        
        # Ajustar a límites duros
        adjusted = min(final_volume, self.max_position_size)
        
        # Redondear a 2 decimales y asegurar mínimo 0.01 si base_volume > 0
        if base_volume > 0:
            return round(max(adjusted, 0.01), 2)
        return 0.0
    
    def _is_in_cooldown(self) -> bool:
        """Verifica si estamos en periodo de Cooldown"""
        if self._cooldown_until and datetime.now() < self._cooldown_until:
            return True
        return False
    
    def _check_daily_reset(self):
        """Resetea contadores diarios de gobernanza si cambió el día"""
        today = datetime.now().date()
        if today != self._daily_reset_date:
            self._daily_loss = 0.0
            self._daily_profit = 0.0
            self._daily_reset_date = today
            self._streak_count = 0
            self._cooldown_until = None
            logger.info("✅ Gobernanza: Límites diarios reseteados")
    
    def record_trade_result(self, profit: float, symbol: str):
        """
        Registra el resultado de una operación
        
        Args:
            profit: Resultado (positivo = ganancia, negativo = pérdida)
            symbol: Símbolo operado
        """
        self._check_daily_reset()
        
        if profit < 0:
            # Pérdida registrada en el Streak
            loss = abs(profit)
            self._daily_loss += loss
            self._streak_count += 1
            self._last_loss_time = datetime.now()
            
            logger.warning(f"📉 Streak Alert: {self._streak_count} pérdidas. Pérdida: {loss}")
            
            # Evaluar si activamos Cooldown (Streak Protection)
            if self._streak_count >= self.max_consecutive_losses:
                if self.check_market_conditions():
                    self._cooldown_until = datetime.now() + timedelta(minutes=self.pause_after_losses_minutes)
                    logger.error(f"🛡️ STREAK PROTECTION: Cooldown {self.pause_after_losses_minutes} min activado.")
                else:
                    logger.info("ℹ️ Streak Protection omitida: Mercado en régimen favorabla/bajo spread.")
        else:
            # Ganancia restablece el Streak y recupera Budget
            self._daily_profit += profit
            self._streak_count = 0 
            self._daily_loss = max(0, self._daily_loss - profit)
            
            logger.info(f"💰 Profit registrado: {profit}. Streak reseteado.")
    
    def check_market_conditions(self) -> bool:
        """
        Evalúa si el mercado justifica un Cooldown tras pérdidas.
        Retorna True si el mercado es adverso (debe pausar).
        """
        # TODO: Integrar con datos reales de spread/volatilidad
        # Por ahora, simulamos basado en el RiskAgent o pasamos parámetros externos
        return True 
    
    def record_loss(self, amount: float):
        """Alias para compatibilidad"""
        self.record_trade_result(-amount, "N/A")
    
    def record_profit(self, amount: float):
        """Alias para compatibilidad"""
        self.record_trade_result(amount, "N/A")
    
    def get_daily_status(self, balance: float) -> Dict[str, Any]:
        """Obtiene estado de gobernanza diario"""
        self._check_daily_reset()
        loss_pct = (self._daily_loss / balance) * 100 if balance > 0 else 0
        remaining_budget = self.max_daily_loss_pct - loss_pct
        
        return {
            "daily_loss": round(self._daily_loss, 2),
            "daily_profit": round(self._daily_profit, 2),
            "daily_net": round(self._daily_profit - self._daily_loss, 2),
            "daily_loss_pct": round(loss_pct, 2),
            "max_allowed_pct": self.max_daily_loss_pct,
            "risk_budget_remaining": round(max(remaining_budget / self.max_daily_loss_pct, 0), 2),
            "streak_count": self._streak_count,
            "is_in_cooldown": self._is_in_cooldown(),
            "cooldown_until": self._cooldown_until.isoformat() if self._cooldown_until else None,
            "can_trade": not self._is_in_cooldown() and loss_pct < self.max_daily_loss_pct,
            "status": self._current_status.value,
            "date": self._daily_reset_date.isoformat()
        }
    
    def get_full_status(self, balance: float, equity: float, margin_free: float) -> Dict[str, Any]:
        """Obtiene estado completo de gobernanza de riesgo"""
        daily = self.get_daily_status(balance)
        
        drawdown_pct = ((balance - equity) / balance) * 100 if balance > 0 else 0
        margin_free_pct = (margin_free / balance) * 100 if balance > 0 else 0
        
        # Determinar color/estado según Gobernanza
        if daily["is_in_cooldown"] or daily["daily_loss_pct"] >= self.max_daily_loss_pct:
            status = RiskStatus.BLOCKED
            color = "red"
        elif drawdown_pct >= self.max_drawdown_pct:
            status = RiskStatus.EMERGENCY
            color = "red"
        elif daily["daily_loss_pct"] >= self.max_daily_loss_pct * 0.75:
            status = RiskStatus.WARNING
            color = "orange"
        elif self._streak_count >= 2:
            status = RiskStatus.CAUTION
            color = "yellow"
        else:
            status = RiskStatus.NORMAL
            color = "green"
        
        return {
            **daily,
            "drawdown_pct": round(drawdown_pct, 2),
            "max_drawdown_pct": self.max_drawdown_pct,
            "margin_free_pct": round(margin_free_pct, 2),
            "min_margin_free_pct": self.min_margin_free_pct,
            "status": status.value,
            "color": color,
            "recent_decisions": self._decisions_log[-10:]  # Últimas 10 decisiones
        }
    
    def _log_decision(
        self,
        action: str,
        symbol: str,
        approved: bool,
        reasons: List[str],
        risk_score: float,
        balance: float,
        daily_loss: float
    ):
        """Registra decisión para auditoría"""
        decision = RiskDecision(
            timestamp=datetime.now(),
            action=action,
            symbol=symbol,
            approved=approved,
            reasons=reasons,
            risk_score=risk_score,
            balance=balance,
            daily_loss=daily_loss
        )
        self._decisions_log.append(decision)
        
        # Mantener solo últimas 100 decisiones
        if len(self._decisions_log) > 100:
            self._decisions_log = self._decisions_log[-100:]
        
        logger.debug(f"Decision logged: {action} {symbol} -> {'✅' if approved else '❌'}")
    
    def calculate_position_size(
        self,
        balance: float,
        risk_pct: float,
        sl_pips: float,
        symbol: str
    ) -> float:
        """
        Calcula el tamaño de posición óptimo basado en riesgo (1% rule).
        Utiliza datos reales de MT5 si están disponibles para determinar el valor del tick.
        """
        # Dinero real a arriesgar
        risk_amount = balance * (risk_pct / 100)
        
        pip_value = 0.0
        
        if MT5_AVAILABLE and mt5.terminal_info() is not None:
            try:
                # Intentamos obtener el valor real por punto del broker
                symbol_info = mt5.symbol_info(symbol)
                if symbol_info:
                    # tick_value es el profit en la moneda de la cuenta para 1 lote si el precio se mueve 1 tick
                    # tick_size es el movimiento mínimo de precio
                    # point es el movimiento mínimo de precio (suelen ser casi iguales)
                    
                    tick_value = symbol_info.trade_tick_value
                    tick_size = symbol_info.trade_tick_size
                    
                    if tick_value and tick_size:
                        # Calculamos valor de 1 pip (asumiendo 1 pip = 10 ticks en 5 dígitos)
                        # O mejor, usamos directamente la distancia en ticks
                        point = symbol_info.point
                        distancia_en_puntos = sl_pips * (0.0001 / point if "JPY" not in symbol else 0.01 / point)
                        
                        # Valor de la pérdida por lote si se mueve sl_pips
                        # (distancia / tick_size) * tick_value
                        loss_per_lot = (distancia_en_puntos * point / tick_size) * tick_value
                        
                        if loss_per_lot > 0:
                            pip_value = loss_per_lot  # Esto es el loss sumado por 1 lote completo
                            volume = risk_amount / pip_value
                            logger.debug(f"Cálculo MT5 para {symbol}: Risk=${risk_amount}, SL={sl_pips} pips, Loss/Lot=${loss_per_lot:.2f}")
                            return round(min(volume, self.max_position_size), 2)
            except Exception as e:
                logger.warning(f"Error calculando volumen con MT5: {e}. Usando fallback.")

        # FALLBACK: Cálculos genéricos si MT5 no está disponible o falla
        # Asunción: 1 lote estándar = 100,000 unidades. 1 pip EURUSD = $10. 1 pip JPY = $7-10 approx.
        if "JPY" in symbol:
            # Para JPY, 0.01 es un pip. En una cuenta USD, 1 lote = 100k. 
            # 0.01 * 100,000 = 1,000 JPY. Si USDJPY = 150, 1000 JPY = $6.66
            generic_pip_value_per_lot = 7.0 
        else:
            # Pares estándar (EURUSD, GBPUSD, etc.) 1 pip = $10 por lote
            generic_pip_value_per_lot = 10.0
            
        volume = risk_amount / (sl_pips * generic_pip_value_per_lot)
        volume = round(min(volume, self.max_position_size), 2)
        volume = max(volume, 0.01)
        
        return volume
    
    def emergency_stop(self) -> bool:
        """Activa parada de emergencia - Cooldown global 24h"""
        self._cooldown_until = datetime.now() + timedelta(hours=24)
        self._current_status = RiskStatus.EMERGENCY
        logger.critical("🚨 EMERGENCY STOP ACTIVADO - Cooldown 24h")
        return True
    
    def reset_governance(self):
        """Reset manual de gobernanza (usar con precaución)"""
        self._cooldown_until = None
        self._streak_count = 0
        self._current_status = RiskStatus.NORMAL
        logger.warning("⚠️ Gobernanza reseteada manualmente")


if __name__ == "__main__":
    print("=" * 60)
    print("Test de RiskAgent v2.0 - Reglas Duras")
    print("=" * 60)
    
    agent = RiskAgent()
    
    # Test 1: Operación normal
    print("\n--- Test 1: Operación Normal ---")
    result = agent.run({
        "symbol": "EURUSD",
        "type": "BUY",
        "volume": 0.1,
        "signal_strength": 0.75,
        "balance": 1000,
        "equity": 1000,
        "margin_free": 800,
        "open_positions": []
    })
    
    print(f"Aprobado: {'✅' if result.data['approved'] else '❌'}")
    print(f"Status: {result.data['status']}")
    print(f"Risk Score: {result.data['risk_score']}")
    for reason in result.data['reasons']:
        print(f"  • {reason}")
    
    # Test 2: Simular pérdidas consecutivas
    print("\n--- Test 2: Simular 3 Pérdidas Consecutivas ---")
    agent.record_trade_result(-20, "EURUSD")
    agent.record_trade_result(-15, "EURUSD")
    agent.record_trade_result(-25, "EURUSD")
    
    status = agent.get_daily_status(1000)
    print(f"Bloqueado: {'🚫 SÍ' if status['is_blocked'] else '✅ NO'}")
    print(f"Pérdidas consecutivas: {status['consecutive_losses']}")
    print(f"Bloqueado hasta: {status['blocked_until']}")
    
    # Test 3: Intentar operar bloqueado
    print("\n--- Test 3: Intentar Operar Bloqueado ---")
    result = agent.run({
        "symbol": "GBPUSD",
        "type": "SELL",
        "volume": 0.1,
        "signal_strength": 0.8,
        "balance": 1000,
        "equity": 940,
        "margin_free": 700,
        "open_positions": []
    })
    
    print(f"Aprobado: {'✅' if result.data['approved'] else '❌'}")
    for reason in result.data['reasons']:
        print(f"  • {reason}")
    
    print("\n✅ Tests completados")
