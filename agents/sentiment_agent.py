"""
Sentiment Agent - Agente especializado en análisis de sentimiento con LLM
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger

from .base_agent import BaseAgent, AgentResult
from .llm_provider import get_llm


class SentimentAgent(BaseAgent):
    """
    Agente que analiza sentimiento de textos usando LLM local.
    
    Funciones:
    - Análisis de sentimiento de noticias/tweets
    - Extracción de eventos económicos
    - Scoring de impacto en mercado
    """
    
    def __init__(self):
        super().__init__("SentimentAgent")
        self.llm = get_llm()
        self._cache = {}  # Cache simple para evitar reprocesar
    
    def execute(self, data: Any) -> AgentResult:
        """
        Analiza el sentimiento de uno o más textos
        
        Args:
            data: Dict con "texts" (lista de textos) o "text" (string único)
        """
        if not data:
            return AgentResult(
                agent_name=self.name,
                success=False,
                error="No se proporcionaron datos para analizar"
            )
        
        if not self.llm.is_available():
            return AgentResult(
                agent_name=self.name,
                success=False,
                error="LLM no disponible. Ejecute: ollama pull mistral"
            )
        
        try:
            # Normalizar entrada
            texts = data.get("texts", [])
            if not texts and "text" in data:
                texts = [data["text"]]
            
            context = data.get("context", "forex")
            
            results = []
            for text in texts:
                # Verificar cache
                cache_key = hash(text[:100])
                if cache_key in self._cache:
                    results.append(self._cache[cache_key])
                    continue
                
                # Analizar con LLM
                # Truncar texto si es muy largo para evitar errores de contexto/truncamiento
                max_chars = 300
                safe_text = text[:max_chars] + ("..." if len(text) > max_chars else "")
                
                analysis = self.llm.analyze_sentiment(safe_text, context)
                results.append(analysis)
                
                # Guardar en cache
                self._cache[cache_key] = analysis
            
            # Calcular sentimiento agregado
            if results:
                avg_score = sum(r.get("score", 0) for r in results) / len(results)
                if avg_score > 0.3:
                    overall = "bullish"
                elif avg_score < -0.3:
                    overall = "bearish"
                else:
                    overall = "neutral"
            else:
                avg_score = 0
                overall = "neutral"
            
            return AgentResult(
                agent_name=self.name,
                success=True,
                data={
                    "results": results,
                    "count": len(results),
                    "overall_sentiment": overall,
                    "average_score": round(avg_score, 3)
                }
            )
            
        except Exception as e:
            logger.error(f"Error en SentimentAgent: {e}")
            return AgentResult(
                agent_name=self.name,
                success=False,
                error=str(e)
            )
    
    def analyze_single(self, text: str, context: str = "forex") -> Dict[str, Any]:
        """Analiza un texto único y retorna resultado directo"""
        if not self.llm.is_available():
            return {
                "sentiment": "neutral",
                "score": 0.0,
                "impact": "low",
                "error": "LLM no disponible"
            }
        
        return self.llm.analyze_sentiment(text, context)
    
    def analyze_for_symbol(self, texts: List[str], symbol: str) -> Dict[str, Any]:
        """
        Analiza textos enfocándose en un símbolo específico
        
        Args:
            texts: Lista de textos (noticias, tweets)
            symbol: Par de divisas (ej: "EURUSD")
        
        Returns:
            Análisis agregado para el símbolo
        """
        base_currency = symbol[:3].upper()
        quote_currency = symbol[3:6].upper() if len(symbol) >= 6 else ""
        
        # Filtrar textos relevantes al símbolo
        relevant = []
        aliases = [base_currency, symbol.upper()]
        
        # Diccionario de alias comunes por moneda para mejorar filtrado
        currency_aliases = {
            "EUR": ["EURO", "EUROZONE", "BCE", "ECB"],
            "USD": ["DOLLAR", "FED", "FOMC", "TREASURY"],
            "GBP": ["POUND", "STERLING", "BOE"],
            "JPY": ["YEN", "BOJ"],
            "GOLD": ["XAU", "ORO"],
            "OIL": ["WTI", "BRENT", "CRUDO"]
        }
        
        if base_currency in currency_aliases:
            aliases.extend(currency_aliases[base_currency])
        if quote_currency in currency_aliases:
            aliases.extend(currency_aliases[quote_currency])
            
        for text in texts:
            text_u = text.upper()
            if any(alias in text_u for alias in aliases):
                relevant.append(text)
        
        if not relevant:
            return {
                "symbol": symbol,
                "sentiment": "neutral",
                "score": 0.0,
                "confidence": 0.0,
                "relevant_news": 0
            }
        
        # Analizar textos relevantes
        result = self.run({"texts": relevant_texts, "context": f"forex {symbol}"})
        
        if result.success:
            return {
                "symbol": symbol,
                "sentiment": result.data.get("overall_sentiment"),
                "score": result.data.get("average_score"),
                "confidence": min(len(relevant_texts) / 5, 1.0),
                "relevant_news": len(relevant_texts)
            }
        
        return {
            "symbol": symbol,
            "sentiment": "neutral",
            "score": 0.0,
            "confidence": 0.0,
            "error": result.error
        }
    
    def clear_cache(self):
        """Limpia el cache de análisis"""
        self._cache = {}
        logger.debug("Cache de SentimentAgent limpiado")


if __name__ == "__main__":
    print("=" * 50)
    print("Test de SentimentAgent")
    print("=" * 50)
    
    agent = SentimentAgent()
    
    # Test análisis único
    print("\n--- Análisis único ---")
    result = agent.analyze_single(
        "El BCE sorprende al mercado con una subida de tipos de 50 puntos básicos",
        context="forex"
    )
    print(f"Resultado: {result}")
    
    # Test batch
    print("\n--- Análisis batch ---")
    texts = [
        "El dólar se fortalece frente al euro por datos de empleo positivos",
        "Incertidumbre política en Europa presiona la divisa común",
        "Los mercados esperan continuidad en la política monetaria"
    ]
    
    batch_result = agent.run({"texts": texts})
    print(f"Éxito: {batch_result.success}")
    print(f"Sentimiento general: {batch_result.data.get('overall_sentiment')}")
    print(f"Score promedio: {batch_result.data.get('average_score')}")
