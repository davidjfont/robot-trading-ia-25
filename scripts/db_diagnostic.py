"""
Diagnostic Tool for Trading Database Integrity
"""

import sys
import os
from datetime import datetime, timedelta
from loguru import logger

# Configurar path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from scraping.storage import get_storage, TradeHistory
from mt5.connector import MT5Connector

def run_diagnostic():
    print("=" * 60)
    print("🔍 DIAGNÓSTICO DE INTEGRIDAD DEL SISTEMA")
    print("=" * 60)
    
    storage = get_storage()
    mt5 = MT5Connector()
    
    # 1. Chequeo Físico de SQLite
    print("\n1. [DB] Verificando integridad física de SQLite...")
    session = storage.get_session()
    try:
        result = session.execute("PRAGMA integrity_check").fetchone()
        if result[0] == "ok":
            print("   ✅ Base de datos físicamente íntegra.")
        else:
            print(f"   ❌ ERROR DE INTEGRIDAD: {result[0]}")
    except Exception as e:
        print(f"   ❌ Error ejecutando PRAGMA: {e}")
    finally:
        session.close()

    # 2. Verificar Duplicados y Estadísticas Básicas
    print("\n2. [Contenido] Analizando registros locales...")
    session = storage.get_session()
    try:
        total_trades = session.query(TradeHistory).count()
        closed_trades = session.query(TradeHistory).filter(TradeHistory.status == "closed").count()
        open_trades = session.query(TradeHistory).filter(TradeHistory.status == "open").count()
        
        # Buscar duplicados por ticket
        duplicates = session.execute(
            "SELECT ticket, COUNT(*) FROM trade_history GROUP BY ticket HAVING COUNT(*) > 1"
        ).fetchall()
        
        print(f"   📊 Total registros: {total_trades}")
        print(f"   📊 Cerrados: {closed_trades} | Abiertos: {open_trades}")
        
        if not duplicates:
            print("   ✅ No se detectaron tickets duplicados.")
        else:
            print(f"   ❌ SE DETECTARON {len(duplicates)} TICKETS DUPLICADOS:")
            for d in duplicates:
                print(f"      - Ticket #{d[0]}: {d[1]} apariciones")
                
    except Exception as e:
        print(f"   ❌ Error analizando registros: {e}")
    finally:
        session.close()

    # 3. Consistencia con MT5
    print("\n3. [MT5] Comparando con la realidad del broker...")
    if not mt5.connect():
        print("   ❌ No se pudo conectar a MetaTrader 5 para validación.")
    else:
        try:
            # Comparar últimos 7 días
            days = 7
            cutoff = datetime.now() - timedelta(days=days)
            
            # Local
            session = storage.get_session()
            local_deals_count = session.query(TradeHistory).filter(
                TradeHistory.closed_at >= cutoff
            ).count()
            session.close()
            
            # Broker
            mt5_deals = mt5.get_history_deals(days=days)
            # Agrupar por posición para contar trades cerrados (cada cierre genera un deal ENTRY_OUT)
            mt5_closed_tickets = {d['ticket'] for d in mt5_deals if d.get('entry_type') == 1}
            broker_count = len(mt5_closed_tickets)
            
            print(f"   📅 Datos de los últimos {days} días:")
            print(f"      - Local (DB): {local_deals_count} trades cerrados")
            print(f"      - Broker (MT5): {broker_count} trades cerrados")
            
            if local_deals_count >= broker_count:
                print("   ✅ El historial local está al día o por delante del broker.")
            else:
                diff = broker_count - local_deals_count
                print(f"   ⚠️ FALTAN {diff} TRADES en la base de datos local.")
                print("      👉 Sugerencia: Pulse 'Sincronizar TOTAL' en el dashboard.")

            # 4. Verificar posiciones huerfanas (Open en DB pero no en MT5)
            print("\n4. [Sync] Buscando posiciones huérfanas...")
            session = storage.get_session()
            db_open_trades = session.query(TradeHistory).filter(TradeHistory.status == "open").all()
            session.close()
            
            mt5_positions = mt5.get_positions()
            mt5_open_tickets = {p.ticket for p in mt5_positions}
            
            orphans = []
            for t in db_open_trades:
                if t.ticket not in mt5_open_tickets:
                    orphans.append(t.ticket)
            
            if not orphans:
                print("   ✅ Todas las órdenes 'Abiertas' en DB existen en MT5.")
            else:
                print(f"   ⚠️ Se encontraron {len(orphans)} órdenes huérfanas (Open en DB, Cerradas en MT5):")
                print(f"      Tickets: {orphans}")
                print("      👉 Estas órdenes se cerrarán automáticamente en la próxima sincronización.")

        except Exception as e:
            print(f"   ❌ Error en validación MT5: {e}")
        finally:
            mt5.disconnect()

    print("\n" + "=" * 60)
    print("🏁 Diagnóstico completado.")
    print("=" * 60)

if __name__ == "__main__":
    run_diagnostic()
