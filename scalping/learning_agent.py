"""
Learning Agent - Capa 6 del Sistema de Scalping
Aprende de cada trade para mejorar
"""

from typing import Dict, Any, List
from datetime import datetime
from loguru import logger
import json


class LearningAgent:
    """
    Agente de Aprendizaje
    
    Después de cada trade analiza:
    - ¿Entrada por impulso o por ruido?
    - ¿SL justo o mal colocado?
    - ¿Hora rentable o tóxica?
    
    Aprende patrones temporales, no setups bonitos.
    """
    
    def __init__(self, storage, config: dict = None):
        self.storage = storage
        self.config = config or {}
        
        # Policy Bandit (Light Learning)
        from .policy_bandit import PolicyBandit
        self.bandit = PolicyBandit()
        
        # Estadísticas por hora
        self.hourly_stats = {h: {'wins': 0, 'losses': 0, 'total_pnl': 0} for h in range(24)}
        
        # Estadísticas por tipo de entrada
        self.entry_type_stats = {
            'velocity': {'wins': 0, 'losses': 0},
            'rejection': {'wins': 0, 'losses': 0},
            'absorption': {'wins': 0, 'losses': 0},
            'intention': {'wins': 0, 'losses': 0}
        }
        
        # Patrones detectados
        self.patterns = []
        
        # Cargar datos históricos si existen
        self._load_historical_data()
    
    def analyze_trade(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analiza un trade después de cerrar
        
        Args:
            trade_data: {
                'ticket': int,
                'symbol': str,
                'direction': str,
                'entry_type': str,  # 'velocity', 'rejection', 'absorption', 'intention'
                'entry_time': datetime,  
                'exit_time': datetime,
                'entry_price': float,
                'exit_price': float,
                'profit': float,
                'sl_hit': bool,
                'tp_hit': bool,
                'timeout': bool,
                'context': dict  # Estado del mercado al entrar
            }
            
        Returns:
            {
                'analysis': str,
                'learnings': list,
                'recommendations': list
            }
        """
        learnings = []
        recommendations = []
        
        profit = trade_data.get('profit', 0)
        is_win = profit > 0
        entry_hour = trade_data.get('entry_time', datetime.now()).hour
        entry_type = trade_data.get('entry_type', 'unknown')
        duration = (trade_data.get('exit_time', datetime.now()) - 
                   trade_data.get('entry_time', datetime.now())).total_seconds()
        
        # 1. Actualizar estadísticas por hora
        self._update_hourly_stats(entry_hour, is_win, profit)
        
        # 2. Actualizar estadísticas por tipo de entrada
        if entry_type in self.entry_type_stats:
            if is_win:
                self.entry_type_stats[entry_type]['wins'] += 1
            else:
                self.entry_type_stats[entry_type]['losses'] += 1
        
        # 3. Analizar entrada
        entry_analysis = self._analyze_entry_quality(trade_data)
        if entry_analysis:
            learnings.append(entry_analysis)
        
        # 4. Analizar SL
        sl_analysis = self._analyze_stop_loss(trade_data)
        if sl_analysis:
            learnings.append(sl_analysis)
        
        # 5. Verificar hora tóxica
        if self._is_toxic_hour(entry_hour):
            learnings.append(f"Hora {entry_hour}:00 identificada como tóxica (win rate < 40%)")
            recommendations.append(f"Evitar trades entre {entry_hour}:00-{entry_hour}:59")
        
        # 6. Verificar patrón temporal
        pattern = self._detect_temporal_pattern(entry_hour, trade_data.get('symbol', ''))
        if pattern:
            self.patterns.append(pattern)
            learnings.append(f"Patrón detectado: {pattern['description']}")
        
        # 7. Análisis de duración
        if duration < 10 and not is_win:
            learnings.append("Trade cerrado muy rápido en pérdida - posible ruido")
            recommendations.append("Aumentar distancia de SL o esperar mejor setup")
        elif duration > 90 and not is_win:
            learnings.append("Trade prolongado en pérdida - señal de directionalidad incorrecta")
        
        # Generar resumen
        analysis = self._generate_analysis_summary(trade_data, learnings)
        
        # Guardar aprendizaje
        self._save_learning(trade_data, learnings, recommendations)
        
        logger.info(f"[LearningAgent] Trade #{trade_data.get('ticket')}: {len(learnings)} aprendizajes")
        
        return {
            'analysis': analysis,
            'learnings': learnings,
            'recommendations': recommendations,
            'hourly_stats': self.hourly_stats[entry_hour],
            'entry_type_stats': self.entry_type_stats.get(entry_type, {})
        }
    
    def get_recommendations(self) -> List[str]:
        """Obtiene recomendaciones basadas en datos históricos"""
        recommendations = []
        
        # Recomendar mejores horas
        best_hours = self._get_best_hours()
        if best_hours:
            recommendations.append(f"Mejores horas para scalping: {best_hours}")
        
        # Recomendar peores horas
        worst_hours = self._get_worst_hours()
        if worst_hours:
            recommendations.append(f"Evitar estas horas: {worst_hours}")
        
        # Recomendar mejor tipo de entrada
        best_entry = self._get_best_entry_type()
        if best_entry:
            recommendations.append(f"Tipo de entrada más efectivo: {best_entry}")
        
        return recommendations
    
    def get_trading_profile(self) -> Dict[str, Any]:
        """Genera perfil de trading basado en historial"""
        return {
            'hourly_performance': self.hourly_stats,
            'entry_type_performance': self.entry_type_stats,
            'patterns': self.patterns[-10:],  # Últimos 10 patrones
            'recommendations': self.get_recommendations()
        }
    
    def _update_hourly_stats(self, hour: int, is_win: bool, profit: float):
        """Actualiza estadísticas por hora"""
        if is_win:
            self.hourly_stats[hour]['wins'] += 1
        else:
            self.hourly_stats[hour]['losses'] += 1
        self.hourly_stats[hour]['total_pnl'] += profit
    
    def _analyze_entry_quality(self, trade_data: Dict) -> str:
        """Analiza calidad de la entrada"""
        profit = trade_data.get('profit', 0)
        sl_hit = trade_data.get('sl_hit', False)
        
        if sl_hit and profit < -1:  # Pérdida significativa
            context = trade_data.get('context', {})
            market_state = context.get('market_state', 'unknown')
            
            if market_state == 'chaotic':
                return "Entrada en mercado caótico - filtro de contexto debería haber bloqueado"
            elif market_state == 'ranging':
                return "Entrada en rango - considerar solo trades de reversión"
        
        return ""
    
    def _analyze_stop_loss(self, trade_data: Dict) -> str:
        """Analiza si el SL estaba bien colocado"""
        sl_hit = trade_data.get('sl_hit', False)
        profit = trade_data.get('profit', 0)
        
        if sl_hit:
            # TODO: Comparar con movimiento post-SL
            return "SL activado - verificar si precio continuó en dirección o revirtió"
        
        return ""
    
    def _is_toxic_hour(self, hour: int) -> bool:
        """Determina si una hora es tóxica"""
        stats = self.hourly_stats[hour]
        total = stats['wins'] + stats['losses']
        
        if total < 5:  # No suficientes datos
            return False
        
        win_rate = stats['wins'] / total
        return win_rate < 0.4
    
    def _detect_temporal_pattern(self, hour: int, symbol: str) -> Dict:
        """Detecta patrones temporales"""
        # Simplificado - en producción sería más sofisticado
        stats = self.hourly_stats[hour]
        total = stats['wins'] + stats['losses']
        
        if total >= 10:
            win_rate = stats['wins'] / total
            avg_pnl = stats['total_pnl'] / total
            
            if win_rate >= 0.7:
                return {
                    'hour': hour,
                    'symbol': symbol,
                    'type': 'positive',
                    'description': f"Hora {hour}:00 es consistentemente rentable ({win_rate:.0%})",
                    'detected_at': datetime.now().isoformat()
                }
            elif win_rate <= 0.3:
                return {
                    'hour': hour,
                    'symbol': symbol,
                    'type': 'negative',
                    'description': f"Hora {hour}:00 es consistentemente pérdida ({win_rate:.0%})",
                    'detected_at': datetime.now().isoformat()
                }
        
        return None
    
    def _get_best_hours(self) -> str:
        """Retorna las mejores horas para tradear"""
        good_hours = []
        
        for hour, stats in self.hourly_stats.items():
            total = stats['wins'] + stats['losses']
            if total >= 5:
                win_rate = stats['wins'] / total
                if win_rate >= 0.6:
                    good_hours.append(f"{hour}:00")
        
        return ", ".join(good_hours) if good_hours else ""
    
    def _get_worst_hours(self) -> str:
        """Retorna las peores horas para tradear"""
        bad_hours = []
        
        for hour, stats in self.hourly_stats.items():
            total = stats['wins'] + stats['losses']
            if total >= 5:
                win_rate = stats['wins'] / total
                if win_rate <= 0.4:
                    bad_hours.append(f"{hour}:00")
        
        return ", ".join(bad_hours) if bad_hours else ""
    
    def _get_best_entry_type(self) -> str:
        """Retorna el mejor tipo de entrada"""
        best_type = None
        best_rate = 0
        
        for entry_type, stats in self.entry_type_stats.items():
            total = stats['wins'] + stats['losses']
            if total >= 5:
                win_rate = stats['wins'] / total
                if win_rate > best_rate:
                    best_rate = win_rate
                    best_type = entry_type
        
        return f"{best_type} ({best_rate:.0%})" if best_type else ""
    
    def _generate_analysis_summary(self, trade_data: Dict, learnings: List) -> str:
        """Genera resumen del análisis"""
        profit = trade_data.get('profit', 0)
        result = "✅ Ganancia" if profit > 0 else "❌ Pérdida"
        
        summary = f"{result}: ${profit:.2f}"
        if learnings:
            summary += f" | {len(learnings)} insights"
        
        return summary
    
    def _save_learning(self, trade_data: Dict, learnings: List, recommendations: List):
        """Guarda aprendizaje en storage"""
        if self.storage:
            try:
                self.storage.save_agent_log(
                    "LearningAgent",
                    f"Análisis #{trade_data.get('ticket', 'N/A')}",
                    f"Learnings: {len(learnings)} | Recs: {len(recommendations)}",
                    trade_data.get('profit', 0) > 0,
                    0
                )
            except:
                pass
    
    def _load_historical_data(self):
        """Carga datos históricos de aprendizaje"""
        # TODO: Implementar carga desde base de datos
        pass

    def register_trade_result(self, trade_data: Dict[str, Any], preset_used: str):
        """Registra el resultado en el bandit"""
        profit = trade_data.get('profit', 0)
        sl_pips = trade_data.get('sl_pips', 1.0) # Evitar division por cero
        
        # R-Multiple aproximado (Profit / Riesgo inicial)
        # En una fase más avanzada usaríamos el R exacto del risk agent
        r_multiple = profit / (sl_pips * 10) if sl_pips > 0 else 0
        
        self.bandit.update_stats(
            symbol=trade_data.get('symbol', 'UNK'),
            preset_name=preset_used,
            r_multiple=r_multiple
        )
