"""
Price Service - Servicio de precios en tiempo real
"""

import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from loguru import logger
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from mt5.connector import MT5Connector
    from core.symbols import get_all_symbols
    MT5_AVAILABLE = True
except:
    MT5_AVAILABLE = False


@dataclass
class PriceTick:
    """Tick de precio"""
    symbol: str
    bid: float
    ask: float
    spread: float
    time: datetime


@dataclass
class OHLC:
    """Datos OHLC"""
    symbol: str
    timeframe: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class PriceService:
    """
    Servicio de precios en tiempo real.
    
    Features:
    - Actualización automática de precios
    - Cache de datos OHLC
    - Callbacks para nuevos precios
    - Multi-símbolo
    """
    
    TIMEFRAME_MAP = {
        "M1": 1, "M5": 5, "M15": 15, "M30": 30,
        "H1": 60, "H4": 240, "D1": 1440
    }
    
    def __init__(
        self,
        symbols: List[str] = None,
        update_interval: float = 15.0,
        cache_size: int = 500
    ):
        self.symbols = symbols or get_all_symbols()
        self.update_interval = update_interval
        self.cache_size = cache_size
        
        # Cache de precios
        self._price_cache: Dict[str, PriceTick] = {}
        self._ohlc_cache: Dict[str, Dict[str, List[OHLC]]] = {}
        
        # Control de threads
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Callbacks
        self._price_callbacks: List[Callable[[PriceTick], None]] = []
        self._ohlc_callbacks: List[Callable[[OHLC], None]] = []
        
        # Estado
        self._last_update: Optional[datetime] = None
        self._connected = False
        self._error_count = 0
        
        logger.info(f"PriceService inicializado para {len(self.symbols)} símbolos")
    
    def start(self):
        """Inicia el servicio de precios"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()
        logger.info("PriceService iniciado")
    
    def stop(self):
        """Detiene el servicio de precios"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("PriceService detenido")
    
    def _update_loop(self):
        """Loop principal de actualización"""
        while self._running:
            try:
                self._update_prices()
                self._update_ohlc()
                self._error_count = 0
                
            except Exception as e:
                self._error_count += 1
                logger.error(f"Error actualizando precios: {e}")
                
                if self._error_count >= 5:
                    logger.error("Demasiados errores, pausando 60s")
                    time.sleep(60)
            
            time.sleep(self.update_interval)
    
    def _update_prices(self):
        """Actualiza precios de todos los símbolos"""
        if not MT5_AVAILABLE:
            return
        
        connector = MT5Connector()
        if not connector.connect():
            self._connected = False
            return
        
        self._connected = True
        
        for symbol in self.symbols:
            try:
                tick = connector.get_symbol_tick(symbol)
                
                if tick:
                    price_tick = PriceTick(
                        symbol=symbol,
                        bid=tick.bid,
                        ask=tick.ask,
                        spread=round((tick.ask - tick.bid) * 10000, 1),
                        time=datetime.now()
                    )
                    
                    with self._lock:
                        self._price_cache[symbol] = price_tick
                    
                    # Notificar callbacks
                    for callback in self._price_callbacks:
                        try:
                            callback(price_tick)
                        except:
                            pass
                    
            except Exception as e:
                logger.warning(f"Error obteniendo precio de {symbol}: {e}")
        
        connector.disconnect()
        self._last_update = datetime.now()
    
    def _update_ohlc(self):
        """Actualiza datos OHLC"""
        if not MT5_AVAILABLE:
            return
        
        connector = MT5Connector()
        if not connector.connect():
            return
        
        for symbol in self.symbols:
            for tf_name, tf_value in self.TIMEFRAME_MAP.items():
                try:
                    data = connector.get_rates(symbol, tf_value, 10)
                    
                    if data is not None and len(data) > 0:
                        with self._lock:
                            if symbol not in self._ohlc_cache:
                                self._ohlc_cache[symbol] = {}
                            
                            self._ohlc_cache[symbol][tf_name] = [
                                OHLC(
                                    symbol=symbol,
                                    timeframe=tf_name,
                                    time=datetime.fromtimestamp(bar['time']),
                                    open=bar['open'],
                                    high=bar['high'],
                                    low=bar['low'],
                                    close=bar['close'],
                                    volume=bar['tick_volume']
                                )
                                for bar in data[-10:]
                            ]
                        
                except Exception:
                    pass
        
        connector.disconnect()
    
    def get_price(self, symbol: str) -> Optional[PriceTick]:
        """Obtiene precio actual de un símbolo"""
        with self._lock:
            return self._price_cache.get(symbol)
    
    def get_all_prices(self) -> Dict[str, PriceTick]:
        """Obtiene todos los precios actuales"""
        with self._lock:
            return self._price_cache.copy()
    
    def get_ohlc(self, symbol: str, timeframe: str = "M15") -> List[OHLC]:
        """Obtiene datos OHLC de un símbolo"""
        with self._lock:
            if symbol in self._ohlc_cache:
                return self._ohlc_cache[symbol].get(timeframe, [])
            return []
    
    def get_spread(self, symbol: str) -> float:
        """Obtiene spread actual de un símbolo"""
        price = self.get_price(symbol)
        return price.spread if price else 0.0
    
    def on_price(self, callback: Callable[[PriceTick], None]):
        """Registra callback para nuevos precios"""
        self._price_callbacks.append(callback)
    
    def on_ohlc(self, callback: Callable[[OHLC], None]):
        """Registra callback para nuevos datos OHLC"""
        self._ohlc_callbacks.append(callback)
    
    def is_connected(self) -> bool:
        """Verifica si está conectado a MT5"""
        return self._connected
    
    def get_status(self) -> Dict[str, Any]:
        """Obtiene estado del servicio"""
        return {
            "running": self._running,
            "connected": self._connected,
            "symbols": self.symbols,
            "cached_prices": len(self._price_cache),
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "error_count": self._error_count,
            "update_interval": self.update_interval
        }


# Instancia global
_price_service: Optional[PriceService] = None


def get_price_service() -> PriceService:
    """Obtiene instancia global del servicio de precios"""
    global _price_service
    if _price_service is None:
        _price_service = PriceService()
    return _price_service


def start_price_service(symbols: List[str] = None, interval: float = 15.0):
    """Inicia el servicio de precios global"""
    global _price_service
    _price_service = PriceService(symbols=symbols, update_interval=interval)
    _price_service.start()
    return _price_service


def stop_price_service():
    """Detiene el servicio de precios global"""
    global _price_service
    if _price_service:
        _price_service.stop()


if __name__ == "__main__":
    import time
    
    print("=" * 50)
    print("Test de PriceService")
    print("=" * 50)
    
    # Callback de ejemplo
    def on_new_price(tick: PriceTick):
        print(f"  {tick.symbol}: {tick.bid:.5f}/{tick.ask:.5f} (spread: {tick.spread})")
    
    service = PriceService(update_interval=5.0)
    service.on_price(on_new_price)
    
    service.start()
    
    print("\nEscuchando precios por 30 segundos...")
    time.sleep(30)
    
    print("\nEstado final:")
    print(service.get_status())
    
    service.stop()
    print("\n✅ Test completado")
