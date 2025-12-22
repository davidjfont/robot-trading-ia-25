"""
Tests for RiskAgent - Reglas Duras
"""

import pytest
import sys
import os
from datetime import datetime, timedelta

# Agregar path del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.risk_agent import RiskAgent, RiskStatus, RiskAssessment


class TestRiskAgentBasic:
    """Tests básicos del RiskAgent"""
    
    @pytest.fixture
    def agent(self):
        """Crea instancia de RiskAgent para tests"""
        return RiskAgent()
    
    def test_agent_initialization(self, agent):
        """Test que el agente se inicializa correctamente"""
        assert agent.name == "RiskAgent"
        assert agent.max_daily_loss_pct > 0
        assert agent.max_position_size > 0
        assert agent.max_open_positions > 0
    
    def test_normal_trade_approved(self, agent):
        """Test operación normal que debe ser aprobada"""
        result = agent.run({
            "symbol": "EURUSD",
            "type": "BUY",
            "volume": 0.1,
            "signal_strength": 0.75,
            "balance": 1000,
            "equity": 1000,
            "margin_free": 900,
            "open_positions": []
        })
        
        assert result.success == True
        assert result.data["approved"] == True
        assert result.data["max_volume"] > 0
        assert result.data["status"] in ["normal", "caution"]
    
    def test_weak_signal_rejected(self, agent):
        """Test que señales débiles son rechazadas"""
        result = agent.run({
            "symbol": "EURUSD",
            "type": "BUY",
            "volume": 0.1,
            "signal_strength": 0.15,  # Muy débil
            "balance": 1000,
            "equity": 1000,
            "margin_free": 900,
            "open_positions": []
        })
        
        assert result.data["approved"] == False
        assert any("débil" in reason.lower() for reason in result.data["reasons"])


class TestRiskAgentDailyLoss:
    """Tests de límite de pérdida diaria"""
    
    @pytest.fixture
    def agent(self):
        return RiskAgent()
    
    def test_daily_loss_limit_blocks_trading(self, agent):
        """Test que pérdida diaria bloquea trading"""
        # Simular pérdidas grandes
        agent._daily_loss = 25  # 2.5% de 1000
        
        result = agent.run({
            "symbol": "EURUSD",
            "type": "BUY",
            "volume": 0.1,
            "signal_strength": 0.8,
            "balance": 1000,
            "equity": 975,
            "margin_free": 900,
            "open_positions": []
        })
        
        assert result.data["approved"] == False
        assert result.data["status"] == "blocked"
    
    def test_daily_status_tracking(self, agent):
        """Test seguimiento de estado diario"""
        agent.record_trade_result(-10, "EURUSD")
        status = agent.get_daily_status(1000)
        
        assert status["daily_loss"] == 10
        assert status["consecutive_losses"] == 1
        assert status["can_trade"] == True
    
    def test_daily_reset(self, agent):
        """Test reset diario"""
        agent._daily_loss = 50
        agent._daily_reset_date = datetime.now().date() - timedelta(days=1)
        
        agent._check_daily_reset()
        
        assert agent._daily_loss == 0
        assert agent._daily_reset_date == datetime.now().date()


class TestRiskAgentConsecutiveLosses:
    """Tests de pérdidas consecutivas"""
    
    @pytest.fixture
    def agent(self):
        return RiskAgent()
    
    def test_consecutive_losses_trigger_block(self, agent):
        """Test que 3 pérdidas consecutivas bloquean"""
        agent.record_trade_result(-10, "EURUSD")
        agent.record_trade_result(-10, "EURUSD")
        agent.record_trade_result(-10, "EURUSD")
        
        assert agent._is_blocked() == True
        assert agent._consecutive_losses == 3
    
    def test_profit_resets_consecutive_losses(self, agent):
        """Test que una ganancia resetea pérdidas consecutivas"""
        agent.record_trade_result(-10, "EURUSD")
        agent.record_trade_result(-10, "EURUSD")
        assert agent._consecutive_losses == 2
        
        agent.record_trade_result(20, "EURUSD")
        assert agent._consecutive_losses == 0


class TestRiskAgentPositionLimits:
    """Tests de límites de posiciones"""
    
    @pytest.fixture
    def agent(self):
        return RiskAgent()
    
    def test_max_positions_blocks_new_trades(self, agent):
        """Test que máximo de posiciones bloquea nuevas"""
        open_positions = [
            {"symbol": "EURUSD", "type": 0},
            {"symbol": "GBPUSD", "type": 1},
            {"symbol": "USDJPY", "type": 0},
        ]
        
        result = agent.run({
            "symbol": "AUDUSD",
            "type": "BUY",
            "volume": 0.1,
            "signal_strength": 0.8,
            "balance": 1000,
            "equity": 1000,
            "margin_free": 500,
            "open_positions": open_positions
        })
        
        assert result.data["approved"] == False
        assert any("máximo" in reason.lower() for reason in result.data["reasons"])


class TestRiskAgentCorrelation:
    """Tests de correlación entre pares"""
    
    @pytest.fixture
    def agent(self):
        return RiskAgent()
    
    def test_correlated_pairs_same_direction_blocked(self, agent):
        """Test que pares correlacionados en misma dirección se bloquean"""
        open_positions = [{"symbol": "EURUSD", "type": 0}]  # BUY EURUSD
        
        result = agent.run({
            "symbol": "GBPUSD",
            "type": "BUY",  # BUY GBPUSD - alta correlación
            "volume": 0.1,
            "signal_strength": 0.8,
            "balance": 1000,
            "equity": 1000,
            "margin_free": 800,
            "open_positions": open_positions
        })
        
        # Debe ser rechazado por correlación
        assert result.data["approved"] == False
        assert any("correlación" in reason.lower() for reason in result.data["reasons"])


class TestRiskAgentMargin:
    """Tests de margen"""
    
    @pytest.fixture
    def agent(self):
        return RiskAgent()
    
    def test_low_margin_blocks_trading(self, agent):
        """Test que margen bajo bloquea trading"""
        result = agent.run({
            "symbol": "EURUSD",
            "type": "BUY",
            "volume": 0.1,
            "signal_strength": 0.8,
            "balance": 1000,
            "equity": 1000,
            "margin_free": 200,  # Solo 20% - muy bajo
            "open_positions": []
        })
        
        assert result.data["approved"] == False
        assert any("margen" in reason.lower() for reason in result.data["reasons"])


class TestRiskAgentEmergency:
    """Tests de emergencia"""
    
    @pytest.fixture
    def agent(self):
        return RiskAgent()
    
    def test_emergency_stop(self, agent):
        """Test parada de emergencia"""
        result = agent.emergency_stop()
        assert result == True
        assert agent._is_blocked() == True
    
    def test_high_drawdown_triggers_emergency(self, agent):
        """Test que drawdown alto activa emergencia"""
        result = agent.run({
            "symbol": "EURUSD",
            "type": "BUY",
            "volume": 0.1,
            "signal_strength": 0.9,
            "balance": 1000,
            "equity": 920,  # 8% drawdown
            "margin_free": 800,
            "open_positions": []
        })
        
        assert result.data["approved"] == False
        assert result.data["status"] == "emergency"


class TestRiskAgentVolumeCalculation:
    """Tests de cálculo de volumen"""
    
    @pytest.fixture
    def agent(self):
        return RiskAgent()
    
    def test_position_size_calculation(self, agent):
        """Test cálculo de tamaño de posición"""
        volume = agent.calculate_position_size(
            balance=1000,
            risk_pct=1.0,
            sl_pips=50,
            symbol="EURUSD"
        )
        
        assert volume > 0
        assert volume <= agent.max_position_size
    
    def test_volume_reduced_for_weak_signals(self, agent):
        """Test que volumen se reduce con señales débiles"""
        result_strong = agent.run({
            "symbol": "EURUSD",
            "type": "BUY",
            "volume": 0.1,
            "signal_strength": 0.9,
            "balance": 1000,
            "equity": 1000,
            "margin_free": 900,
            "open_positions": []
        })
        
        result_moderate = agent.run({
            "symbol": "GBPUSD",
            "type": "BUY",
            "volume": 0.1,
            "signal_strength": 0.4,
            "balance": 1000,
            "equity": 1000,
            "margin_free": 900,
            "open_positions": []
        })
        
        # Señal fuerte debería permitir más volumen
        assert result_strong.data["max_volume"] >= result_moderate.data["max_volume"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
