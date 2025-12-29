"""
News Scraper - Scraper para noticias de Forex/Trading
"""

import asyncio
import pytz
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from loguru import logger
import json
import requests

from .base_scraper import BaseScraper, ScrapedItem


class NewsScraper(BaseScraper):
    """
    Scraper especializado en noticias de trading forex con arquitectura en capas.
    
    Fuentes (Pesos):
    - Reuters (0.4)
    - Investing.com (0.25)
    - Yahoo Finance (0.2)
    - MarketWatch (0.1)
    - CNBC (0.05)
    """
    
    def __init__(self):
        super().__init__("NewsScraper")
        
        self.sources = [
            {
                "name": "reuters",
                "url": "https://www.reuters.com/markets/",
                "article_selector": "article",
                "title_selector": "h3",
                "summary_selector": "p",
                "link_selector": "a[href]",
                "time_selector": "time",
                "weight": 0.4,
                "enabled": True
            },
            {
                "name": "investing",
                "url": "https://www.investing.com/news/stock-market-news",
                "article_selector": "article.js-article-item",
                "title_selector": "a.title",
                "summary_selector": "p",
                "link_selector": "a.title",
                "time_selector": "span.date",
                "weight": 0.25,
                "enabled": True
            },
            {
                "name": "yahoo",
                "url": "https://finance.yahoo.com/news/",
                "article_selector": "li.js-stream-content",
                "title_selector": "h3",
                "summary_selector": "p",
                "link_selector": "a[href]",
                "time_selector": "time",
                "weight": 0.2,
                "enabled": True
            },
            {
                "name": "marketwatch",
                "url": "https://www.marketwatch.com/markets",
                "article_selector": "div.element--article",
                "title_selector": "h3.article__headline",
                "summary_selector": "p.article__summary",
                "link_selector": "a[href]",
                "time_selector": "time",
                "weight": 0.1,
                "enabled": True
            },
            {
                "name": "cnbc",
                "url": "https://www.cnbc.com/markets/",
                "article_selector": "div.Card-standardBreakerCard",
                "title_selector": "a.Card-title",
                "summary_selector": None,
                "link_selector": "a.Card-title",
                "time_selector": "time",
                "weight": 0.05,
                "enabled": True
            }
        ]
    
    async def scrape_source(self, source: dict) -> List[ScrapedItem]:
        """Scrapea una fuente específica de noticias"""
        items = []
        
        if not source.get("enabled", True):
            return items
        
        logger.info(f"Scrapeando {source['name']}: {source['url']}")
        
    async def navigate(self, url: str, wait_selector: str = None) -> bool:
        """Navega a la url y espera a que el contenido cargue"""
        return await super().navigate(url, wait_selector)

    def _parse_news_time(self, time_el) -> datetime:
        """Parsea el tiempo de publicación de una noticia de forma robusta"""
        now = datetime.utcnow()
        if not time_el:
            return now
            
        # 1. Intentar atributo datetime o data-time (ISO format)
        for attr in ['datetime', 'data-time', 'title']:
            dt_str = time_el.get(attr, '')
            if dt_str and len(dt_str) > 5:
                try:
                    # Handle Z and common formats
                    clean_dt = dt_str.replace('Z', '+00:00').replace('/', '-')
                    return datetime.fromisoformat(clean_dt).astimezone(timezone.utc).replace(tzinfo=None)
                except:
                    pass
        
        # 2. Parsear texto relativo o absoluto
        text = time_el.get_text(strip=True).lower().replace('.', '')
        import re
        
        try:
            # Just now
            if any(x in text for x in ['just now', 'ahora', '1 min']):
                return now
            
            # Minutes ago
            if 'min' in text:
                m = re.search(r'(\d+)', text)
                if m: return now - timedelta(minutes=int(m.group(1)))
                
            # Hours ago
            if 'hour' in text or 'hora' in text:
                m = re.search(r'(\d+)', text)
                if m: return now - timedelta(hours=int(m.group(1)))
                
            # Days ago
            if 'day' in text or 'día' in text:
                m = re.search(r'(\d+)', text)
                if m: return now - timedelta(days=int(m.group(1)))
                
            # Yesterday
            if 'yesterday' in text or 'ayer' in text:
                return now - timedelta(days=1)
            
            # 3. Formatos específicos complejos (ej: "dec 29, 2025 at 4:30 pm et")
            if ' at ' in text:
                # Extraer fecha y hora
                # "dec 29, 2025 at 4:30 pm et" -> "dec 29, 2025 4:30 pm"
                clean_text = text.split(' et')[0].replace(' at ', ' ')
                for fmt in ['%b %d, %Y %I:%M %p', '%B %d, %Y %I:%M %p']:
                    try:
                        dt = datetime.strptime(clean_text, fmt)
                        # Si dice ET, es US/Eastern (-5h UTC). Madrid es +1 UTC (+6h relativo a ET)
                        return dt + timedelta(hours=5) 
                    except:
                        continue

            # Absolute dates (e.g. "Dec 29, 2025") - Basic approach
            if len(text) > 5:
                for fmt in ['%b %d, %Y', '%B %d, %Y', '%d %b %Y', '%Y-%m-%d']:
                    try:
                        return datetime.strptime(text, fmt)
                    except:
                        continue
        except Exception:
            pass
            
        return now

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
        
        await asyncio.sleep(source.get("wait_time", 3))
        
        try:
            from bs4 import BeautifulSoup
            content = await self.get_page_content()
            soup = BeautifulSoup(content, 'lxml')
            articles = soup.select(source["article_selector"])[:10]
            
            for article in articles:
                try:
                    title_el = article.select_one(source["title_selector"])
                    title = title_el.get_text(strip=True) if title_el else ""
                    if not title: continue
                    
                    summary = ""
                    if source.get("summary_selector"):
                        summary_el = article.select_one(source["summary_selector"])
                        summary = summary_el.get_text(strip=True) if summary_el else ""
                    
                    # Extraer tiempo
                    time_dt = datetime.utcnow()
                    if source.get("time_selector"):
                        time_el = article.select_one(source["time_selector"])
                        if time_el:
                            time_dt = self._parse_news_time(time_el)
                    
                    link_el = article.select_one(source["link_selector"])
                    link = ""
                    if link_el and link_el.get("href"):
                        href = link_el["href"]
                        link = (source["url"].split("//")[0] + "//" + source["url"].split("//")[1].split("/")[0] + href) if href.startswith("/") else href
                    
                    item = ScrapedItem(
                        source=source["name"],
                        title=title,
                        content=summary,
                        url=link,
                        timestamp=time_dt,
                        metadata={
                            "type": "news",
                            "source_weight": source["weight"],
                            "published_at": time_dt.strftime('%Y-%m-%d %H:%M:%S')
                        }
                    )
                    items.append(item)
                except Exception as e:
                    logger.debug(f"Error parseando artículo de {source['name']}: {e}")
            
        except Exception as e:
            logger.error(f"Error parseando HTML de {source['name']}: {e}")
        
        return items
    
    async def scrape(self) -> List[ScrapedItem]:
        """Scrapea todas las fuentes de noticias configuradas"""
        all_items = []
        try:
            await self.start()
            for source in self.sources:
                items = await self.scrape_source(source)
                all_items.extend(items)
                import random
                await asyncio.sleep(random.uniform(2, 5))
        except Exception as e:
            logger.error(f"Error en el ciclo de NewsScraper: {e}")
        finally:
            await self.stop()
            
        logger.info(f"Total noticias scrapeadas: {len(all_items)}")
        return all_items


class CalendarScraper(BaseScraper):
    """
    Scraper para calendario económico (Investing.com) con Stealth 2.0.
    """
    
    def __init__(self):
        super().__init__("CalendarScraper")
        self.calendar_url = "https://www.investing.com/economic-calendar/"
    
    async def scrape(self) -> List[ScrapedItem]:
        items = []
        logger.info(f"Scrapeando calendario Investing.com (Stealth 2.0)")
        
        try:
            await self.start()
            
            # Aplicar Cookies para forzar idioma inglés
            await self.set_cookies([
                {"name": "edition_redirect", "value": "1", "domain": ".investing.com", "path": "/"},
                {"name": "user_lang", "value": "1", "domain": ".investing.com", "path": "/"}
            ])
            
            # Navegar con timeout moderado
            success = await self.navigate(self.calendar_url, wait_selector="#economicCalendarTable")
            
            if success:
                content = await self.get_page_content()
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(content, 'lxml')
                
                # Buscar eventos
                events = soup.select("tr.js-event-item")[:50]
                logger.debug(f"Encontrados {len(events)} eventos en Investing")
                
                for event in events:
                    try:
                        ts_attr = event.get('data-event-datetime', '')
                        event_dt = None
                        if ts_attr:
                            try:
                                event_dt = datetime.strptime(ts_attr, "%Y/%m/%d %H:%M:%S")
                                # Investing US (lang=1) typically uses EDT/EST. 
                                # Normalizamos EDT (+4h) a UTC para consistencia.
                                event_dt = event_dt + timedelta(hours=4)
                            except:
                                pass
                        
                        if not event_dt:
                            # Intento final: si el atributo falla, buscar el texto en la celda de tiempo
                            time_el = event.select_one("td.time")
                            time_text = time_el.get_text(strip=True).lower() if time_el else ""
                            
                            if 'min' in time_text or 'now' in time_text:
                                import re
                                match = re.search(r'(\d+)', time_text)
                                mins = int(match.group(1)) if match else 0
                                event_dt = datetime.utcnow() + timedelta(minutes=mins)
                            else:
                                continue # Sigue siendo desconocido o relativo sin números
                            
                        curr_el = event.select_one("td.flagCur")
                        currency = curr_el.get_text(strip=True) if curr_el else "USD"
                        
                        impact_el = event.select_one("td.sentiment")
                        impact_count = len(event.select("td.sentiment i.grayFullBullishIcon")) if impact_el else 0
                        impact = "high" if impact_count >= 3 else "medium" if impact_count == 2 else "low"
                        
                        # CAPTURAMOS TODO EL IMPACTO (1, 2, 3 ESTRELLAS)
                        # No filtramos por impact == "low"
                            
                        event_el = event.select_one("td.event a")
                        event_name = event_el.get_text(strip=True) if event_el else ""
                        
                        if not event_name:
                            continue
                            
                        actual = event.select_one("td.act").get_text(strip=True) if event.select_one("td.act") else ""
                        forecast = event.select_one("td.fore").get_text(strip=True) if event.select_one("td.fore") else ""
                        previous = event.select_one("td.prev").get_text(strip=True) if event.select_one("td.prev") else ""
                        
                        item = ScrapedItem(
                            source="investing_calendar",
                            title=event_name,
                            content=f"Currency: {currency} | Impact: {impact} | Forecast: {forecast}",
                            url=self.calendar_url,
                            timestamp=datetime.now(),
                            metadata={
                                "type": "economic_event",
                                "currency": currency,
                                "impact": impact,
                                "time": event_dt.strftime('%Y-%m-%d %H:%M:%S'),
                                "actual": actual,
                                "forecast": forecast,
                                "previous": previous
                            }
                        )
                        items.append(item)
                    except:
                        continue
            else:
                logger.warning("Timeout o bloqueo en Investing, activando fallback ForexFactory")
                
        except Exception as e:
            logger.error(f"Error en Investing Scraper: {e}, activando fallback")
        finally:
            await self.stop()

        # MERGE SOURCES: Investing + ForexFactory (100% Coverage)
        ff_items = await self._scrape_forexfactory_fallback()
        
        # Combinar deduplicando por firma (Título + Divisa)
        combined_items = []
        seen_sigs = set()
        
        # Prioridad 1: ForexFactory (Suele tener horas absolutas perfectas)
        for item in ff_items:
            sig = f"{item.title}_{item.metadata.get('currency')}_{item.metadata.get('time')}"
            seen_sigs.add(sig)
            combined_items.append(item)
            
        # Prioridad 2: Investing (Más riqueza de datos como Actual/Forecast)
        for item in items:
            sig = f"{item.title}_{item.metadata.get('currency')}_{item.metadata.get('time')}"
            # Si ya está de FF, solo actualizamos los campos de metadatos si estaban vacíos
            # pero mantenemos la hora de FF si es absoluta.
            if sig in seen_sigs:
                for existing in combined_items:
                    if f"{existing.title}_{existing.metadata.get('currency')}_{existing.metadata.get('time')}" == sig:
                        # Enriquecer con datos de Investing si faltan en FF
                        if not existing.metadata.get("actual") and item.metadata.get("actual"):
                            existing.metadata["actual"] = item.metadata["actual"]
                        if not existing.metadata.get("forecast") and item.metadata.get("forecast"):
                            existing.metadata["forecast"] = item.metadata["forecast"]
                        if not existing.metadata.get("previous") and item.metadata.get("previous"):
                            existing.metadata["previous"] = item.metadata["previous"]
                        break
            else:
                seen_sigs.add(sig)
                combined_items.append(item)
                
        return combined_items

    async def _scrape_forexfactory_fallback(self) -> List[ScrapedItem]:
        """Fallback ultra-fiable usando el feed JSON de ForexFactory"""
        logger.info("Iniciando Fallback: ForexFactory JSON Feed")
        items = []
        json_url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        
        try:
            import requests # Asegurar import local si falló arriba
            response = requests.get(json_url, timeout=10, headers={
                "User-Agent": "Mozilla/5.0 (ARAFURA-Bot/1.0)"
            })
            if response.status_code == 200:
                events = response.json()
                for ev in events:
                    impact = ev.get("impact", "Low").lower()
                    # CAPTURAMOS TODO EL IMPACTO (Low, Medium, High)
                        
                    date_str = ev.get("date", "")
                    try:
                        # ForexFactory JSON is typically EST/EDT (-05:00) or has Z
                        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        # Forzar a UTC real si tiene offset
                        if dt.tzinfo:
                            dt = dt.astimezone(pytz.UTC)
                        
                        final_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        # RECHAZAR si no es un formato de fecha válido
                        continue
                    
                    item = ScrapedItem(
                        source="forexfactory_fallback",
                        title=ev.get("title", "Event"),
                        content=f"Currency: {ev.get('country')} | Impact: {impact} | Forecast: {ev.get('forecast')}",
                        url="https://www.forexfactory.com/calendar",
                        timestamp=datetime.now(),
                        metadata={
                            "type": "economic_event",
                            "currency": ev.get("country"),
                            "impact": impact,
                            "time": final_time,
                            "actual": "", 
                            "forecast": ev.get("forecast", ""),
                            "previous": ev.get("previous", "")
                        }
                    )
                    items.append(item)
                logger.info(f"Fallback exitoso: {len(items)} eventos recuperados")
        except Exception as e:
            logger.error(f"Falla crítica en fallback: {e}")
            
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
