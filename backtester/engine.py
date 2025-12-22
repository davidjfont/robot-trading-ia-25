"""
Backtesting Engine v2.0 - Motor mejorado con datos MT5 y multi-símbolo
"""

from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import numpy as np
from loguru import logger
import random

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

# Importar MT5 connector si disponible
try:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from mt5.connector import MT5Connector
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False


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
    pips: float = 0.0
    status: str = "open"  # open, closed


@dataclass
class BacktestResult:
    """Resultado del backtest"""
    symbol: str
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
    sortino_ratio: float
    profit_factor: float
    expectancy: float
    avg_trade_profit: float
    avg_winning_trade: float
    avg_losing_trade: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    total_bars: int
    trades: List[SimulatedOrder] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    buy_hold_return: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "initial_balance": self.initial_balance,
            "final_balance": round(self.final_balance, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 4),
            "total_profit": round(self.total_profit, 2),
            "total_loss": round(self.total_loss, 2),
            "net_profit": round(self.net_profit, 2),
            "net_profit_pct": round((self.net_profit / self.initial_balance) * 100, 2) if self.initial_balance > 0 else 0,
            "max_drawdown": round(self.max_drawdown, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "sortino_ratio": round(self.sortino_ratio, 3),
            "profit_factor": round(self.profit_factor, 3) if self.profit_factor != float('inf') else "∞",
            "expectancy": round(self.expectancy, 2),
            "avg_trade_profit": round(self.avg_trade_profit, 2),
            "avg_winning_trade": round(self.avg_winning_trade, 2),
            "avg_losing_trade": round(self.avg_losing_trade, 2),
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "total_bars": self.total_bars,
            "buy_hold_return": round(self.buy_hold_return, 2)
        }


@dataclass
class MultiSymbolResult:
    """Resultado de backtest multi-símbolo"""
    symbols: List[str]
    combined_equity_curve: List[float]
    total_net_profit: float
    total_trades: int
    overall_win_rate: float
    overall_sharpe: float
    overall_max_dd: float
    symbol_results: Dict[str, BacktestResult] = field(default_factory=dict)
    
    def best_performing_symbol(self) -> str:
        """Retorna el símbolo con mejor rendimiento"""
        if not self.symbol_results:
            return ""
        return max(self.symbol_results.keys(), key=lambda s: self.symbol_results[s].net_profit)
    
    def worst_performing_symbol(self) -> str:
        """Retorna el símbolo con peor rendimiento"""
        if not self.symbol_results:
            return ""
        return min(self.symbol_results.keys(), key=lambda s: self.symbol_results[s].net_profit)


class BacktestEngine:
    """
    Motor de backtesting v2.0 para validar estrategias de trading.
    
    Features:
    - Datos históricos de MT5
    - Multi-símbolo
    - Monte Carlo simulation
    - Walk-forward optimization
    """
    
    # Timeframe mapping para MT5
    TIMEFRAME_MAP = {
        "M1": 1, "M5": 5, "M15": 15, "M30": 30,
        "H1": 60, "H4": 240, "D1": 1440
    }
    
    def __init__(
        self,
        initial_balance: float = 10000,
        commission: float = 0.0,
        spread_pips: float = 1.0,
        pip_value: float = 10.0,
        default_lot_size: float = 0.1,
        sl_pips: float = 50,
        tp_pips: float = 100
    ):
        self.initial_balance = initial_balance
        self.commission = commission
        self.spread_pips = spread_pips
        self.pip_value = pip_value
        self.default_lot_size = default_lot_size
        self.default_sl_pips = sl_pips
        self.default_tp_pips = tp_pips
        
        # Estado
        self.balance = initial_balance
        self.equity = initial_balance
        self.orders: List[SimulatedOrder] = []
        self.open_orders: List[SimulatedOrder] = []
        self.equity_curve: List[float] = []
        self._order_counter = 0
        
        logger.info(f"BacktestEngine v2.0 inicializado. Balance: {initial_balance}")
    
    def reset(self):
        """Resetea el estado del backtest"""
        self.balance = self.initial_balance
        self.equity = self.initial_balance
        self.orders = []
        self.open_orders = []
        self.equity_curve = []
        self._order_counter = 0
    
    def get_mt5_data(
        self,
        symbol: str,
        timeframe: str = "M15",
        num_bars: int = 1000
    ) -> Optional['pd.DataFrame']:
        """Obtiene datos históricos de MT5"""
        if not MT5_AVAILABLE:
            logger.warning("MT5 no disponible, usando datos simulados")
            return None
        
        try:
            connector = MT5Connector()
            if not connector.connect():
                return None
            
            tf_value = self.TIMEFRAME_MAP.get(timeframe, 15)
            data = connector.get_rates(symbol, tf_value, num_bars)
            connector.disconnect()
            
            if data is not None and len(data) > 0:
                df = pd.DataFrame(data)
                df['time'] = pd.to_datetime(df['time'], unit='s')
                return df
            
            return None
            
        except Exception as e:
            logger.error(f"Error obteniendo datos MT5: {e}")
            return None
    
    def generate_sample_data(self, num_bars: int = 1000, trend: float = 0.0001) -> 'pd.DataFrame':
        """Genera datos de ejemplo para backtesting"""
        np.random.seed(42)
        
        base = 1.1000
        returns = np.random.randn(num_bars) * 0.002 + trend
        closes = base * np.cumprod(1 + returns)
        
        return pd.DataFrame({
            "time": pd.date_range(start="2024-01-01", periods=num_bars, freq="15min"),
            "open": np.roll(closes, 1),
            "high": closes * (1 + np.abs(np.random.randn(num_bars)) * 0.001),
            "low": closes * (1 - np.abs(np.random.randn(num_bars)) * 0.001),
            "close": closes,
            "tick_volume": np.random.randint(100, 1000, num_bars)
        })
    
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
            adjusted_price = price + (self.spread_pips * 0.0001)
        else:
            adjusted_price = price - (self.spread_pips * 0.0001)
        
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
        
        return order
    
    def close_order(self, order: SimulatedOrder, price: float, timestamp: datetime):
        """Cierra una orden simulada"""
        if order.status == "closed":
            return
        
        order.close_price = price
        order.close_time = timestamp
        order.status = "closed"
        
        # Calcular profit y pips
        pip_multiplier = 100 if "JPY" in order.symbol else 10000
        
        if order.order_type == OrderType.BUY:
            order.pips = (price - order.open_price) * pip_multiplier
        else:
            order.pips = (order.open_price - price) * pip_multiplier
        
        order.profit = order.pips * self.pip_value * order.volume / 10 - self.commission
        self.balance += order.profit
        
        if order in self.open_orders:
            self.open_orders.remove(order)
    
    def check_sl_tp(self, high: float, low: float, timestamp: datetime):
        """Verifica si alguna orden ha alcanzado SL o TP"""
        for order in self.open_orders.copy():
            if order.order_type == OrderType.BUY:
                if low <= order.sl:
                    self.close_order(order, order.sl, timestamp)
                elif high >= order.tp:
                    self.close_order(order, order.tp, timestamp)
            else:
                if high >= order.sl:
                    self.close_order(order, order.sl, timestamp)
                elif low <= order.tp:
                    self.close_order(order, order.tp, timestamp)
    
    def update_equity(self, current_price: float):
        """Actualiza el equity con posiciones abiertas"""
        unrealized = 0.0
        
        for order in self.open_orders:
            pip_multiplier = 100 if "JPY" in order.symbol else 10000
            
            if order.order_type == OrderType.BUY:
                pips = (current_price - order.open_price) * pip_multiplier
            else:
                pips = (order.open_price - current_price) * pip_multiplier
            
            unrealized += pips * self.pip_value * order.volume / 10
        
        self.equity = self.balance + unrealized
        self.equity_curve.append(self.equity)
    
    def run(
        self,
        data: 'pd.DataFrame' = None,
        strategy: Callable = None,
        symbol: str = "EURUSD"
    ) -> BacktestResult:
        """Ejecuta el backtest"""
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas es requerido para backtesting")
        
        self.reset()
        
        # Obtener datos si no se proporcionan
        if data is None:
            data = self.get_mt5_data(symbol)
            if data is None:
                data = self.generate_sample_data()
        
        # Usar estrategia por defecto si no se proporciona
        if strategy is None:
            strategy = ema_crossover_strategy
        
        logger.info(f"Iniciando backtest {symbol} con {len(data)} barras")
        
        # Normalizar columnas
        data.columns = data.columns.str.lower()
        
        # Buy and hold para comparación
        first_price = data['close'].iloc[50]
        last_price = data['close'].iloc[-1]
        buy_hold = ((last_price - first_price) / first_price) * self.initial_balance
        
        for i in range(50, len(data)):
            row = data.iloc[i]
            timestamp = row.get('time', datetime.now())
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)
            
            high = row['high']
            low = row['low']
            close = row['close']
            
            # Verificar SL/TP
            self.check_sl_tp(high, low, timestamp)
            
            # Obtener señal
            signal = strategy(data.iloc[:i+1], i)
            
            if signal and len(self.open_orders) == 0:
                order_type = OrderType.BUY if signal.get("type") == "BUY" else OrderType.SELL
                volume = signal.get("volume", self.default_lot_size)
                sl_pips = signal.get("sl_pips", self.default_sl_pips)
                tp_pips = signal.get("tp_pips", self.default_tp_pips)
                
                pip_size = 0.01 if "JPY" in symbol else 0.0001
                
                if order_type == OrderType.BUY:
                    sl = close - sl_pips * pip_size
                    tp = close + tp_pips * pip_size
                else:
                    sl = close + sl_pips * pip_size
                    tp = close - tp_pips * pip_size
                
                self.open_order(symbol, order_type, volume, close, sl, tp, timestamp)
            
            self.update_equity(close)
        
        # Cerrar órdenes abiertas
        if self.open_orders:
            last_row = data.iloc[-1]
            for order in self.open_orders.copy():
                self.close_order(order, last_row['close'], last_row.get('time', datetime.now()))
        
        result = self._calculate_results(symbol, len(data))
        result.buy_hold_return = buy_hold
        
        return result
    
    def run_multi_symbol(
        self,
        symbols: List[str],
        strategy: Callable = None,
        timeframe: str = "M15",
        num_bars: int = 1000
    ) -> MultiSymbolResult:
        """Ejecuta backtest en múltiples símbolos"""
        
        results = {}
        all_equity_curves = []
        
        for symbol in symbols:
            logger.info(f"Backtesting {symbol}...")
            
            # Resetear para cada símbolo
            data = self.get_mt5_data(symbol, timeframe, num_bars)
            if data is None:
                data = self.generate_sample_data(num_bars)
            
            result = self.run(data, strategy, symbol)
            results[symbol] = result
            
            # Normalizar equity curve
            if result.equity_curve:
                normalized = [e / result.initial_balance for e in result.equity_curve]
                all_equity_curves.append(normalized)
        
        # Combinar equity curves (promedio)
        if all_equity_curves:
            min_len = min(len(ec) for ec in all_equity_curves)
            combined = [
                sum(ec[i] for ec in all_equity_curves) / len(all_equity_curves) * self.initial_balance
                for i in range(min_len)
            ]
        else:
            combined = []
        
        # Calcular métricas agregadas
        total_profit = sum(r.net_profit for r in results.values())
        total_trades = sum(r.total_trades for r in results.values())
        
        if total_trades > 0:
            total_wins = sum(r.winning_trades for r in results.values())
            overall_wr = total_wins / total_trades
        else:
            overall_wr = 0
        
        # Sharpe promedio
        sharpes = [r.sharpe_ratio for r in results.values() if r.sharpe_ratio != 0]
        overall_sharpe = np.mean(sharpes) if sharpes else 0
        
        # Max DD (peor)
        overall_dd = max(r.max_drawdown_pct for r in results.values()) if results else 0
        
        return MultiSymbolResult(
            symbols=symbols,
            combined_equity_curve=combined,
            total_net_profit=total_profit,
            total_trades=total_trades,
            overall_win_rate=overall_wr,
            overall_sharpe=overall_sharpe,
            overall_max_dd=overall_dd,
            symbol_results=results
        )
    
    def monte_carlo(
        self,
        result: BacktestResult,
        num_simulations: int = 100
    ) -> Dict[str, Any]:
        """Ejecuta simulación Monte Carlo sobre los resultados"""
        
        if not result.trades:
            return {"error": "No trades to simulate"}
        
        profits = [t.profit for t in result.trades]
        
        final_balances = []
        max_drawdowns = []
        
        for _ in range(num_simulations):
            # Shuffle de trades
            shuffled = profits.copy()
            random.shuffle(shuffled)
            
            # Simular equity curve
            equity = [self.initial_balance]
            for p in shuffled:
                equity.append(equity[-1] + p)
            
            final_balances.append(equity[-1])
            
            # Calcular DD
            peak = equity[0]
            max_dd = 0
            for e in equity:
                if e > peak:
                    peak = e
                dd = (peak - e) / peak * 100 if peak > 0 else 0
                max_dd = max(max_dd, dd)
            max_drawdowns.append(max_dd)
        
        return {
            "simulations": num_simulations,
            "avg_final_balance": np.mean(final_balances),
            "std_final_balance": np.std(final_balances),
            "min_final_balance": np.min(final_balances),
            "max_final_balance": np.max(final_balances),
            "percentile_5": np.percentile(final_balances, 5),
            "percentile_95": np.percentile(final_balances, 95),
            "avg_max_drawdown": np.mean(max_drawdowns),
            "worst_max_drawdown": np.max(max_drawdowns),
            "probability_profit": sum(1 for b in final_balances if b > self.initial_balance) / num_simulations
        }
    
    def get_equity_curve(self) -> List[float]:
        """Retorna la curva de equity"""
        return self.equity_curve
    
    def get_trades(self) -> List[Dict]:
        """Retorna trades como lista de dicts"""
        return [{
            "id": t.id,
            "symbol": t.symbol,
            "type": t.order_type.value,
            "volume": t.volume,
            "open_price": t.open_price,
            "close_price": t.close_price,
            "profit": t.profit,
            "pips": t.pips
        } for t in self.orders if t.status == "closed"]
    
    def _calculate_results(self, symbol: str, total_bars: int) -> BacktestResult:
        """Calcula métricas del backtest"""
        closed_orders = [o for o in self.orders if o.status == "closed"]
        
        if not closed_orders:
            return self._empty_result(symbol, total_bars)
        
        profits = [o.profit for o in closed_orders]
        winners = [p for p in profits if p > 0]
        losers = [p for p in profits if p < 0]
        
        total_profit = sum(winners)
        total_loss = abs(sum(losers))
        net_profit = self.balance - self.initial_balance
        
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
        
        # Ratios
        if len(profits) > 1:
            returns = np.array(profits) / self.initial_balance
            std_ret = np.std(returns)
            sharpe = (np.mean(returns) / std_ret) * np.sqrt(252) if std_ret > 0 else 0
            
            negative_returns = [r for r in returns if r < 0]
            std_neg = np.std(negative_returns) if negative_returns else 0
            sortino = (np.mean(returns) / std_neg) * np.sqrt(252) if std_neg > 0 else 0
        else:
            sharpe = 0.0
            sortino = 0.0
        
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        
        # Expectancy
        win_rate = len(winners) / len(closed_orders)
        avg_win = np.mean(winners) if winners else 0
        avg_loss = np.mean(losers) if losers else 0
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
        
        # Consecutive
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
            symbol=symbol,
            initial_balance=self.initial_balance,
            final_balance=self.balance,
            total_trades=len(closed_orders),
            winning_trades=len(winners),
            losing_trades=len(losers),
            win_rate=win_rate,
            total_profit=total_profit,
            total_loss=total_loss,
            net_profit=net_profit,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            profit_factor=profit_factor,
            expectancy=expectancy,
            avg_trade_profit=np.mean(profits),
            avg_winning_trade=avg_win,
            avg_losing_trade=avg_loss,
            max_consecutive_wins=max_wins,
            max_consecutive_losses=max_losses,
            total_bars=total_bars,
            trades=closed_orders,
            equity_curve=self.equity_curve
        )
    
    def _empty_result(self, symbol: str, total_bars: int) -> BacktestResult:
        """Retorna resultado vacío"""
        return BacktestResult(
            symbol=symbol,
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
            sortino_ratio=0.0,
            profit_factor=0.0,
            expectancy=0.0,
            avg_trade_profit=0.0,
            avg_winning_trade=0.0,
            avg_losing_trade=0.0,
            max_consecutive_wins=0,
            max_consecutive_losses=0,
            total_bars=total_bars,
            trades=[],
            equity_curve=self.equity_curve
        )


# ═══════════════════════════════════════════════════════════════════
# ESTRATEGIAS DE EJEMPLO
# ═══════════════════════════════════════════════════════════════════

def ema_crossover_strategy(data: 'pd.DataFrame', index: int) -> Optional[Dict[str, Any]]:
    """Estrategia de cruce de EMAs"""
    if index < 50:
        return None
    
    close = data['close']
    ema_fast = close.ewm(span=20, adjust=False).mean()
    ema_slow = close.ewm(span=50, adjust=False).mean()
    
    current_fast = ema_fast.iloc[-1]
    current_slow = ema_slow.iloc[-1]
    prev_fast = ema_fast.iloc[-2]
    prev_slow = ema_slow.iloc[-2]
    
    # Cruce alcista
    if prev_fast <= prev_slow and current_fast > current_slow:
        return {"type": "BUY", "volume": 0.1, "sl_pips": 40, "tp_pips": 80}
    
    # Cruce bajista
    if prev_fast >= prev_slow and current_fast < current_slow:
        return {"type": "SELL", "volume": 0.1, "sl_pips": 40, "tp_pips": 80}
    
    return None


def rsi_strategy(data: 'pd.DataFrame', index: int) -> Optional[Dict[str, Any]]:
    """Estrategia de RSI oversold/overbought"""
    if index < 50:
        return None
    
    close = data['close']
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    current_rsi = rsi.iloc[-1]
    prev_rsi = rsi.iloc[-2]
    
    # Oversold -> BUY
    if prev_rsi < 30 and current_rsi >= 30:
        return {"type": "BUY", "volume": 0.1, "sl_pips": 50, "tp_pips": 100}
    
    # Overbought -> SELL
    if prev_rsi > 70 and current_rsi <= 70:
        return {"type": "SELL", "volume": 0.1, "sl_pips": 50, "tp_pips": 100}
    
    return None


def macd_strategy(data: 'pd.DataFrame', index: int) -> Optional[Dict[str, Any]]:
    """Estrategia de señales MACD"""
    if index < 50:
        return None
    
    close = data['close']
    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    
    current_macd = macd.iloc[-1]
    current_signal = signal.iloc[-1]
    prev_macd = macd.iloc[-2]
    prev_signal = signal.iloc[-2]
    
    # Cruce alcista
    if prev_macd <= prev_signal and current_macd > current_signal:
        return {"type": "BUY", "volume": 0.1, "sl_pips": 45, "tp_pips": 90}
    
    # Cruce bajista
    if prev_macd >= prev_signal and current_macd < current_signal:
        return {"type": "SELL", "volume": 0.1, "sl_pips": 45, "tp_pips": 90}
    
    return None


# Alias para compatibilidad
simple_moving_average_strategy = ema_crossover_strategy


if __name__ == "__main__":
    print("=" * 60)
    print("Test de Backtesting Engine v2.0")
    print("=" * 60)
    
    engine = BacktestEngine(initial_balance=1000.0)
    
    # Test básico
    print("\n--- Test con EMA Crossover ---")
    result = engine.run(strategy=ema_crossover_strategy, symbol="EURUSD")
    
    metrics = result.to_dict()
    for key, value in metrics.items():
        if key not in ["trades", "equity_curve"]:
            print(f"  {key}: {value}")
    
    # Test Monte Carlo
    print("\n--- Monte Carlo Simulation ---")
    mc = engine.monte_carlo(result, num_simulations=100)
    print(f"  Probability of profit: {mc['probability_profit']:.1%}")
    print(f"  Avg final balance: {mc['avg_final_balance']:.2f}")
    print(f"  95th percentile: {mc['percentile_95']:.2f}")
    print(f"  Worst drawdown: {mc['worst_max_drawdown']:.1f}%")
    
    # Test multi-símbolo
    print("\n--- Multi-Symbol Test ---")
    multi_result = engine.run_multi_symbol(
        symbols=["EURUSD", "GBPUSD", "USDJPY"],
        strategy=ema_crossover_strategy
    )
    print(f"  Total profit: {multi_result.total_net_profit:.2f}")
    print(f"  Total trades: {multi_result.total_trades}")
    print(f"  Best symbol: {multi_result.best_performing_symbol()}")
    print(f"  Worst symbol: {multi_result.worst_performing_symbol()}")
    
    print("\n✅ Tests completados")
