"""
Order Agent - Agente de ejecución de órdenes en MT5
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base_agent import BaseAgent, AgentResult
from mt5.connector import MT5Connector, OrderResult, Position
from scraping.storage import get_storage


class OrderAgent(BaseAgent):
    """
    Agente de ejecución de órdenes.
    
    Responsabilidades:
    - Ejecutar órdenes en MetaTrader 5
    - Gestionar posiciones abiertas
    - Registrar todas las operaciones
    - Aplicar filtros de seguridad finales
    """
    
    def __init__(self):
        super().__init__("OrderAgent")
        self.connector = MT5Connector()
        self.storage = get_storage()
        self._connected = False
    
    def connect(self) -> bool:
        """Conecta al MT5"""
        self._connected = self.connector.connect()
        return self._connected
    
    def disconnect(self):
        """Desconecta del MT5"""
        self.connector.disconnect()
        self._connected = False
    
    def execute(self, data: Any) -> AgentResult:
        """
        Ejecuta una orden de trading
        
        Args:
            data: Dict con:
                - symbol: Par de divisas
                - type: BUY/SELL
                - volume: Volumen en lotes
                - sl_pips: Stop loss en pips
                - tp_pips: Take profit en pips
                - signal_id: ID de la señal que generó la orden (opcional)
        """
        if not data:
            return AgentResult(
                agent_name=self.name,
                success=False,
                error="No se proporcionaron datos de orden"
            )
        
        try:
            # Asegurar conexión
            if not self.connector.ensure_connected():
                return AgentResult(
                    agent_name=self.name,
                    success=False,
                    error="No se pudo conectar a MT5. Asegúrese de que MetaTrader 5 está abierto."
                )
            
            symbol = data.get("symbol")
            order_type = data.get("type", "BUY")
            volume = data.get("volume", 0.01)
            sl_pips = data.get("sl_pips", 50)
            tp_pips = data.get("tp_pips", 100)
            signal_id = data.get("signal_id")
            
            # Verificar que es orden válida
            if order_type.upper() not in ["BUY", "SELL"]:
                return AgentResult(
                    agent_name=self.name,
                    success=False,
                    error=f"Tipo de orden inválido: {order_type}"
                )
            
            # Ejecutar orden
            result = self.connector.send_order(
                symbol=symbol,
                order_type=order_type.upper(),
                volume=volume,
                sl_pips=sl_pips,
                tp_pips=tp_pips,
                comment=f"IA Bot - Signal #{signal_id}" if signal_id else "IA Trading Bot"
            )
            
            # Registrar en base de datos
            if result.success:
                symbol_to_save = result.symbol
                self.storage.save_trade({
                    "ticket": result.ticket,
                    "symbol": symbol_to_save,
                    "type": order_type.upper(),
                    "volume": volume,
                    "open_price": result.price,
                    "sl": result.sl,
                    "tp": result.tp,
                    "opened_at": datetime.now(),
                    "status": "open",
                    "signal_id": signal_id
                })
                
                logger.info(f"Orden ejecutada: {order_type} {volume} {symbol_to_save} @ {result.price}")
            else:
                logger.warning(f"Orden fallida: {result.error}")
            
            # Log de agente
            self.storage.save_agent_log(
                agent_name=self.name,
                action=f"{order_type} {volume} {symbol}",
                result=f"Ticket: {result.ticket}" if result.success else result.error,
                success=result.success
            )

            
            return AgentResult(
                agent_name=self.name,
                success=result.success,
                data={
                    "ticket": result.ticket,
                    "symbol": symbol,
                    "type": order_type,
                    "volume": volume,
                    "price": result.price,
                    "sl": result.sl,
                    "tp": result.tp
                },
                error=result.error
            )
            
        except Exception as e:
            logger.error(f"Error en OrderAgent: {e}")
            return AgentResult(
                agent_name=self.name,
                success=False,
                error=str(e)
            )
    
    def get_open_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Obtiene posiciones abiertas"""
        if not self.connector.ensure_connected():
            return []
        
        positions = self.connector.get_positions(symbol)
        return [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": p.type,
                "volume": p.volume,
                "open_price": p.open_price,
                "current_price": p.current_price,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "open_time": p.open_time.isoformat()
            }
            for p in positions
        ]
    
    def close_position(self, ticket: int) -> bool:
        """Cierra una posición específica y actualiza la DB local"""
        if not self.connector.ensure_connected():
            return False
        
        success = self.connector.close_position(ticket)
        
        if success:
            # Intentar sincronizar este trade específico inmediatamente en la DB
            try:
                # Obtener deals recientes de MT5 para encontrar el de cierre
                deals = self.connector.get_history_deals(days=1)
                if deals:
                    self.storage.import_mt5_history(deals)
            except Exception as e:
                logger.warning(f"Error sincronizando cierre de trade #{ticket}: {e}")

            self.storage.save_agent_log(
                agent_name=self.name,
                action=f"CLOSE #{ticket}",
                result="Posición cerrada y DB sincronizada",
                success=True
            )
        
        return success
    
    def close_all_positions(self, symbol: Optional[str] = None) -> int:
        """Cierra todas las posiciones (de un símbolo o todas)"""
        positions = self.connector.get_positions(symbol)
        closed = 0
        
        for pos in positions:
            if self.close_position(pos.ticket):
                closed += 1
        
        logger.info(f"Cerradas {closed}/{len(positions)} posiciones")
        return closed
    
    def get_account_status(self) -> Dict[str, Any]:
        """Obtiene estado de la cuenta"""
        if not self.connector.ensure_connected():
            return {"error": "No conectado"}
        
        return self.connector.get_account_info() or {}
    
    def modify_position(self, ticket: int, sl: float, tp: float) -> bool:
        """Modifica SL/TP de una posición"""
        if not self.connector.ensure_connected():
            return False
        
        return self.connector.modify_position(ticket, sl, tp)


if __name__ == "__main__":
    print("=" * 50)
    print("Test de OrderAgent")
    print("=" * 50)
    
    agent = OrderAgent()
    
    if agent.connect():
        print("\n✅ Conectado a MT5")
        
        # Estado de cuenta
        status = agent.get_account_status()
        print(f"\n📊 Balance: {status.get('balance', 'N/A')}")
        print(f"   Equity: {status.get('equity', 'N/A')}")
        print(f"   Modo: {status.get('trade_mode', 'N/A')}")
        
        # Posiciones abiertas
        positions = agent.get_open_positions()
        print(f"\n📈 Posiciones abiertas: {len(positions)}")
        for pos in positions:
            print(f"   #{pos['ticket']}: {pos['type']} {pos['volume']} {pos['symbol']} P/L: {pos['profit']}")
        
        agent.disconnect()
    else:
        print("\n❌ No se pudo conectar a MT5")
        print("   Asegúrese de que MetaTrader 5 está abierto")
