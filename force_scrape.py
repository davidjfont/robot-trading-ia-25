import asyncio
import sys
import os

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraping.news_scraper import CalendarScraper, NewsScraper
from scraping.storage import get_storage
from loguru import logger

logger.add("scrape_debug.log", rotation="1 MB")

async def main():
    storage = get_storage()
    
    print("Starting Manual Calendar Scrape...")
    c_scraper = CalendarScraper()
    c_items = await c_scraper.scrape()
    print(f"Scraped {len(c_items)} events.")
    
    if c_items:
        saved = storage.save_events(c_items)
        print(f"Stored Events: {saved} new.")
    
    print("\nStarting Manual News Scrape (Layered Architecture)...")
    n_scraper = NewsScraper()
    n_items = await n_scraper.scrape()
    print(f"Scraped {len(n_items)} news pieces.")
    
    if n_items:
        saved = storage.save_news(n_items)
        print(f"Stored News: {saved} new.")
    
    print("\nProcess completed.")

if __name__ == "__main__":
    asyncio.run(main())
