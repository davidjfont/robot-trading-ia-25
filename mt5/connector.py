"""
MT5 Connector - Conexión con MetaTrader 5
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from loguru import logger
import time
import yaml
import os

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    logger.warning("MetaTrader5 no instalado. Instale con: pip install MetaTrader5")

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


@dataclass
class Tick:
    """Datos de tick"""
    symbol: str
    bid: float
    ask: float
    time: datetime
    spread: float


@dataclass
class Position:
    """Posición abierta en MT5"""
    ticket: int
    symbol: str
    type: str  # BUY/SELL
    volume: float
    open_price: float
    current_price: float
    sl: float
    tp: float
    profit: float
    open_time: datetime


@dataclass
class OrderResult:
    """Resultado de una orden"""
    success: bool
    ticket: int
    order_type: str
    symbol: str
    volume: float
    price: float
    sl: float
    tp: float
    error: Optional[str] = None
    retcode: Optional[int] = None


class MT5Connector:
    """
    Conector para MetaTrader 5.
    
    Maneja la conexión, obtención de datos y envío de órdenes.
    
    Uso:
        connector = MT5Connector()
        if connector.connect():
            tick = connector.get_tick("EURUSD")
            result = connector.send_order("EURUSD", "BUY", 0.1)
    """
    
    TIMEFRAMES = {
        "M1": mt5.TIMEFRAME_M1 if MT5_AVAILABLE else 1,
        "M5": mt5.TIMEFRAME_M5 if MT5_AVAILABLE else 5,
        "M15": mt5.TIMEFRAME_M15 if MT5_AVAILABLE else 15,
        "M30": mt5.TIMEFRAME_M30 if MT5_AVAILABLE else 30,
        "H1": mt5.TIMEFRAME_H1 if MT5_AVAILABLE else 60,
        "H4": mt5.TIMEFRAME_H4 if MT5_AVAILABLE else 240,
        "D1": mt5.TIMEFRAME_D1 if MT5_AVAILABLE else 1440,
    }
    
    def __init__(self, config_path: str = "config.yaml"):
        """Inicializa el conector MT5"""
        self.config = self._load_config(config_path)
        self.connected = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        
        mt5_config = self.config.get("mt5", {})
        self.account = mt5_config.get("account")
        self.password = mt5_config.get("password")
        self.server = mt5_config.get("server")
        self.timeout = mt5_config.get("timeout", 60000)
        self.demo_mode = mt5_config.get("demo_mode", True)
        
        logger.info(f"MT5Connector inicializado. Cuenta: {self.account}")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Carga configuración"""
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            full_path = os.path.join(base_dir, config_path)
            
            with open(full_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception:
            return {}
    
    def connect(self) -> bool:
        """
        Establece conexión con MetaTrader 5
        
        Returns:
            True si la conexión fue exitosa
        """
        if not MT5_AVAILABLE:
            logger.error("MetaTrader5 no está instalado")
            return False
        
        try:
            # Inicializar MT5
            if not mt5.initialize():
                logger.error(f"Error inicializando MT5: {mt5.last_error()}")
                return False
            
            # Login si hay credenciales
            if self.account and self.password and self.server:
                authorized = mt5.login(
                    login=int(self.account),
                    password=str(self.password),
                    server=str(self.server)
                )
                
                if not authorized:
                    error_code = mt5.last_error()
                    logger.error(f"Error en login: {error_code}")
                    if error_code[0] == mt5.RES_E_INVALID_ACCOUNT:
                        logger.error("  👉 Cuenta inválida o no existe")
                    elif error_code[0] == mt5.RES_E_INVALID_PASSWORD:
                        logger.error("  👉 Contraseña incorrecta")
                    elif error_code[0] == mt5.RES_E_CONNECT_FAILED:
                        logger.error("  👉 No se pudo conectar al servidor")
                    return False
            
            self.connected = True
            self._reconnect_attempts = 0
            
            # Información de la cuenta
            account_info = mt5.account_info()
            if account_info:
                logger.info(f"Conectado a MT5. Balance: {account_info.balance}, Servidor: {account_info.server}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error conectando a MT5: {e}")
            return False
    
    def disconnect(self):
        """Cierra la conexión con MT5"""
        if self.connected and MT5_AVAILABLE:
            try:
                mt5.shutdown()
            except:
                pass
        self.connected = False
        logger.info("Desconectado de MT5")

    
    def ensure_connected(self) -> bool:
        """Asegura que hay conexión activa, reconecta si es necesario"""
        if not self.connected:
            return self.connect()
        
        # Verificar que la conexión sigue activa sin ser agresivo
        if MT5_AVAILABLE:
            try:
                # terminal_info() es ligero, sirve como heartbeat
                terminal_info = mt5.terminal_info()
                if terminal_info is None:
                    # Solo intentar reconectar si realmente se perdió la terminal
                    return self._reconnect()
                
                # Verificar si está logueado (conectado al servidor)
                if not terminal_info.connected:
                     return self._reconnect()
                     
                return True
            except Exception as e:
                logger.debug(f"Error en heartbeat MT5: {e}")
                return self._reconnect()
        
        return False

    
    def _reconnect(self) -> bool:
        """Intenta reconectar a MT5"""
        self._reconnect_attempts += 1
        
        if self._reconnect_attempts > self._max_reconnect_attempts:
            logger.error(f"Máximo de intentos de reconexión alcanzado ({self._max_reconnect_attempts})")
            return False
        
        logger.info(f"Intento de reconexión {self._reconnect_attempts}/{self._max_reconnect_attempts}")
        time.sleep(2 ** self._reconnect_attempts)  # Backoff exponencial
        
        self.disconnect()
        return self.connect()
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Obtiene información de la cuenta"""
        if not self.ensure_connected():
            return None
        
        info = mt5.account_info()
        if info:
            return {
                "login": info.login,
                "balance": info.balance,
                "equity": info.equity,
                "margin": info.margin,
                "free_margin": info.margin_free,
                "leverage": info.leverage,
                "profit": info.profit,
                "server": info.server,
                "currency": info.currency,
                "trade_mode": "demo" if info.trade_mode == 0 else "real"
            }
        return None
    
    def get_tick(self, symbol: str) -> Optional[Tick]:
        """
        Obtiene el tick actual de un símbolo
        
        Args:
            symbol: Par de divisas (ej: "EURUSD")
        """
        if not self.ensure_connected():
            return None
        
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            return Tick(
                symbol=symbol,
                bid=tick.bid,
                ask=tick.ask,
                time=datetime.fromtimestamp(tick.time),
                spread=round((tick.ask - tick.bid) / 0.0001, 1)
            )
        return None
    
    # Alias for compatibility
    def get_symbol_tick(self, symbol: str) -> Optional[Tick]:
        """Alias for get_tick()"""
        return self.get_tick(symbol)

    def get_symbol_info(self, symbol: str) -> Optional[Any]:
        """Obtiene información detallada de un símbolo"""
        if not self.ensure_connected():
            return None
        return mt5.symbol_info(symbol)


    
    def get_rates(
        self, 
        symbol: str, 
        timeframe: str = "M15", 
        count: int = 100
    ) -> Optional['pd.DataFrame']:
        """
        Obtiene velas históricas
        
        Args:
            symbol: Par de divisas
            timeframe: Período (M1, M5, M15, H1, H4, D1)
            count: Número de velas
        """
        if not self.ensure_connected() or not PANDAS_AVAILABLE:
            return None
        
        tf = self.TIMEFRAMES.get(timeframe.upper(), self.TIMEFRAMES["M15"])
        
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            return df
        
        return None
    
    def get_symbol_data(self, symbol: str, timeframe: str = "M15", count: int = 100) -> Optional[List[Dict[str, Any]]]:
        """Alias para get_rates que retorna lista de dicts para compatibilidad"""
        df = self.get_rates(symbol, timeframe, count)
        if df is not None:
            return df.to_dict('records')
        return None
    
    def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """Obtiene posiciones abiertas"""
        if not self.ensure_connected():
            return []
        
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()
        
        if positions is None:
            return []
        
        result = []
        for pos in positions:
            result.append(Position(
                ticket=pos.ticket,
                symbol=pos.symbol,
                type="BUY" if pos.type == 0 else "SELL",
                volume=pos.volume,
                open_price=pos.price_open,
                current_price=pos.price_current,
                sl=pos.sl,
                tp=pos.tp,
                profit=pos.profit,
                open_time=datetime.fromtimestamp(pos.time)
            ))
        
        return result

    def get_history_deals(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Obtiene el historial de ejecuciones (deals) de los últimos X días.
        Útil para detectar trades cerrados.
        """
        if not self.ensure_connected():
            return []
            
        from_date = datetime.now() - timedelta(days=days)
        deals = mt5.history_deals_get(from_date, datetime.now())
        
        if deals is None or len(deals) == 0:
            return []
            
        result = []
        for d in deals:
            # Solo nos interesan deals que no sean depósitos/retiros (type 0=buy, 1=sell)
            # Y que tengan un ticket de posición asociado
            if d.type in [0, 1] and d.position_id != 0:
                result.append({
                    "ticket": d.position_id,
                    "symbol": d.symbol,
                    "type": "BUY" if d.type == 0 else "SELL",
                    "volume": d.volume,
                    "price": d.price,
                    "profit": d.profit,
                    "commission": d.commission,
                    "swap": d.swap,
                    "timestamp": datetime.fromtimestamp(d.time),
                    "entry_type": d.entry # 0=EN_ENTRY_IN, 1=EN_ENTRY_OUT, 2=EN_ENTRY_INOUT
                })
        
        return result
    
    def send_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        sl_pips: float = 50,
        tp_pips: float = 100,
        comment: str = "IA Trading Bot"
    ) -> OrderResult:
        """
        Envía una orden al mercado
        
        Args:
            symbol: Par de divisas
            order_type: "BUY" o "SELL"
            volume: Volumen en lotes
            sl_pips: Stop loss en pips
            tp_pips: Take profit en pips
            comment: Comentario de la orden
        """
        if not self.ensure_connected():
            return OrderResult(
                success=False,
                ticket=0,
                order_type=order_type,
                symbol=symbol,
                volume=volume,
                price=0,
                sl=0,
                tp=0,
                error="No conectado a MT5"
            )
        
        # Verificar modo demo
        account_info = mt5.account_info()
        if self.demo_mode and account_info.trade_mode != 0:
            return OrderResult(
                success=False,
                ticket=0,
                order_type=order_type,
                symbol=symbol,
                volume=volume,
                price=0,
                sl=0,
                tp=0,
                error="Solo se permiten operaciones en cuenta DEMO"
            )
        
        # Obtener información del símbolo
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return OrderResult(
                success=False,
                ticket=0,
                order_type=order_type,
                symbol=symbol,
                volume=volume,
                price=0,
                sl=0,
                tp=0,
                error=f"Símbolo {symbol} no encontrado"
            )
        
        if not symbol_info.visible:
            mt5.symbol_select(symbol, True)
        
        # Obtener precio actual
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return OrderResult(
                success=False,
                ticket=0,
                order_type=order_type,
                symbol=symbol,
                volume=volume,
                price=0,
                sl=0,
                tp=0,
                error="No se pudo obtener precio"
            )
        
        # Configurar orden
        point = symbol_info.point
        
        if order_type.upper() == "BUY":
            price = tick.ask
            sl = price - sl_pips * point * 10
            tp = price + tp_pips * point * 10
            mt5_type = mt5.ORDER_TYPE_BUY
        else:
            price = tick.bid
            sl = price + sl_pips * point * 10
            tp = price - tp_pips * point * 10
            mt5_type = mt5.ORDER_TYPE_SELL
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 123456,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        # Enviar orden
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            # Mapeo de errores comunes para diagnóstico fácil
            error_reasons = {
                10004: "Requote",
                10006: "Rechazado",
                10013: "Símbolo inválido",
                10014: "Volumen inválido",
                10015: "Precio inválido",
                10018: "Mercado cerrado",
                10019: "Fondos insuficientes",
                10026: "Autotrading deshabilitado en la terminal",
                10027: "Autotrading deshabilitado para la cuenta",
            }
            reason = error_reasons.get(result.retcode, result.comment)
            error_msg = f"Error {result.retcode}: {reason}"
            logger.error(f"Orden fallida para {symbol}: {error_msg}")
            
            return OrderResult(
                success=False,
                ticket=0,
                order_type=order_type,
                symbol=symbol,
                volume=volume,
                price=price,
                sl=sl,
                tp=tp,
                error=error_msg,
                retcode=result.retcode
            )
        
        logger.info(f"Orden ejecutada: {order_type} {volume} {symbol} @ {result.price}")
        
        return OrderResult(
            success=True,
            ticket=result.order,
            order_type=order_type,
            symbol=symbol,
            volume=volume,
            price=result.price,
            sl=sl,
            tp=tp,
            retcode=result.retcode
        )
    
    def close_position(self, ticket: int) -> bool:
        """Cierra una posición por su ticket"""
        if not self.ensure_connected():
            return False
        
        position = mt5.positions_get(ticket=ticket)
        if not position:
            logger.warning(f"Posición {ticket} no encontrada")
            return False
        
        pos = position[0]
        
        # Determinar tipo de cierre
        close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(pos.symbol).bid if pos.type == 0 else mt5.symbol_info_tick(pos.symbol).ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 123456,
            "comment": "Close by IA Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Posición {ticket} cerrada")
            return True
        else:
            logger.error(f"Error cerrando posición: {result.comment}")
            return False
    
    def modify_position(self, ticket: int, sl: float, tp: float) -> bool:
        """Modifica SL/TP de una posición"""
        if not self.ensure_connected():
            return False
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": sl,
            "tp": tp,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Posición {ticket} modificada: SL={sl}, TP={tp}")
            return True
        else:
            logger.error(f"Error modificando posición: {result.comment}")
            return False


if __name__ == "__main__":
    print("=" * 50)
    print("Test de MT5Connector")
    print("=" * 50)
    
    if not MT5_AVAILABLE:
        print("❌ MetaTrader5 no disponible")
        print("   Instale con: pip install MetaTrader5")
        exit(1)
    
    connector = MT5Connector()
    
    if connector.connect():
        print("\n✅ Conectado a MT5")
        
        # Info de cuenta
        info = connector.get_account_info()
        if info:
            print(f"\n📊 Cuenta: {info['login']}")
            print(f"   Balance: {info['balance']} {info['currency']}")
            print(f"   Equity: {info['equity']}")
            print(f"   Modo: {info['trade_mode']}")
        
        # Obtener tick
        tick = connector.get_tick("EURUSD")
        if tick:
            print(f"\n💹 EURUSD: Bid={tick.bid:.5f}, Ask={tick.ask:.5f}, Spread={tick.spread}")
        
        # Posiciones abiertas
        positions = connector.get_positions()
        print(f"\n📈 Posiciones abiertas: {len(positions)}")
        
        connector.disconnect()
    else:
        print("\n❌ No se pudo conectar a MT5")
        print("   Asegúrese de que MetaTrader 5 está abierto y logueado")
