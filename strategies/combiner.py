"""
Combiner - Sistema de decisión multi-agente para trading
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
from loguru import logger
import sys
import os

# Agregar directorio padre al path para imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.signals import SignalGenerator, TradingSignal, SignalType


@dataclass
class AgentVote:
    """Voto de un agente en la decisión"""
    agent_name: str
    vote: str  # BUY/SELL/HOLD
    confidence: float  # 0-1
    reason: str


@dataclass
class TradingDecision:
    """Decisión final de trading multi-agente"""
    symbol: str
    action: str  # BUY/SELL/HOLD
    confidence: float
    unanimous: bool
    votes: List[AgentVote]
    signal: Optional[TradingSignal]
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "confidence": self.confidence,
            "unanimous": self.unanimous,
            "votes": [
                {"agent": v.agent_name, "vote": v.vote, "confidence": v.confidence, "reason": v.reason}
                for v in self.votes
            ],
            "signal": self.signal.to_dict() if self.signal else None,
            "timestamp": self.timestamp.isoformat()
        }


class MultiAgentCombiner:
    """
    Sistema de decisión que combina las opiniones de múltiples agentes
    para tomar decisiones de trading más robustas.
    
    Reglas de votación:
    1. Consenso: Todos los agentes deben estar de acuerdo
    2. Mayoría: 2/3 de los agentes deben estar de acuerdo
    3. Ponderado: Votos pesados por confianza de cada agente
    """
    
    def __init__(self, voting_mode: str = "weighted"):
        """
        Args:
            voting_mode: Modo de votación ('consensus', 'majority', 'weighted')
        """
        self.voting_mode = voting_mode
        self.signal_generator = SignalGenerator()
        
        # Pesos de confianza por defecto para cada agente
        self.agent_weights = {
            "TechnicalAgent": 0.4,
            "SentimentAgent": 0.3,
            "NewsAgent": 0.2,
            "RiskAgent": 0.1  # El RiskAgent no vota, solo filtra
        }
        
        logger.info(f"MultiAgentCombiner inicializado. Modo: {voting_mode}")
    
    def collect_votes(
        self,
        technical_result: Dict[str, Any],
        sentiment_result: Dict[str, Any],
        news_result: Dict[str, Any]
    ) -> List[AgentVote]:
        """Recolecta votos de cada agente"""
        votes = []
        
        # Voto del TechnicalAgent
        if technical_result:
            tech_signal = technical_result.get("combined_signal", "HOLD")
            tech_score = abs(technical_result.get("combined_score", 0))
            votes.append(AgentVote(
                agent_name="TechnicalAgent",
                vote=tech_signal,
                confidence=min(tech_score, 1.0),
                reason=f"Trend: {technical_result.get('trend', 'neutral')}"
            ))
        
        # Voto del SentimentAgent
        if sentiment_result:
            sent = sentiment_result.get("sentiment", "neutral")
            if sent == "bullish":
                sent_vote = "BUY"
            elif sent == "bearish":
                sent_vote = "SELL"
            else:
                sent_vote = "HOLD"
            
            votes.append(AgentVote(
                agent_name="SentimentAgent",
                vote=sent_vote,
                confidence=sentiment_result.get("confidence", 0.5),
                reason=f"Score: {sentiment_result.get('score', 0):.2f}"
            ))
        
        # Voto del NewsAgent
        if news_result:
            news_sent = news_result.get("sentiment", "neutral")
            if news_sent == "bullish":
                news_vote = "BUY"
            elif news_sent == "bearish":
                news_vote = "SELL"
            else:
                news_vote = "HOLD"
            
            votes.append(AgentVote(
                agent_name="NewsAgent",
                vote=news_vote,
                confidence=news_result.get("confidence", 0.5),
                reason=f"Noticias: {news_result.get('news_count', 0)}"
            ))
        
        return votes
    
    def make_decision(
        self,
        symbol: str,
        technical_result: Dict[str, Any],
        sentiment_result: Dict[str, Any],
        news_result: Dict[str, Any],
        risk_result: Optional[Dict[str, Any]] = None
    ) -> TradingDecision:
        """
        Toma una decisión de trading basada en múltiples agentes
        
        Returns:
            TradingDecision con la decisión final
        """
        # Recolectar votos
        votes = self.collect_votes(technical_result, sentiment_result, news_result)
        
        if not votes:
            return TradingDecision(
                symbol=symbol,
                action="HOLD",
                confidence=0.0,
                unanimous=True,
                votes=[],
                signal=None,
                timestamp=datetime.now()
            )
        
        # Generar señal
        signal = self.signal_generator.generate_signal(
            symbol,
            technical_result or {},
            sentiment_result or {},
            news_result or {}
        )
        
        # Decidir según modo de votación
        if self.voting_mode == "consensus":
            decision = self._consensus_decision(votes)
        elif self.voting_mode == "majority":
            decision = self._majority_decision(votes)
        else:  # weighted
            decision = self._weighted_decision(votes, signal)
        
        # Aplicar filtro de riesgo si está disponible
        if risk_result and not risk_result.get("approved", True):
            decision["action"] = "HOLD"
            decision["reasons"] = risk_result.get("reasons", [])
        
        return TradingDecision(
            symbol=symbol,
            action=decision["action"],
            confidence=decision["confidence"],
            unanimous=decision["unanimous"],
            votes=votes,
            signal=signal,
            timestamp=datetime.now()
        )
    
    def _consensus_decision(self, votes: List[AgentVote]) -> Dict[str, Any]:
        """Decisión por consenso (todos deben estar de acuerdo)"""
        unique_votes = set(v.vote for v in votes if v.vote != "HOLD")
        
        if len(unique_votes) == 1:
            # Consenso alcanzado
            action = list(unique_votes)[0]
            avg_confidence = sum(v.confidence for v in votes) / len(votes)
            return {
                "action": action,
                "confidence": avg_confidence,
                "unanimous": True
            }
        else:
            # Sin consenso
            return {
                "action": "HOLD",
                "confidence": 0.3,
                "unanimous": False
            }
    
    def _majority_decision(self, votes: List[AgentVote]) -> Dict[str, Any]:
        """Decisión por mayoría (2/3 deben estar de acuerdo)"""
        vote_counts = {"BUY": 0, "SELL": 0, "HOLD": 0}
        confidence_sums = {"BUY": 0, "SELL": 0, "HOLD": 0}
        
        for v in votes:
            vote_counts[v.vote] += 1
            confidence_sums[v.vote] += v.confidence
        
        threshold = len(votes) * 2 / 3
        
        for action in ["BUY", "SELL"]:
            if vote_counts[action] >= threshold:
                avg_conf = confidence_sums[action] / vote_counts[action] if vote_counts[action] > 0 else 0
                return {
                    "action": action,
                    "confidence": avg_conf,
                    "unanimous": vote_counts[action] == len(votes)
                }
        
        return {
            "action": "HOLD",
            "confidence": 0.3,
            "unanimous": False
        }
    
    def _weighted_decision(self, votes: List[AgentVote], signal: TradingSignal) -> Dict[str, Any]:
        """Decisión ponderada por peso y confianza de cada agente"""
        weighted_score = 0.0
        total_weight = 0.0
        
        for v in votes:
            weight = self.agent_weights.get(v.agent_name, 0.33)
            
            if v.vote == "BUY":
                vote_score = v.confidence
            elif v.vote == "SELL":
                vote_score = -v.confidence
            else:
                vote_score = 0
            
            weighted_score += vote_score * weight
            total_weight += weight
        
        final_score = weighted_score / total_weight if total_weight > 0 else 0
        
        # Usar threshold de la señal
        threshold = self.signal_generator.signal_threshold
        
        if final_score >= threshold:
            action = "BUY"
        elif final_score <= -threshold:
            action = "SELL"
        else:
            action = "HOLD"
        
        return {
            "action": action,
            "confidence": abs(final_score),
            "unanimous": all(v.vote == action for v in votes)
        }


if __name__ == "__main__":
    print("=" * 50)
    print("Test de MultiAgentCombiner")
    print("=" * 50)
    
    combiner = MultiAgentCombiner(voting_mode="weighted")
    
    # Datos de prueba - Escenario alcista
    technical = {
        "combined_signal": "BUY",
        "combined_score": 0.65,
        "trend": "bullish"
    }
    
    sentiment = {
        "sentiment": "bullish",
        "score": 0.4,
        "confidence": 0.7
    }
    
    news = {
        "sentiment": "neutral",
        "score": 0.1,
        "confidence": 0.5,
        "news_count": 3
    }
    
    decision = combiner.make_decision(
        symbol="EURUSD",
        technical_result=technical,
        sentiment_result=sentiment,
        news_result=news
    )
    
    print(f"\n🎯 Decisión para {decision.symbol}")
    print(f"   Acción: {decision.action}")
    print(f"   Confianza: {decision.confidence:.0%}")
    print(f"   Unánime: {'✅' if decision.unanimous else '❌'}")
    print(f"\n   Votos:")
    for vote in decision.votes:
        print(f"     - {vote.agent_name}: {vote.vote} ({vote.confidence:.0%}) - {vote.reason}")
    
    if decision.signal:
        print(f"\n   Señal combinada: {decision.signal.combined_score:.3f}")
