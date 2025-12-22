from enum import Enum, auto

class TradingState(Enum):
    """
    Core State Machine for ARAFURA Trading System.
    Strictly enforcing the lifecycle: IDLE -> OBSERVE -> READY -> EXECUTE -> RECOVER
    """
    IDLE = auto()       # Passive, waiting for triggers
    OBSERVE = auto()    # Gathering data (prices, news, DOM)
    READY = auto()      # Processing signals, Risk analysis
    EXECUTE = auto()    # Sending orders to Broker (MT5)
    MANAGE = auto()     # Managing open positions (Trailing, BE)
    RECOVER = auto()    # Error handling, reconnection
