"""
Tests for TradingAnalytics
"""

import pytest
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.analytics import TradingAnalytics, TradeResult


class TestTradingAnalytics:
    """Tests para métricas de trading"""
    
    @pytest.fixture
    def sample_trades(self):
        """Genera trades de ejemplo"""
        base_time = datetime.now() - timedelta(days=30)
        trades = []
        
        # 7 ganadores, 3 perdedores = 70% win rate
        profits = [50, 40, -30, 60, 45, -25, 55, 50, -20, 65]
        
        for i, profit in enumerate(profits):
            trades.append(TradeResult(
                ticket=10000 + i,
                symbol="EURUSD",
                order_type="BUY" if i % 2 == 0 else "SELL",
                volume=0.1,
                open_price=1.0850,
                close_price=1.0850 + (profit / 10000),
                open_time=base_time + timedelta(hours=i * 4),
                close_time=base_time + timedelta(hours=i * 4 + 2),
                profit=profit,
                pips=abs(profit),
                duration_minutes=120
            ))
        
        return trades
    
    @pytest.fixture
    def analytics(self, sample_trades):
        """Crea instancia de TradingAnalytics"""
        return TradingAnalytics(sample_trades, initial_balance=1000)
    
    def test_total_trades(self, analytics):
        """Test contador de trades"""
        assert analytics.total_trades == 10
    
    def test_win_rate(self, analytics):
        """Test win rate"""
        assert analytics.win_rate == 0.7  # 7/10
    
    def test_winning_losing_trades(self, analytics):
        """Test conteo de ganadores/perdedores"""
        assert analytics.winning_trades == 7
        assert analytics.losing_trades == 3
    
    def test_profit_calculations(self, analytics):
        """Test cálculos de profit"""
        expected_total = 50 + 40 - 30 + 60 + 45 - 25 + 55 + 50 - 20 + 65
        assert analytics.total_profit == expected_total
        assert analytics.net_profit == expected_total
    
    def test_gross_profit_loss(self, analytics):
        """Test profit/loss brutas"""
        assert analytics.gross_profit == 50 + 40 + 60 + 45 + 55 + 50 + 65  # 365
        assert analytics.gross_loss == 30 + 25 + 20  # 75
    
    def test_profit_factor(self, analytics):
        """Test profit factor"""
        # Profit factor = gross profit / gross loss
        expected_pf = 365 / 75
        assert abs(analytics.profit_factor - expected_pf) < 0.01
    
    def test_average_trades(self, analytics):
        """Test promedios"""
        assert analytics.avg_profit > 0
        assert analytics.avg_winning_trade > 0
        assert analytics.avg_losing_trade < 0
    
    def test_equity_curve(self, analytics):
        """Test curva de equity"""
        curve = analytics.equity_curve
        
        assert len(curve) == 11  # 10 trades + balance inicial
        assert curve[0] == 1000  # Balance inicial
        assert curve[-1] == 1000 + analytics.total_profit
    
    def test_max_drawdown(self, analytics):
        """Test max drawdown"""
        # Drawdown debería ser >= 0
        assert analytics.max_drawdown >= 0
        assert analytics.max_drawdown_percent >= 0
    
    def test_consecutive_streaks(self, analytics):
        """Test rachas consecutivas"""
        assert analytics.max_consecutive_wins >= 1
        assert analytics.max_consecutive_losses >= 1
    
    def test_empty_analytics(self):
        """Test analytics vacío"""
        empty = TradingAnalytics([], initial_balance=1000)
        metrics = empty.calculate_all_metrics()
        
        assert metrics['total_trades'] == 0
        assert metrics['win_rate'] == 0
        assert metrics['profit_factor'] == 0
    
    def test_to_dataframe(self, analytics):
        """Test conversión a DataFrame"""
        df = analytics.to_dataframe()
        
        assert len(df) == 10
        assert 'ticket' in df.columns
        assert 'profit' in df.columns
    
    def test_generate_report(self, analytics):
        """Test generación de reporte"""
        report = analytics.generate_report()
        
        assert "REPORTE DE TRADING" in report
        assert "Win Rate" in report
        assert "Profit Factor" in report


class TestRiskMetrics:
    """Tests para métricas de riesgo"""
    
    @pytest.fixture
    def volatile_trades(self):
        """Genera trades con alta volatilidad"""
        base_time = datetime.now() - timedelta(days=30)
        trades = []
        
        # Alternando ganancias y pérdidas grandes
        profits = [100, -50, 80, -60, 120, -40, 90, -70, 110, -30]
        
        for i, profit in enumerate(profits):
            trades.append(TradeResult(
                ticket=10000 + i,
                symbol="EURUSD",
                order_type="BUY",
                volume=0.1,
                open_price=1.0850,
                close_price=1.0850 + (profit / 10000),
                open_time=base_time + timedelta(hours=i * 4),
                close_time=base_time + timedelta(hours=i * 4 + 2),
                profit=profit,
                pips=abs(profit),
                duration_minutes=120
            ))
        
        return trades
    
    def test_sharpe_ratio_exists(self, volatile_trades):
        """Test que Sharpe Ratio se calcula"""
        analytics = TradingAnalytics(volatile_trades, initial_balance=1000)
        
        # Sharpe puede ser cualquier valor real
        sharpe = analytics.sharpe_ratio
        assert isinstance(sharpe, (int, float))
    
    def test_sortino_ratio_exists(self, volatile_trades):
        """Test que Sortino Ratio se calcula"""
        analytics = TradingAnalytics(volatile_trades, initial_balance=1000)
        
        sortino = analytics.sortino_ratio
        assert isinstance(sortino, (int, float))
    
    def test_expectancy(self, volatile_trades):
        """Test expectativa matemática"""
        analytics = TradingAnalytics(volatile_trades, initial_balance=1000)
        
        expectancy = analytics.expectancy
        # Con estos trades, expectancy debería ser positiva
        assert expectancy > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
