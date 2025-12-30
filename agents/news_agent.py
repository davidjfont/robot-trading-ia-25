"""
News Agent - Agente especializado en scraping y análisis de noticias
"""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger

from .base_agent import BaseAgent, AgentResult
from .llm_provider import get_llm
from scraping.news_scraper import NewsScraper, CalendarScraper
from scraping.storage import get_storage


class NewsAgent(BaseAgent):
    """
    Agente que recopila y analiza noticias de trading.
    
    Funciones:
    - Scrapea noticias de múltiples fuentes
    - Analiza impacto en mercado con LLM
    - Almacena en base de datos
    """
    
    def __init__(self):
        super().__init__("NewsAgent")
        self.news_scraper = NewsScraper()
        self.calendar_scraper = CalendarScraper()
        self.llm = get_llm()
        self.storage = get_storage()
    
    def execute(self, data: Any = None) -> AgentResult:
        """
        Ejecuta el ciclo completo de recopilación y análisis de noticias
        
        Args:
            data: Configuración opcional (ej: {"sources": ["investing"]})
        """
        try:
            # Ejecutar scrapers de forma síncrona compartiendo sesión
            async def run_scrapers_optimized():
                news_items = []
                calendar_items = []
                try:
                    # Iniciar playwright una sola vez
                    await self.news_scraper.start()
                    # Reutilizar el contexto para el otro scraper
                    self.calendar_scraper.playwright = self.news_scraper.playwright
                    self.calendar_scraper.browser = self.news_scraper.browser
                    self.calendar_scraper.context = self.news_scraper.context
                    self.calendar_scraper.page = await self.calendar_scraper.context.new_page()
                    
                    # Ejecutar ambos
                    news_items = await self.news_scraper.scrape()
                    calendar_items = await self.calendar_scraper.scrape()
                finally:
                    # Cerrar todo
                    await self.calendar_scraper.stop() # Cierra su página
                    await self.news_scraper.stop()     # Cierra navegador y playwright
                
                return news_items, calendar_items

            try:
                news_items, calendar_items = asyncio.run(run_scrapers_optimized())
            except RuntimeError:
                # Fallback redundante pero robusto
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    news_items, calendar_items = loop.run_until_complete(run_scrapers_optimized())
                finally:
                    loop.close()
            
            # Guardar en base de datos
            news_saved = self.storage.save_news(news_items)
            events_saved = self.storage.save_events(calendar_items)
            
            # Analizar noticias no procesadas
            unprocessed = self.storage.get_recent_news(hours=24, processed=False)
            analyzed_count = 0
            
            for news in unprocessed[:10]:  # Limitar para no sobrecargar
                if self.llm.is_available():
                    analysis = self.llm.analyze_sentiment(
                        f"Título: {news.title}\nContenido: {news.content}",
                        context="forex"
                    )
                    
                    self.storage.mark_news_processed(
                        news.id,
                        sentiment=analysis.get("sentiment", "neutral"),
                        score=analysis.get("score", 0.0),
                        impact=analysis.get("impact", "low")
                    )
                    analyzed_count += 1
            
            # Guardar log en Consola
            self.storage.save_agent_log(
                self.name,
                "Scraping y Análisis",
                f"Noticias: {news_saved}, Eventos: {events_saved}, Analizadas: {analyzed_count}",
                True
            )
            
            return AgentResult(
                agent_name=self.name,
                success=True,
                data={

                    "news_scraped": len(news_items),
                    "news_saved": news_saved,
                    "events_scraped": len(calendar_items),
                    "events_saved": events_saved,
                    "analyzed": analyzed_count
                }
            )
            
        except Exception as e:
            logger.error(f"Error en NewsAgent: {e}")
            return AgentResult(
                agent_name=self.name,
                success=False,
                error=str(e)
            )
    
    def get_recent_news_summary(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Obtiene resumen de noticias recientes analizadas"""
        news_list = self.storage.get_recent_news(hours=hours, processed=True)
        
        return [{
            "title": n.title,
            "source": n.source,
            "sentiment": n.sentiment,
            "score": n.sentiment_score,
            "impact": n.impact,
            "time": n.scraped_at.isoformat()
        } for n in news_list]
    
    def get_market_sentiment(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Calcula el sentimiento general del mercado basado en noticias
        
        Args:
            symbol: Par de divisas específico (ej: "EUR", "USD")
        
        Returns:
            Dict con sentimiento agregado
        """
        news_list = self.storage.get_recent_news(hours=24, processed=True)
        
        if symbol:
            # Filtrar noticias relacionadas con el símbolo
            news_list = [n for n in news_list if symbol.upper() in (n.title + n.content).upper()]
        
        if not news_list:
            return {
                "sentiment": "neutral",
                "score": 0.0,
                "confidence": 0.0,
                "news_count": 0
            }
        
        # Calcular sentimiento promedio ponderado por impacto
        weights = {"high": 3, "medium": 2, "low": 1}
        total_weight = 0
        weighted_score = 0
        
        for news in news_list:
            weight = weights.get(news.impact, 1)
            score = news.sentiment_score or 0
            weighted_score += score * weight
            total_weight += weight
        
        avg_score = weighted_score / total_weight if total_weight > 0 else 0
        
        # Determinar sentimiento basado en score
        if avg_score > 0.3:
            sentiment = "bullish"
        elif avg_score < -0.3:
            sentiment = "bearish"
        else:
            sentiment = "neutral"
        
        return {
            "sentiment": sentiment,
            "score": round(avg_score, 3),
            "confidence": min(len(news_list) / 10, 1.0),  # Más noticias = más confianza
            "news_count": len(news_list)
        }


if __name__ == "__main__":
    print("=" * 50)
    print("Test de NewsAgent")
    print("=" * 50)
    
    agent = NewsAgent()
    
    # Ejecutar agente
    result = agent.run(None)
    
    print(f"\nResultado: {'✅ Éxito' if result.success else '❌ Error'}")
    print(f"Datos: {result.data}")
    print(f"Tiempo: {result.execution_time_ms:.2f}ms")
    
    # Obtener sentimiento
    sentiment = agent.get_market_sentiment("EUR")
    print(f"\nSentimiento EUR: {sentiment}")
