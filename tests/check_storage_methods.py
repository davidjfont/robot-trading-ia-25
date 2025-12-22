import sys
import os

# AGREGAR ANTES DE IMPORTAR
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraping.storage import Storage

storage = Storage()
print(f"Methods in Storage: {[m for m in dir(storage) if not m.startswith('_')]}")
if hasattr(storage, 'get_recent_agent_logs'):
    print("SUCCESS: get_recent_agent_logs FOUND")
else:
    print("FAILURE: get_recent_agent_logs NOT FOUND")
