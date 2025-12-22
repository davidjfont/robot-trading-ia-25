import sys
import os

# AGREGAR ANTES DE IMPORTAR
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mt5.connector import MT5Connector

conn = MT5Connector()
print(f"Methods in MT5Connector: {[m for m in dir(conn) if not m.startswith('_')]}")
if hasattr(conn, 'get_symbol_info'):
    print("SUCCESS: get_symbol_info FOUND")
else:
    print("FAILURE: get_symbol_info NOT FOUND")
