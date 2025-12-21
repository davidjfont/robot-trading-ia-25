"""
News Scraper - Scraper para noticias de Forex/Trading
"""

import asyncio
from typing import List, Optional
from datetime import datetime
from loguru import logger
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper, ScrapedItem


class NewsScraper(BaseScraper):
    """
    Scraper especializado en noticias de trading forex.
    
    Fuentes soportadas:
    - Investing.com
    - FXStreet
    - DailyFX
    """
    
    def __init__(self):
        super().__init__("NewsScraper")
        
        self.sources = [
            {
                "name": "investing",
                "url": "https://www.investing.com/news/forex-news",
                "article_selector": ".largeTitle article",
                "title_selector": "a.title",
                "summary_selector": "p",
                "link_selector": "a.title",
                "enabled": True
            },
            {
                "name": "fxstreet",
                "url": "https://www.fxstreet.es/news",
                "article_selector": "article.fxs_article",
                "title_selector": "h4 a, h3 a",
                "summary_selector": "p.fxs_article_text",
                "link_selector": "h4 a, h3 a",
                "enabled": True
            }
        ]
    
    async def scrape_source(self, source: dict) -> List[ScrapedItem]:
        """Scrapea una fuente específica de noticias"""
        items = []
        
        if not source.get("enabled", True):
            return items
        
        logger.info(f"Scrapeando {source['name']}: {source['url']}")
        
        success = await self.navigate(source["url"])
        if not success:
            logger.warning(f"No se pudo acceder a {source['name']}")
            return items
        
        # Esperar un poco para que cargue contenido dinámico
        await asyncio.sleep(2)
        
        try:
            # Obtener HTML de la página
            content = await self.get_page_content()
            soup = BeautifulSoup(content, 'lxml')
            
            # Buscar artículos
            articles = soup.select(source["article_selector"])[:10]  # Máximo 10 artículos
            
            logger.debug(f"Encontrados {len(articles)} artículos en {source['name']}")
            
            for article in articles:
                try:
                    # Extraer título
                    title_el = article.select_one(source["title_selector"])
                    title = title_el.get_text(strip=True) if title_el else ""
                    
                    if not title:
                        continue
                    
                    # Extraer resumen
                    summary_el = article.select_one(source["summary_selector"])
                    summary = summary_el.get_text(strip=True) if summary_el else ""
                    
                    # Extraer link
                    link_el = article.select_one(source["link_selector"])
                    link = ""
                    if link_el and link_el.get("href"):
                        href = link_el["href"]
                        if href.startswith("/"):
                            # URL relativa
                            base = source["url"].split("/")[0:3]
                            link = "/".join(base) + href
                        else:
                            link = href
                    
                    item = ScrapedItem(
                        source=source["name"],
                        title=title,
                        content=summary,
                        url=link,
                        timestamp=datetime.now(),
                        metadata={
                            "type": "news",
                            "category": "forex"
                        }
                    )
                    
                    items.append(item)
                    
                except Exception as e:
                    logger.debug(f"Error parseando artículo: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error scrapeando {source['name']}: {e}")
        
        return items
    
    async def scrape(self) -> List[ScrapedItem]:
        """Scrapea todas las fuentes de noticias configuradas"""
        all_items = []
        
        for source in self.sources:
            items = await self.scrape_source(source)
            all_items.extend(items)
            
            # Pequeña pausa entre fuentes
            await asyncio.sleep(1)
        
        logger.info(f"Total noticias scrapeadas: {len(all_items)}")
        return all_items


class CalendarScraper(BaseScraper):
    """
    Scraper para calendario económico.
    
    Obtiene eventos económicos próximos que pueden afectar el mercado.
    """
    
    def __init__(self):
        super().__init__("CalendarScraper")
        
        self.calendar_url = "https://www.investing.com/economic-calendar/"
    
    async def scrape(self) -> List[ScrapedItem]:
        """Scrapea el calendario económico"""
        items = []
        
        logger.info(f"Scrapeando calendario económico")
        
        success = await self.navigate(self.calendar_url)
        if not success:
            logger.warning("No se pudo acceder al calendario económico")
            return items
        
        await asyncio.sleep(3)  # Esperar carga de JS
        
        try:
            content = await self.get_page_content()
            soup = BeautifulSoup(content, 'lxml')
            
            # Buscar eventos del calendario
            events = soup.select("tr.js-event-item")[:20]
            
            logger.debug(f"Encontrados {len(events)} eventos")
            
            for event in events:
                try:
                    # Tiempo del evento
                    time_el = event.select_one("td.time")
                    event_time = time_el.get_text(strip=True) if time_el else ""
                    
                    # País/Moneda
                    currency_el = event.select_one("td.flagCur")
                    currency = currency_el.get_text(strip=True) if currency_el else ""
                    
                    # Impacto (estrellas)
                    impact_el = event.select_one("td.sentiment")
                    impact_count = len(event.select("td.sentiment i.grayFullBullishIcon")) if impact_el else 0
                    impact = "high" if impact_count >= 3 else "medium" if impact_count == 2 else "low"
                    
                    # Nombre del evento
                    event_name_el = event.select_one("td.event a")
                    event_name = event_name_el.get_text(strip=True) if event_name_el else ""
                    
                    if not event_name:
                        continue
                    
                    # Valores actual/pronóstico/anterior
                    actual_el = event.select_one("td.act")
                    forecast_el = event.select_one("td.fore")
                    prev_el = event.select_one("td.prev")
                    
                    actual = actual_el.get_text(strip=True) if actual_el else ""
                    forecast = forecast_el.get_text(strip=True) if forecast_el else ""
                    previous = prev_el.get_text(strip=True) if prev_el else ""
                    
                    item = ScrapedItem(
                        source="investing_calendar",
                        title=event_name,
                        content=f"Currency: {currency} | Impact: {impact} | Forecast: {forecast} | Previous: {previous}",
                        url=self.calendar_url,
                        timestamp=datetime.now(),
                        metadata={
                            "type": "economic_event",
                            "currency": currency,
                            "impact": impact,
                            "time": event_time,
                            "actual": actual,
                            "forecast": forecast,
                            "previous": previous
                        }
                    )
                    
                    items.append(item)
                    
                except Exception as e:
                    logger.debug(f"Error parseando evento: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error scrapeando calendario: {e}")
        
        return items


async def main():
    """Test de los scrapers"""
    print("=" * 60)
    print("Test de Scrapers")
    print("=" * 60)
    
    # Test News Scraper
    print("\n--- Test NewsScraper ---")
    news_scraper = NewsScraper()
    news_items = await news_scraper.run()
    
    for item in news_items[:3]:
        print(f"\n📰 {item.title[:60]}...")
        print(f"   Fuente: {item.source}")
        print(f"   URL: {item.url[:50]}...")
    
    # Test Calendar Scraper
    print("\n--- Test CalendarScraper ---")
    calendar_scraper = CalendarScraper()
    calendar_items = await calendar_scraper.run()
    
    for item in calendar_items[:5]:
        print(f"\n📅 {item.title}")
        print(f"   {item.content}")


if __name__ == "__main__":
    asyncio.run(main())
