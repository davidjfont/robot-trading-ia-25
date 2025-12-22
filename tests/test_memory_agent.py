
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.memory_agent import get_memory_agent

def test_memory():
    print("Testing MemoryAgent...")
    agent = get_memory_agent()
    
    # Generate memory for today (as a test)
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"Generating memory for {today}...")
    
    result = agent.execute({"date": today})
    
    if result.success:
        print("✅ MemoryAgent execution SUCCESSFUL")
        print("\nSummary generated:")
        print("-" * 50)
        print(result.data.get("summary"))
        print("-" * 50)
    else:
        print(f"❌ MemoryAgent execution FAILED: {result.error}")

if __name__ == "__main__":
    test_memory()
