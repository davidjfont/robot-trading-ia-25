"""
Policy Bandit - Sistema de aprendizaje ligero para ARAFURA
Selecciona el mejor 'preset' de parámetros basándose en el contexto y resultados históricos.
"""

import json
import os
import random
from typing import Dict, List, Any
from loguru import logger
from datetime import datetime

class PolicyBandit:
    def __init__(self, persistence_path: str = "data/symbol_policies.json"):
        self.path = persistence_path
        self.policies = self._load_policies()
        
        # Presets predefinidos
        self.presets = {
            "conservative": {"k_sl": 2.5, "k_tp": 1.5, "trail": True, "description": "SL largo, TP corto"},
            "balanced": {"k_sl": 1.5, "k_tp": 2.5, "trail": True, "description": "Equilibrio ATR"},
            "aggressive": {"k_sl": 1.2, "k_tp": 3.0, "trail": False, "description": "SL ceñido, TP lejano"},
            "safe": {"k_sl": 3.0, "k_tp": 2.0, "trail": True, "description": "Máxima protección"}
        }

    def select_preset(self, symbol: str, context: Dict[str, Any]) -> str:
        """Selecciona un preset usando Epsilon-Greedy"""
        epsilon = 0.2 # 20% exploración
        
        if random.random() < epsilon or symbol not in self.policies:
            return random.choice(list(self.presets.keys()))
            
        # Elegir el que tenga mayor reward promedio para ese símbolo
        symbol_stats = self.policies[symbol]
        best_preset = max(symbol_stats, key=lambda k: symbol_stats[k]['avg_reward'])
        return best_preset

    def get_params(self, preset_name: str) -> Dict[str, Any]:
        return self.presets.get(preset_name, self.presets["balanced"])

    def update_stats(self, symbol: str, preset_name: str, r_multiple: float):
        """Actualiza las estadísticas del bandit (Reward = R-Multiple)"""
        if symbol not in self.policies:
            self.policies[symbol] = {k: {"avg_reward": 0.0, "count": 0} for k in self.presets}
            
        stats = self.policies[symbol][preset_name]
        stats['count'] += 1
        # Media móvil incremental
        stats['avg_reward'] += (r_multiple - stats['avg_reward']) / stats['count']
        
        self._save_policies()
        logger.info(f"📊 Bandit Update: {symbol} [{preset_name}] -> R:{r_multiple:.2f} | Avg:{stats['avg_reward']:.2f}")

    def _load_policies(self) -> Dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_policies(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w') as f:
            json.dump(self.policies, f, indent=4)
