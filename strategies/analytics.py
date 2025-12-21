"""
Analytics - Métricas profesionales de trading
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from loguru import logger


@dataclass
class TradeResult:
    """Resultado de una operación"""
    ticket: int
    symbol: str
    order_type: str  # BUY or SELL
    volume: float
    open_price: float
    close_price: float
    open_time: datetime
    close_time: datetime
    profit: float
    pips: float
    duration_minutes: int


class TradingAnalytics:
    """Clase para calcular métricas profesionales de trading"""
    
    def __init__(self, trades: List[TradeResult] = None, initial_balance: float = 1000.0):
        self.trades = trades or []
        self.initial_balance = initial_balance
        self._equity_curve = None
    
    def add_trade(self, trade: TradeResult):
        """Añade un trade al historial"""
        self.trades.append(trade)
        self._equity_curve = None  # Invalidar cache
    
    def calculate_all_metrics(self) -> Dict[str, Any]:
        """Calcula todas las métricas de trading"""
        if not self.trades:
            return self._empty_metrics()
        
        return {
            # Métricas básicas
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': self.win_rate,
            
            # Profit
            'total_profit': self.total_profit,
            'gross_profit': self.gross_profit,
            'gross_loss': self.gross_loss,
            'net_profit': self.net_profit,
            'net_profit_pct': self.net_profit_percent,
            
            # Promedios
            'avg_profit': self.avg_profit,
            'avg_winning_trade': self.avg_winning_trade,
            'avg_losing_trade': self.avg_losing_trade,
            
            # Ratios profesionales
            'profit_factor': self.profit_factor,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'calmar_ratio': self.calmar_ratio,
            
            # Drawdown
            'max_drawdown': self.max_drawdown,
            'max_drawdown_pct': self.max_drawdown_percent,
            'max_drawdown_duration': self.max_drawdown_duration,
            
            # Expectativa
            'expectancy': self.expectancy,
            'expectancy_pips': self.expectancy_pips,
            'risk_reward_ratio': self.risk_reward_ratio,
            
            # Rachas
            'max_consecutive_wins': self.max_consecutive_wins,
            'max_consecutive_losses': self.max_consecutive_losses,
            
            # Recovery
            'recovery_factor': self.recovery_factor,
            
            # Tiempo
            'avg_trade_duration': self.avg_trade_duration,
            'total_trading_days': self.total_trading_days
        }
    
    @property
    def total_trades(self) -> int:
        return len(self.trades)
    
    @property
    def winning_trades(self) -> int:
        return len([t for t in self.trades if t.profit > 0])
    
    @property
    def losing_trades(self) -> int:
        return len([t for t in self.trades if t.profit < 0])
    
    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades
    
    @property
    def total_profit(self) -> float:
        return sum(t.profit for t in self.trades)
    
    @property
    def net_profit(self) -> float:
        return self.total_profit
    
    @property
    def net_profit_percent(self) -> float:
        if self.initial_balance == 0:
            return 0.0
        return (self.net_profit / self.initial_balance) * 100
    
    @property
    def gross_profit(self) -> float:
        return sum(t.profit for t in self.trades if t.profit > 0)
    
    @property
    def gross_loss(self) -> float:
        return abs(sum(t.profit for t in self.trades if t.profit < 0))
    
    @property
    def avg_profit(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.total_profit / self.total_trades
    
    @property
    def avg_winning_trade(self) -> float:
        winners = [t.profit for t in self.trades if t.profit > 0]
        if not winners:
            return 0.0
        return sum(winners) / len(winners)
    
    @property
    def avg_losing_trade(self) -> float:
        losers = [t.profit for t in self.trades if t.profit < 0]
        if not losers:
            return 0.0
        return sum(losers) / len(losers)
    
    @property
    def profit_factor(self) -> float:
        """Ratio de beneficio bruto / pérdida bruta"""
        if self.gross_loss == 0:
            return float('inf') if self.gross_profit > 0 else 0.0
        return self.gross_profit / self.gross_loss
    
    @property
    def equity_curve(self) -> List[float]:
        """Curva de equity"""
        if self._equity_curve is not None:
            return self._equity_curve
        
        curve = [self.initial_balance]
        for trade in sorted(self.trades, key=lambda x: x.close_time):
            curve.append(curve[-1] + trade.profit)
        
        self._equity_curve = curve
        return curve
    
    @property
    def returns(self) -> List[float]:
        """Retornos de cada operación"""
        curve = self.equity_curve
        if len(curve) < 2:
            return []
        return [(curve[i] - curve[i-1]) / curve[i-1] for i in range(1, len(curve))]
    
    @property
    def sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
        """Sharpe Ratio anualizado"""
        returns = self.returns
        if not returns or len(returns) < 2:
            return 0.0
        
        avg_return = np.mean(returns)
        std_return = np.std(returns)
        
        if std_return == 0:
            return 0.0
        
        # Asumiendo ~252 días de trading al año
        excess_return = avg_return - (risk_free_rate / 252)
        return (excess_return / std_return) * np.sqrt(252)
    
    @property
    def sortino_ratio(self, risk_free_rate: float = 0.02) -> float:
        """Sortino Ratio (solo considera volatilidad negativa)"""
        returns = self.returns
        if not returns:
            return 0.0
        
        avg_return = np.mean(returns)
        negative_returns = [r for r in returns if r < 0]
        
        if not negative_returns:
            return float('inf') if avg_return > 0 else 0.0
        
        downside_std = np.std(negative_returns)
        
        if downside_std == 0:
            return 0.0
        
        excess_return = avg_return - (risk_free_rate / 252)
        return (excess_return / downside_std) * np.sqrt(252)
    
    @property
    def max_drawdown(self) -> float:
        """Máximo drawdown en valor absoluto"""
        curve = self.equity_curve
        if len(curve) < 2:
            return 0.0
        
        peak = curve[0]
        max_dd = 0.0
        
        for value in curve:
            if value > peak:
                peak = value
            dd = peak - value
            if dd > max_dd:
                max_dd = dd
        
        return max_dd
    
    @property
    def max_drawdown_percent(self) -> float:
        """Máximo drawdown en porcentaje"""
        curve = self.equity_curve
        if len(curve) < 2:
            return 0.0
        
        peak = curve[0]
        max_dd_pct = 0.0
        
        for value in curve:
            if value > peak:
                peak = value
            if peak > 0:
                dd_pct = (peak - value) / peak * 100
                if dd_pct > max_dd_pct:
                    max_dd_pct = dd_pct
        
        return max_dd_pct
    
    @property
    def max_drawdown_duration(self) -> int:
        """Duración máxima del drawdown en días"""
        curve = self.equity_curve
        if len(curve) < 2:
            return 0
        
        peak = curve[0]
        peak_idx = 0
        max_duration = 0
        
        for i, value in enumerate(curve):
            if value > peak:
                duration = i - peak_idx
                if duration > max_duration:
                    max_duration = duration
                peak = value
                peak_idx = i
        
        return max_duration
    
    @property
    def calmar_ratio(self) -> float:
        """Calmar Ratio = CAGR / Max Drawdown"""
        if self.max_drawdown_percent == 0:
            return 0.0
        
        # CAGR simplificado
        if self.total_trading_days == 0:
            return 0.0
        
        annual_return = self.net_profit_percent * (365 / max(self.total_trading_days, 1))
        return annual_return / self.max_drawdown_percent
    
    @property
    def expectancy(self) -> float:
        """Expectativa matemática por operación"""
        if self.total_trades == 0:
            return 0.0
        
        return (self.win_rate * self.avg_winning_trade) + ((1 - self.win_rate) * self.avg_losing_trade)
    
    @property
    def expectancy_pips(self) -> float:
        """Expectativa en pips"""
        if self.total_trades == 0:
            return 0.0
        
        avg_win_pips = np.mean([t.pips for t in self.trades if t.profit > 0]) if self.winning_trades > 0 else 0
        avg_loss_pips = np.mean([t.pips for t in self.trades if t.profit < 0]) if self.losing_trades > 0 else 0
        
        return (self.win_rate * avg_win_pips) + ((1 - self.win_rate) * avg_loss_pips)
    
    @property
    def risk_reward_ratio(self) -> float:
        """Ratio riesgo/recompensa promedio"""
        if self.avg_losing_trade == 0:
            return 0.0
        return abs(self.avg_winning_trade / self.avg_losing_trade)
    
    @property
    def max_consecutive_wins(self) -> int:
        """Máxima racha ganadora"""
        return self._max_consecutive(lambda t: t.profit > 0)
    
    @property
    def max_consecutive_losses(self) -> int:
        """Máxima racha perdedora"""
        return self._max_consecutive(lambda t: t.profit < 0)
    
    def _max_consecutive(self, condition) -> int:
        """Calcula máximo consecutivo según condición"""
        max_streak = 0
        current_streak = 0
        
        for trade in sorted(self.trades, key=lambda x: x.close_time):
            if condition(trade):
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        
        return max_streak
    
    @property
    def recovery_factor(self) -> float:
        """Factor de recuperación = Net Profit / Max Drawdown"""
        if self.max_drawdown == 0:
            return 0.0
        return self.net_profit / self.max_drawdown
    
    @property
    def avg_trade_duration(self) -> float:
        """Duración promedio de operaciones en minutos"""
        if not self.trades:
            return 0.0
        return np.mean([t.duration_minutes for t in self.trades])
    
    @property
    def total_trading_days(self) -> int:
        """Total de días de trading"""
        if not self.trades:
            return 0
        
        dates = set(t.close_time.date() for t in self.trades)
        return len(dates)
    
    def _empty_metrics(self) -> Dict[str, Any]:
        """Retorna métricas vacías"""
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'total_profit': 0.0,
            'gross_profit': 0.0,
            'gross_loss': 0.0,
            'net_profit': 0.0,
            'net_profit_pct': 0.0,
            'avg_profit': 0.0,
            'avg_winning_trade': 0.0,
            'avg_losing_trade': 0.0,
            'profit_factor': 0.0,
            'sharpe_ratio': 0.0,
            'sortino_ratio': 0.0,
            'calmar_ratio': 0.0,
            'max_drawdown': 0.0,
            'max_drawdown_pct': 0.0,
            'max_drawdown_duration': 0,
            'expectancy': 0.0,
            'expectancy_pips': 0.0,
            'risk_reward_ratio': 0.0,
            'max_consecutive_wins': 0,
            'max_consecutive_losses': 0,
            'recovery_factor': 0.0,
            'avg_trade_duration': 0.0,
            'total_trading_days': 0
        }
    
    def to_dataframe(self) -> pd.DataFrame:
        """Convierte trades a DataFrame"""
        if not self.trades:
            return pd.DataFrame()
        
        return pd.DataFrame([{
            'ticket': t.ticket,
            'symbol': t.symbol,
            'type': t.order_type,
            'volume': t.volume,
            'open_price': t.open_price,
            'close_price': t.close_price,
            'open_time': t.open_time,
            'close_time': t.close_time,
            'profit': t.profit,
            'pips': t.pips,
            'duration_min': t.duration_minutes
        } for t in self.trades])
    
    def generate_report(self) -> str:
        """Genera reporte en texto"""
        metrics = self.calculate_all_metrics()
        
        report = f"""
═══════════════════════════════════════════════════════════
                    REPORTE DE TRADING
═══════════════════════════════════════════════════════════

📊 RESUMEN GENERAL
───────────────────────────────────────────────────────────
Total de operaciones: {metrics['total_trades']}
Operaciones ganadoras: {metrics['winning_trades']}
Operaciones perdedoras: {metrics['losing_trades']}
Win Rate: {metrics['win_rate']*100:.2f}%

💰 RESULTADOS
───────────────────────────────────────────────────────────
Profit Total: €{metrics['total_profit']:.2f}
Profit Neto: €{metrics['net_profit']:.2f} ({metrics['net_profit_pct']:.2f}%)
Profit Promedio: €{metrics['avg_profit']:.2f}
Media Ganadora: €{metrics['avg_winning_trade']:.2f}
Media Perdedora: €{metrics['avg_losing_trade']:.2f}

📈 RATIOS PROFESIONALES
───────────────────────────────────────────────────────────
Profit Factor: {metrics['profit_factor']:.3f}
Sharpe Ratio: {metrics['sharpe_ratio']:.3f}
Sortino Ratio: {metrics['sortino_ratio']:.3f}
Calmar Ratio: {metrics['calmar_ratio']:.3f}
Risk/Reward: {metrics['risk_reward_ratio']:.2f}

📉 RIESGO
───────────────────────────────────────────────────────────
Max Drawdown: €{metrics['max_drawdown']:.2f} ({metrics['max_drawdown_pct']:.2f}%)
Duración Max DD: {metrics['max_drawdown_duration']} operaciones
Recovery Factor: {metrics['recovery_factor']:.3f}

🎯 EXPECTATIVA
───────────────────────────────────────────────────────────
Expectativa/Operación: €{metrics['expectancy']:.2f}
Expectativa (pips): {metrics['expectancy_pips']:.1f}

🔥 RACHAS
───────────────────────────────────────────────────────────
Máx rachas ganadoras: {metrics['max_consecutive_wins']}
Máx rachas perdedoras: {metrics['max_consecutive_losses']}

⏱️ TIEMPO
───────────────────────────────────────────────────────────
Duración promedio: {metrics['avg_trade_duration']:.0f} min
Días de trading: {metrics['total_trading_days']}

═══════════════════════════════════════════════════════════
        Generado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
═══════════════════════════════════════════════════════════
        """
        
        return report


# Test standalone
if __name__ == "__main__":
    from datetime import datetime, timedelta
    import random
    
    # Generar trades de ejemplo
    trades = []
    base_time = datetime.now() - timedelta(days=30)
    
    for i in range(50):
        is_winner = random.random() > 0.4
        profit = random.uniform(20, 80) if is_winner else random.uniform(-50, -20)
        
        trades.append(TradeResult(
            ticket=10000 + i,
            symbol="EURUSD",
            order_type="BUY" if random.random() > 0.5 else "SELL",
            volume=0.1,
            open_price=1.0850,
            close_price=1.0850 + (profit / 10000),
            open_time=base_time + timedelta(hours=i * 4),
            close_time=base_time + timedelta(hours=i * 4 + 2),
            profit=profit,
            pips=abs(profit) / 10,
            duration_minutes=random.randint(30, 240)
        ))
    
    analytics = TradingAnalytics(trades, initial_balance=1000)
    print(analytics.generate_report())
