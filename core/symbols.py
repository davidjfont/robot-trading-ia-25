"""
Standardized Trading Symbols for the platform
"""

TRADING_SYMBOLS = {
    "Forex": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"],
    "Materias Primas": ["GOLD", "SILVER", "BRENT", "WTI", "NATGAS"],
    "Índices": ["US500", "USTEC", "US30", "GER40", "UK100", "ESP35"]
}

def get_all_symbols():
    """Returns a flat list of all symbols"""
    return [s for cat in TRADING_SYMBOLS.values() for s in cat]

def get_symbols_by_category():
    """Returns the categorized dictionary of symbols"""
    return TRADING_SYMBOLS
