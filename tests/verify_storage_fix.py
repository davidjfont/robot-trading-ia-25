
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from scraping.base_scraper import ScrapedItem
from scraping.storage import get_storage

def test_storage():
    storage = get_storage()
    
    # Test item
    item = ScrapedItem(
        source="test_source",
        title="Test Event",
        content="Test Content",
        url="https://example.com/test",
        timestamp=datetime.now(),
        metadata={
            "currency": "USD",
            "impact": "high",
            "time": "12:00",
            "actual": "1.0",
            "forecast": "0.9",
            "previous": "0.8"
        }
    )
    
    print("Testing save_events...")
    saved = storage.save_events([item])
    print(f"Saved {saved} events")
    
    print("Testing save_news...")
    saved_news = storage.save_news([item])
    print(f"Saved {saved_news} news")
    
    if saved > 0 and (saved_news >= 0): # saved_news might be 0 if URL exists
        print("✅ Storage verification SUCCESSFUL")
    else:
        print("❌ Storage verification FAILED")

if __name__ == "__main__":
    test_storage()
