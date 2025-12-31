"""
Standardized Trading Symbols for the platform
"""

TRADING_SYMBOLS = {
    "Forex": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"],
    "Materias Primas": ["GOLD", "SILVER", "BRENT", "WTI", "NATGAS"],
    "Índices": ["US500", "USTEC", "US30", "GER40", "UK100", "ESP35"]
}

# Mapeo invertido para compatibilidad (Símbolo Broker -> Símbolo Interno)
REVERSE_MAPPINGS = {
    "[SP500]": "US500",
    "US100": "USTEC",
    "[DJI30]": "US30",
    "GERMANY40": "GER40",
    "[FTSE100]": "UK100",
    "[IBEX35]": "ESP35",
    "#WTI.US": "WTI",
    "NGAS": "NATGAS"
}

# Mapeo de símbolos por broker
BROKER_MAPPINGS = {
    "Admirals Group AS": {
        "US500": "[SP500]",
        "USTEC": "US100",
        "US30": "[DJI30]",
        "GER40": "GERMANY40",
        "UK100": "[FTSE100]",
        "ESP35": "[IBEX35]",
        "WTI": "#WTI.US",
        "NATGAS": "NGAS",
        "BRENT": "BRENT"
    },
    "Admirals": { # Alias común
        "US500": "[SP500]",
        "USTEC": "US100",
        "US30": "[DJI30]",
        "GER40": "GERMANY40",
        "UK100": "[FTSE100]",
        "ESP35": "[IBEX35]",
        "WTI": "#WTI.US",
        "NATGAS": "NGAS",
        "BRENT": "BRENT"
    }
}

def get_all_symbols():
    """Returns a flat list of all symbols"""
    return [s for cat in TRADING_SYMBOLS.values() for s in cat]

def get_symbols_by_category():
    """Returns the categorized dictionary of symbols"""
    return TRADING_SYMBOLS

def normalize_symbol(symbol: str, company_name: str = "") -> str:
    """
    Normaliza un símbolo básico al nombre específico del broker.
    
    Args:
        symbol: Símbolo básico (ej: "US500")
        company_name: Nombre del broker/compañía obtenido de MT5
        
    Returns:
        Símbolo mapeado o el original si no hay mapeo
    """
    if not symbol:
        return symbol

    symbol_upper = symbol.upper()
    
    # 1. Búsqueda exacta por compañía
    if company_name:
        for name, mapping in BROKER_MAPPINGS.items():
            if name.lower() in company_name.lower():
                return mapping.get(symbol_upper, symbol_upper)
    
    # 2. Fallback: buscar en todos los mapeos (tomar el primero encontrado que coincida con la clave)
    for mapping in BROKER_MAPPINGS.values():
        if symbol_upper in mapping:
            return mapping[symbol_upper]
            
    return symbol_upper

