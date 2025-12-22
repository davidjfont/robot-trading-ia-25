"""
Config Manager - Gestión de configuración persistente
"""

import os
import json
from datetime import datetime
from loguru import logger

# Directorio base
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, 'data', 'user_config.json')

# Configuración por defecto
DEFAULT_CONFIG = {
    "symbols": ["EURUSD", "GBPUSD"],
    "timeframe": "M15",
    "max_risk_percent": 2,
    "max_positions": 3,
    "auto_refresh": True,
    "refresh_interval": 5,
    "trading_mode": "normal",
    "scalping": {
        "max_positions_per_symbol": 1,
        "target_total_positions": 7,
        "stop_loss_pips": 3,
        "take_profit_pips": 6,
        "max_trade_duration_seconds": 120
    }
}


def load_config() -> dict:
    """Carga la configuración guardada o retorna la por defecto"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved_config = json.load(f)
                # Mezclar con defaults para nuevas claves
                merged = {**DEFAULT_CONFIG, **saved_config}
                return merged
    except Exception as e:
        logger.warning(f"Error cargando config: {e}")
    
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> bool:
    """Guarda la configuración"""
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        config['last_updated'] = datetime.now().isoformat()
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.debug("Configuración guardada")
        return True
    except Exception as e:
        logger.error(f"Error guardando config: {e}")
        return False


def reset_config() -> dict:
    """Restablece la configuración a los valores por defecto"""
    try:
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
        logger.info("Configuración restablecida a valores por defecto")
    except Exception as e:
        logger.error(f"Error reseteando config: {e}")
    
    return DEFAULT_CONFIG.copy()


def get_trading_mode() -> str:
    """Obtiene el modo de trading actual"""
    config = load_config()
    return config.get('trading_mode', 'normal')


def set_trading_mode(mode: str) -> bool:
    """Establece el modo de trading"""
    config = load_config()
    config['trading_mode'] = mode
    return save_config(config)


def update_config(**kwargs) -> bool:
    """Actualiza valores específicos de la configuración"""
    config = load_config()
    config.update(kwargs)
    return save_config(config)
