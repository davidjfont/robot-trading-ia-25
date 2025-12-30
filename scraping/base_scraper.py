"""
Base Scraper - Clase base para web scraping con Playwright
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger
import random
import time
import os
import yaml


@dataclass
class ScrapedItem:
    """Representa un item scrapeado"""
    source: str
    title: str
    content: str
    url: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseScraper(ABC):
    """
    Clase base para todos los scrapers del sistema.
    
    Características:
    - Usa Playwright para navegación
    - Rotación de User-Agents
    - Manejo de errores y reintentos
    - Rate limiting para evitar bloqueos
    """
    
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    ]
    
    def __init__(self, name: str, config_path: str = "config.yaml"):
        """
        Inicializa el scraper base
        
        Args:
            name: Nombre identificador del scraper
            config_path: Ruta al archivo de configuración
        """
        self.name = name
        self.config = self._load_config(config_path)
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self._request_count = 0
        self._last_request_time = None
        
        # Config de rate limiting
        scraping_config = self.config.get("scraping", {})
        self.min_delay = scraping_config.get("min_delay_seconds", 1)
        self.max_delay = scraping_config.get("max_delay_seconds", 3)
        self.max_retries = scraping_config.get("max_retries", 3)
        
        logger.info(f"Scraper '{self.name}' inicializado")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Carga configuración desde YAML"""
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            full_path = os.path.join(base_dir, config_path)
            
            with open(full_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Config no encontrada: {config_path}")
            return {}
        except Exception as e:
            logger.error(f"Error cargando config: {e}")
            return {}
    
    def _get_random_user_agent(self) -> str:
        """Obtiene un User-Agent aleatorio"""
        custom_agents = self.config.get("scraping", {}).get("user_agents", [])
        agents = custom_agents if custom_agents else self.USER_AGENTS
        return random.choice(agents)
    
    def _rate_limit(self):
        """Aplica rate limiting entre requests"""
        if self._last_request_time:
            elapsed = (datetime.now() - self._last_request_time).total_seconds()
            delay = random.uniform(self.min_delay, self.max_delay)
            if elapsed < delay:
                sleep_time = delay - elapsed
                logger.debug(f"Rate limit: esperando {sleep_time:.2f}s")
                time.sleep(sleep_time)
        
        self._last_request_time = datetime.now()
        self._request_count += 1
    
    async def start(self):
        """Inicia el navegador Playwright"""
        from playwright.async_api import async_playwright
        
        self.playwright = await async_playwright().start()
        
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--allow-running-insecure-content'
            ]
        )
        
        user_agent = self._get_random_user_agent()
        self.context = await self.browser.new_context(
            user_agent=user_agent,
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='UTC',
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/"
            }
        )
        
        self.page = await self.context.new_page()
        
        logger.info(f"Navegador iniciado para '{self.name}' (Stealth 2.0)")
    
    async def set_cookies(self, cookies: List[Dict[str, Any]]):
        """Añade cookies al contexto"""
        if self.context:
            await self.context.add_cookies(cookies)
            logger.debug(f"Cookies añadidas para '{self.name}'")

    async def stop(self):
        """Cierra el navegador"""
        if self.browser:
            await self.browser.close()
            logger.info(f"Navegador cerrado para '{self.name}'")
        
        if self.playwright:
            await self.playwright.stop()
            # Pequeño delay para permitir que Windows limpie los pipes del proceso hijo
            # antes de que el loop de asyncio se cierre del todo.
            await asyncio.sleep(0.2)
    
    async def navigate(self, url: str, wait_selector: Optional[str] = None) -> bool:
        """
        Navega a una URL con manejo de errores
        
        Args:
            url: URL a visitar
            wait_selector: Selector CSS a esperar (opcional)
        
        Returns:
            True si la navegación fue exitosa
        """
        if not self.page:
            logger.error("Navegador no iniciado. Ejecute start() primero.")
            return False
        
        self._rate_limit()
        
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Navegando a {url} (intento {attempt + 1})")
                
                # Usar un timeout mas largo y wait_until="networkidle"
                response = await self.page.goto(url, wait_until="load", timeout=45000)
                
                if response:
                    logger.debug(f"HTTP Status: {response.status} para {url}")
                
                if response and response.status >= 400:
                    logger.warning(f"HTTP {response.status} en {url}")
                    if response.status == 403:
                         logger.error("Detección de Bot (403 Forbidden).")
                    continue
                
                if wait_selector:
                    logger.debug(f"Esperando selector {wait_selector}...")
                    await self.page.wait_for_selector(wait_selector, timeout=15000)
                
                logger.debug(f"Navegación exitosa a {url}")
                return True
                
            except Exception as e:
                logger.warning(f"Error navegando a {url}: {e} (intento {attempt + 1})")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(5)  # Esperar mas tiempo entre reintentos
        
        logger.error(f"Falló navegación a {url} después de {self.max_retries} intentos")
        return False
    
    async def get_text(self, selector: str) -> str:
        """Obtiene texto de un elemento"""
        try:
            element = await self.page.query_selector(selector)
            if element:
                return await element.text_content() or ""
            return ""
        except Exception as e:
            logger.debug(f"Error obteniendo texto de {selector}: {e}")
            return ""
    
    async def get_texts(self, selector: str) -> List[str]:
        """Obtiene textos de múltiples elementos"""
        try:
            elements = await self.page.query_selector_all(selector)
            texts = []
            for el in elements:
                text = await el.text_content()
                if text:
                    texts.append(text.strip())
            return texts
        except Exception as e:
            logger.debug(f"Error obteniendo textos de {selector}: {e}")
            return []
    
    async def get_attribute(self, selector: str, attribute: str) -> str:
        """Obtiene atributo de un elemento"""
        try:
            element = await self.page.query_selector(selector)
            if element:
                return await element.get_attribute(attribute) or ""
            return ""
        except Exception as e:
            logger.debug(f"Error obteniendo atributo {attribute} de {selector}: {e}")
            return ""
    
    async def get_page_content(self) -> str:
        """Obtiene todo el contenido de la página"""
        if self.page:
            return await self.page.content()
        return ""
    
    @abstractmethod
    async def scrape(self) -> List[ScrapedItem]:
        """
        Método principal de scraping. Debe ser implementado por cada scraper.
        
        Returns:
            Lista de items scrapeados
        """
        pass
    
    async def run(self) -> List[ScrapedItem]:
        """
        Ejecuta el scraper completo con manejo de recursos
        
        Returns:
            Lista de items scrapeados
        """
        items = []
        
        try:
            await self.start()
            items = await self.scrape()
            logger.info(f"'{self.name}' obtuvo {len(items)} items")
        except Exception as e:
            logger.error(f"Error en scraper '{self.name}': {e}")
        finally:
            await self.stop()
        
        return items
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del scraper"""
        return {
            "name": self.name,
            "request_count": self._request_count,
            "last_request": self._last_request_time.isoformat() if self._last_request_time else None
        }


# Import asyncio for the navigate method
import asyncio
