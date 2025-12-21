"""
Backtesting Engine - Motor de backtesting para validación de estrategias
"""

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import numpy as np
from loguru import logger

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


class OrderType(Enum):
    """Tipo de orden"""
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class SimulatedOrder:
    """Orden simulada en backtest"""
    id: int
    symbol: str
    order_type: OrderType
    volume: float
    open_price: float
    open_time: datetime
    sl: float
    tp: float
    close_price: Optional[float] = None
    close_time: Optional[datetime] = None
    profit: float = 0.0
    status: str = "open"  # open, closed


@dataclass
class BacktestResult:
    """Resultado del backtest"""
    initial_balance: float
    final_balance: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_profit: float
    total_loss: float
    net_profit: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    profit_factor: float
    avg_trade_profit: float
    avg_winning_trade: float
    avg_losing_trade: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    total_bars: int
    trades: List[SimulatedOrder] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "initial_balance": self.initial_balance,
            "final_balance": round(self.final_balance, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 4),
            "total_profit": round(self.total_profit, 2),
            "total_loss": round(self.total_loss, 2),
            "net_profit": round(self.net_profit, 2),
            "net_profit_pct": round((self.net_profit / self.initial_balance) * 100, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "profit_factor": round(self.profit_factor, 3) if self.profit_factor != float('inf') else "∞",
            "avg_trade_profit": round(self.avg_trade_profit, 2),
            "avg_winning_trade": round(self.avg_winning_trade, 2),
            "avg_losing_trade": round(self.avg_losing_trade, 2),
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "total_bars": self.total_bars
        }


class BacktestEngine:
    """
    Motor de backtesting para validar estrategias de trading.
    
    Simula la ejecución de trades usando datos históricos.
    """
    
    def __init__(
        self,
        initial_balance: float = 10000,
        commission: float = 0.0,  # Por trade
        spread_pips: float = 1.0,
        pip_value: float = 10.0  # Por lote estándar
    ):
        """
        Args:
            initial_balance: Balance inicial de la cuenta
            commission: Comisión por trade
            spread_pips: Spread en pips
            pip_value: Valor del pip por lote
        """
        self.initial_balance = initial_balance
        self.commission = commission
        self.spread_pips = spread_pips
        self.pip_value = pip_value
        
        # Estado del backtest
        self.balance = initial_balance
        self.equity = initial_balance
        self.orders: List[SimulatedOrder] = []
        self.open_orders: List[SimulatedOrder] = []
        self.equity_curve: List[float] = []
        self._order_counter = 0
        
        logger.info(f"BacktestEngine inicializado. Balance: {initial_balance}")
    
    def reset(self):
        """Resetea el estado del backtest"""
        self.balance = self.initial_balance
        self.equity = self.initial_balance
        self.orders = []
        self.open_orders = []
        self.equity_curve = []
        self._order_counter = 0
    
    def open_order(
        self,
        symbol: str,
        order_type: OrderType,
        volume: float,
        price: float,
        sl: float,
        tp: float,
        timestamp: datetime
    ) -> SimulatedOrder:
        """Abre una orden simulada"""
        self._order_counter += 1
        
        # Aplicar spread
        if order_type == OrderType.BUY:
            adjusted_price = price + (self.spread_pips * 0.0001)  # Ask
        else:
            adjusted_price = price - (self.spread_pips * 0.0001)  # Bid
        
        order = SimulatedOrder(
            id=self._order_counter,
            symbol=symbol,
            order_type=order_type,
            volume=volume,
            open_price=adjusted_price,
            open_time=timestamp,
            sl=sl,
            tp=tp
        )
        
        self.open_orders.append(order)
        self.orders.append(order)
        
        logger.debug(f"Orden abierta: {order_type.value} {volume} {symbol} @ {adjusted_price:.5f}")
        
        return order
    
    def close_order(self, order: SimulatedOrder, price: float, timestamp: datetime):
        """Cierra una orden simulada"""
        if order.status == "closed":
            return
        
        order.close_price = price
        order.close_time = timestamp
        order.status = "closed"
        
        # Calcular profit
        if order.order_type == OrderType.BUY:
            pips = (price - order.open_price) / 0.0001
        else:
            pips = (order.open_price - price) / 0.0001
        
        order.profit = pips * self.pip_value * order.volume - self.commission
        self.balance += order.profit
        
        # Remover de órdenes abiertas
        if order in self.open_orders:
            self.open_orders.remove(order)
        
        logger.debug(f"Orden cerrada: #{order.id} Profit: {order.profit:.2f}")
    
    def check_sl_tp(self, high: float, low: float, timestamp: datetime):
        """Verifica si alguna orden ha alcanzado SL o TP"""
        for order in self.open_orders.copy():
            if order.order_type == OrderType.BUY:
                # BUY: SL se activa con low, TP con high
                if low <= order.sl:
                    self.close_order(order, order.sl, timestamp)
                elif high >= order.tp:
                    self.close_order(order, order.tp, timestamp)
            else:
                # SELL: SL se activa con high, TP con low
                if high >= order.sl:
                    self.close_order(order, order.sl, timestamp)
                elif low <= order.tp:
                    self.close_order(order, order.tp, timestamp)
    
    def update_equity(self, current_price: float):
        """Actualiza el equity con posiciones abiertas"""
        unrealized = 0.0
        
        for order in self.open_orders:
            if order.order_type == OrderType.BUY:
                pips = (current_price - order.open_price) / 0.0001
            else:
                pips = (order.open_price - current_price) / 0.0001
            
            unrealized += pips * self.pip_value * order.volume
        
        self.equity = self.balance + unrealized
        self.equity_curve.append(self.equity)
    
    def run(
        self,
        data: 'pd.DataFrame',
        strategy: Callable[['pd.DataFrame', int], Optional[Dict[str, Any]]],
        symbol: str = "EURUSD"
    ) -> BacktestResult:
        """
        Ejecuta el backtest con los datos y estrategia proporcionados
        
        Args:
            data: DataFrame con columnas 'open', 'high', 'low', 'close', 'time'
            strategy: Función que recibe (data, index) y retorna señal o None
            symbol: Símbolo a tradear
        
        Returns:
            BacktestResult con métricas
        """
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas es requerido para backtesting")
        
        self.reset()
        
        logger.info(f"Iniciando backtest con {len(data)} barras")
        
        # Normalizar columnas
        data.columns = data.columns.str.lower()
        
        for i in range(50, len(data)):  # Empezar después de calentamiento
            row = data.iloc[i]
            timestamp = row.get('time', datetime.now())
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)
            
            high = row['high']
            low = row['low']
            close = row['close']
            
            # Verificar SL/TP
            self.check_sl_tp(high, low, timestamp)
            
            # Obtener señal de la estrategia
            signal = strategy(data.iloc[:i+1], i)
            
            if signal and len(self.open_orders) == 0:  # Solo si no hay órdenes abiertas
                order_type = OrderType.BUY if signal.get("type") == "BUY" else OrderType.SELL
                volume = signal.get("volume", 0.1)
                sl_pips = signal.get("sl_pips", 50)
                tp_pips = signal.get("tp_pips", 100)
                
                # Calcular SL y TP
                if order_type == OrderType.BUY:
                    sl = close - sl_pips * 0.0001
                    tp = close + tp_pips * 0.0001
                else:
                    sl = close + sl_pips * 0.0001
                    tp = close - tp_pips * 0.0001
                
                self.open_order(symbol, order_type, volume, close, sl, tp, timestamp)
            
            # Actualizar equity
            self.update_equity(close)
        
        # Cerrar órdenes abiertas al final
        if self.open_orders:
            last_row = data.iloc[-1]
            last_price = last_row['close']
            last_time = last_row.get('time', datetime.now())
            for order in self.open_orders.copy():
                self.close_order(order, last_price, last_time)
        
        return self._calculate_results(len(data))
    
    def _calculate_results(self, total_bars: int) -> BacktestResult:
        """Calcula métricas del backtest"""
        closed_orders = [o for o in self.orders if o.status == "closed"]
        
        if not closed_orders:
            return BacktestResult(
                initial_balance=self.initial_balance,
                final_balance=self.balance,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_profit=0.0,
                total_loss=0.0,
                net_profit=0.0,
                max_drawdown=0.0,
                max_drawdown_pct=0.0,
                sharpe_ratio=0.0,
                profit_factor=0.0,
                avg_trade_profit=0.0,
                avg_winning_trade=0.0,
                avg_losing_trade=0.0,
                max_consecutive_wins=0,
                max_consecutive_losses=0,
                total_bars=total_bars,
                trades=closed_orders,
                equity_curve=self.equity_curve
            )
        
        # Calcular métricas
        profits = [o.profit for o in closed_orders]
        winners = [p for p in profits if p > 0]
        losers = [p for p in profits if p < 0]
        
        total_profit = sum(winners)
        total_loss = abs(sum(losers))
        
        # Max drawdown
        equity_array = np.array(self.equity_curve)
        if len(equity_array) > 0:
            peak = np.maximum.accumulate(equity_array)
            drawdown = peak - equity_array
            max_drawdown = np.max(drawdown)
            max_drawdown_pct = (max_drawdown / np.max(peak)) * 100 if np.max(peak) > 0 else 0
        else:
            max_drawdown = 0.0
            max_drawdown_pct = 0.0
        
        # Sharpe ratio (simplificado)
        if len(profits) > 1:
            returns = np.array(profits) / self.initial_balance
            sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
        else:
            sharpe = 0.0
        
        # Profit factor
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        
        # Consecutive wins/losses
        max_wins = max_losses = current_wins = current_losses = 0
        for p in profits:
            if p > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
        
        return BacktestResult(
            initial_balance=self.initial_balance,
            final_balance=self.balance,
            total_trades=len(closed_orders),
            winning_trades=len(winners),
            losing_trades=len(losers),
            win_rate=len(winners) / len(closed_orders) if closed_orders else 0,
            total_profit=total_profit,
            total_loss=total_loss,
            net_profit=self.balance - self.initial_balance,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe,
            profit_factor=profit_factor,
            avg_trade_profit=sum(profits) / len(profits),
            avg_winning_trade=sum(winners) / len(winners) if winners else 0,
            avg_losing_trade=sum(losers) / len(losers) if losers else 0,
            max_consecutive_wins=max_wins,
            max_consecutive_losses=max_losses,
            total_bars=total_bars,
            trades=closed_orders,
            equity_curve=self.equity_curve
        )


def simple_moving_average_strategy(data: 'pd.DataFrame', index: int) -> Optional[Dict[str, Any]]:
    """Estrategia simple de cruce de medias móviles para testing"""
    if index < 50:
        return None
    
    close = data['close']
    sma_fast = close.rolling(window=10).mean().iloc[-1]
    sma_slow = close.rolling(window=30).mean().iloc[-1]
    
    prev_fast = close.rolling(window=10).mean().iloc[-2]
    prev_slow = close.rolling(window=30).mean().iloc[-2]
    
    # Cruce alcista
    if prev_fast <= prev_slow and sma_fast > sma_slow:
        return {"type": "BUY", "volume": 0.1, "sl_pips": 30, "tp_pips": 60}
    
    # Cruce bajista
    if prev_fast >= prev_slow and sma_fast < sma_slow:
        return {"type": "SELL", "volume": 0.1, "sl_pips": 30, "tp_pips": 60}
    
    return None


if __name__ == "__main__":
    print("=" * 50)
    print("Test de Backtesting Engine")
    print("=" * 50)
    
    if not PANDAS_AVAILABLE:
        print("❌ pandas no disponible")
        exit(1)
    
    # Generar datos de prueba
    np.random.seed(42)
    n = 1000
    
    base = 1.1000
    returns = np.random.randn(n) * 0.002 + 0.00005  # Pequeño drift positivo
    closes = base * np.cumprod(1 + returns)
    
    data = pd.DataFrame({
        "time": pd.date_range(start="2024-01-01", periods=n, freq="H"),
        "open": np.roll(closes, 1),
        "high": closes * (1 + np.abs(np.random.randn(n)) * 0.001),
        "low": closes * (1 - np.abs(np.random.randn(n)) * 0.001),
        "close": closes
    })
    
    # Ejecutar backtest
    engine = BacktestEngine(initial_balance=1000.0)
    result = engine.run(data, simple_moving_average_strategy, "EURUSD")
    
    print(f"\n📊 Resultados del Backtest")
    print("-" * 40)
    
    metrics = result.to_dict()
    for key, value in metrics.items():
        if key not in ["trades", "equity_curve"]:
            print(f"  {key}: {value}")
