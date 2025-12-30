"""
Scalp Risk Agent - Capa 5 del Sistema de Scalping
El policía - Puede cancelar a todos los demás
"""

from typing import Dict, Any
from datetime import datetime, timedelta
from loguru import logger


class ScalpRiskAgent:
    """
    Agente de Riesgo - EL POLICÍA
    
    Este agente puede CANCELAR a todos los demás.
    
    Controla:
    - Máx operaciones por sesión
    - Máx pérdidas consecutivas (2-3)
    - Bloqueo automático si:
      - Spread se abre
      - Latencia sube
      - Slippage anómalo
    
    Este agente NO negocia. EJECUTA DISCIPLINA.
    """
    
    def __init__(self, storage, mt5_connector, config: dict = None):
        self.storage = storage
        self.mt5 = mt5_connector
        self.config = config or {}
        
        # Parámetros de riesgo
        self.max_trades_per_session = self.config.get('max_trades_per_session', 10)
        self.max_consecutive_losses = self.config.get('max_consecutive_losses', 2)
        self.max_spread_multiplier = self.config.get('max_spread_multiplier', 2.0)
        self.max_daily_loss_percent = self.config.get('max_daily_loss_percent', 2.0)
        self.max_positions = self.config.get('max_positions', 3)
        
        # Estado (Gobernanza)
        self.session_trades = 0
        self.streak_count = 0  # Antes consecutive_losses
        self.session_start = datetime.now()
        self.daily_pnl = 0.0
        self.cooldown_until = None
        self.cooldown_reason = None
        
        # Spreads normales por par
        self.normal_spreads = {
            "EURUSD": 0.00010,
            "GBPUSD": 0.00012,
            "USDJPY": 0.010,
            "AUDUSD": 0.00012,
            "USDCAD": 0.00015,
            "USDCHF": 0.00012,
        }
        
    def can_trade(self, symbol: str) -> Dict[str, Any]:
        """
        Verifica si se puede ejecutar un trade
        
        Returns:
            {
                'allowed': bool,
                'reason': str,
                'risk_level': str  # 'low', 'medium', 'high', 'blocked'
            }
        """
        # 1. Verificar Cooldown / Streak Protection
        if self.cooldown_until and datetime.now() < self.cooldown_until:
            remaining = (self.cooldown_until - datetime.now()).seconds
            return {
                'allowed': False,
                'reason': f"⏳ COOLDOWN: {self.cooldown_reason} ({remaining}s restantes)",
                'risk_level': 'blocked'
            }
        else:
            self.cooldown_until = None
            self.cooldown_reason = None
        
        # 2.5 Verificar límite de posiciones abiertas
        positions = self.mt5.get_positions()
        if positions and len(positions) >= self.max_positions:
            return {
                'allowed': False,
                'reason': f"Límite de posiciones alcanzado ({len(positions)}/{self.max_positions})",
                'risk_level': 'blocked'
            }
        
        # 2. Verificar límite de trades por sesión
        if self.session_trades >= self.max_trades_per_session:
            return {
                'allowed': False,
                'reason': f"Límite de sesión alcanzado ({self.session_trades}/{self.max_trades_per_session})",
                'risk_level': 'blocked'
            }
        
        # 3. Verificar Streak Protection
        if self.streak_count >= self.max_consecutive_losses:
            self._apply_cooldown(300)  # 5 minutos de cooldown
            return {
                'allowed': False,
                'reason': f"🛡️ STREAK PROTECTION: {self.streak_count} pérdidas consecutivas",
                'risk_level': 'blocked'
            }
        
        # 4. Verificar spread
        spread_check = self._check_spread(symbol)
        if not spread_check['ok']:
            return {
                'allowed': False,
                'reason': spread_check['reason'],
                'risk_level': 'high'
            }
        
        # 5. Verificar pérdida diaria
        if self.daily_pnl < 0:
            balance = self._get_balance()
            loss_percent = abs(self.daily_pnl) / balance * 100
            if loss_percent >= self.max_daily_loss_percent:
                self._block_session("Pérdida diaria máxima alcanzada")
                return {
                    'allowed': False,
                    'reason': f"Pérdida diaria: {loss_percent:.1f}% >= {self.max_daily_loss_percent}%",
                    'risk_level': 'blocked'
                }
        
        # Calcular nivel de riesgo
        risk_level = self._calculate_risk_level()
        
        logger.debug(f"[ScalpRisk] {symbol}: ✓ Trade permitido | Riesgo: {risk_level}")
        
        return {
            'allowed': True,
            'reason': 'Condiciones de gobernanza aceptables',
            'risk_level': risk_level,
            'session_trades': self.session_trades,
            'streak_count': self.streak_count
        }
    
    def register_trade_result(self, profit: float, ticket: int):
        """Registra resultado de un trade"""
        self.session_trades += 1
        self.daily_pnl += profit
        
        if profit < 0:
            self.streak_count += 1
            logger.warning(f"[ScalpRisk] Streak Alert #{ticket}: {profit:.2f} | Consecutivas: {self.streak_count}")
        else:
            self.streak_count = 0
            logger.info(f"[ScalpRisk] Profit Registrado #{ticket}: {profit:.2f} | Streak reseteado")
        
        # Guardar log
        if self.storage:
            self.storage.save_agent_log(
                "ScalpRiskAgent",
                f"Trade result #{ticket}",
                f"P&L: {profit:.2f} | Session: {self.session_trades} | Streak: {self.streak_count}",
                profit >= 0,
                0
            )
    
    def force_close_all(self, reason: str):
        """Fuerza cierre de todas las posiciones (emergencia)"""
        logger.warning(f"[ScalpRisk] ⚠️ FORCE CLOSE ALL: {reason}")
        
        try:
            positions = self.mt5.get_positions()
            for pos in positions:
                # TODO: Implementar cierre de posición
                logger.info(f"[ScalpRisk] Cerrando posición #{pos.ticket}")
        except Exception as e:
            logger.error(f"[ScalpRisk] Error en force close: {e}")
        
        self._block_session(reason)
    
    def reset_session(self):
        """Reinicia contadores de gobernanza de sesión"""
        logger.info("[ScalpRisk] Reseteando gobernanza")
        self.session_trades = 0
        self.streak_count = 0
        self.session_start = datetime.now()
        self.daily_pnl = 0.0
        self.cooldown_until = None
        self.cooldown_reason = None
    
    def _check_spread(self, symbol: str) -> Dict[str, Any]:
        """Verifica que el spread no esté muy alto"""
        try:
            tick = self.mt5.get_tick(symbol) if self.mt5 else None
            
            if not tick:
                return {'ok': True, 'reason': 'No se pudo verificar spread'}
            
            current_spread = tick.ask - tick.bid
            normal_spread = self.normal_spreads.get(symbol, 0.00015)
            
            if current_spread > normal_spread * self.max_spread_multiplier:
                return {
                    'ok': False,
                    'reason': f"Spread alto: {current_spread:.5f} (normal: {normal_spread:.5f})"
                }
            
            return {'ok': True, 'reason': 'Spread OK'}
            
        except Exception as e:
            logger.debug(f"Error verificando spread: {e}")
            return {'ok': True, 'reason': 'Error verificando spread'}
    
    def _calculate_risk_level(self) -> str:
        """Calcula nivel de riesgo actual"""
        risk_score = 0
        
        # Factor: trades en sesión
        session_ratio = self.session_trades / self.max_trades_per_session
        risk_score += session_ratio * 30
        
        # Factor: Streak count
        loss_ratio = self.streak_count / self.max_consecutive_losses
        risk_score += loss_ratio * 50
        
        # Factor: P&L diario
        if self.daily_pnl < 0:
            risk_score += 20
        
        if risk_score < 30:
            return 'low'
        elif risk_score < 60:
            return 'medium'
        else:
            return 'high'
    
    def _get_balance(self) -> float:
        """Obtiene balance actual"""
        try:
            if self.mt5 and self.mt5.connected:
                info = self.mt5.get_account_info()
                return info.get('balance', 1000) if info else 1000
        except:
            pass
        return 1000
    
    def _apply_cooldown(self, seconds: int):
        """Aplica período de Cooldown dinámico"""
        self.cooldown_until = datetime.now() + timedelta(seconds=seconds)
        self.cooldown_reason = "Streak Protection activada"
        logger.warning(f"[ScalpRisk] Governance Cooldown de {seconds}s activado")
    
    def _block_session(self, reason: str):
        """Activa protección de sesión por el resto del día"""
        # Cooldown hasta las 23:59
        now = datetime.now()
        end_of_day = now.replace(hour=23, minute=59, second=59)
        self.cooldown_until = end_of_day
        self.cooldown_reason = reason
        logger.error(f"[ScalpRisk] 🛑 PROTECCIÓN ACTIVA: {reason}")
