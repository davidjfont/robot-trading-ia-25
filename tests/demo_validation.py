"""
Demo Validation - Checklist de validación para cuenta demo
"""

import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any
from dataclasses import dataclass
from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mt5.connector import MT5Connector
from agents.risk_agent import RiskAgent


@dataclass
class ValidationCheck:
    """Resultado de un check de validación"""
    name: str
    passed: bool
    message: str
    details: Dict[str, Any] = None


class DemoValidator:
    """
    Validador de sistema antes de pasar a producción.
    
    Ejecuta una serie de checks para asegurar que el sistema
    está listo para operar.
    """
    
    def __init__(self):
        self.checks: List[ValidationCheck] = []
        self.start_time = datetime.now()
    
    def run_all_checks(self) -> Dict[str, Any]:
        """Ejecuta todos los checks de validación"""
        
        print("=" * 60)
        print("🔍 VALIDACIÓN DE SISTEMA - PRE-PRODUCCIÓN")
        print("=" * 60)
        print()
        
        # Check 1: Conexión MT5
        self._check_mt5_connection()
        
        # Check 2: Datos de mercado
        self._check_market_data()
        
        # Check 3: RiskAgent
        self._check_risk_agent()
        
        # Check 4: LLM disponible
        self._check_llm()
        
        # Check 5: Base de datos
        self._check_database()
        
        # Check 6: Spread aceptable
        self._check_spreads()
        
        # Resumen
        return self._generate_report()
    
    def _check_mt5_connection(self):
        """Verifica conexión a MT5"""
        print("📡 Verificando conexión MT5...")
        
        try:
            connector = MT5Connector()
            connected = connector.connect()
            
            if connected:
                account_info = connector.get_account_info()
                connector.disconnect()
                
                self.checks.append(ValidationCheck(
                    name="Conexión MT5",
                    passed=True,
                    message=f"Conectado a {account_info.get('server', 'N/A')}",
                    details={
                        "account": account_info.get('login'),
                        "balance": account_info.get('balance'),
                        "server": account_info.get('server')
                    }
                ))
                print(f"   ✅ Conectado | Balance: €{account_info.get('balance', 0):.2f}")
            else:
                self.checks.append(ValidationCheck(
                    name="Conexión MT5",
                    passed=False,
                    message="No se pudo conectar a MT5"
                ))
                print("   ❌ No conectado")
                
        except Exception as e:
            self.checks.append(ValidationCheck(
                name="Conexión MT5",
                passed=False,
                message=f"Error: {str(e)}"
            ))
            print(f"   ❌ Error: {e}")
    
    def _check_market_data(self):
        """Verifica obtención de datos de mercado"""
        print("📊 Verificando datos de mercado...")
        
        try:
            connector = MT5Connector()
            if not connector.connect():
                self.checks.append(ValidationCheck(
                    name="Datos de Mercado",
                    passed=False,
                    message="MT5 no conectado"
                ))
                print("   ❌ MT5 no conectado")
                return
            
            symbols_ok = []
            symbols_fail = []
            
            for symbol in ["EURUSD", "GBPUSD", "USDJPY"]:
                rates = connector.get_rates(symbol, 15, 100)
                if rates is not None and len(rates) > 50:
                    symbols_ok.append(symbol)
                else:
                    symbols_fail.append(symbol)
            
            connector.disconnect()
            
            passed = len(symbols_ok) >= 2
            
            self.checks.append(ValidationCheck(
                name="Datos de Mercado",
                passed=passed,
                message=f"{len(symbols_ok)}/3 símbolos con datos",
                details={"ok": symbols_ok, "fail": symbols_fail}
            ))
            
            if passed:
                print(f"   ✅ {len(symbols_ok)} símbolos disponibles: {', '.join(symbols_ok)}")
            else:
                print(f"   ⚠️ Solo {len(symbols_ok)} símbolos disponibles")
                
        except Exception as e:
            self.checks.append(ValidationCheck(
                name="Datos de Mercado",
                passed=False,
                message=f"Error: {str(e)}"
            ))
            print(f"   ❌ Error: {e}")
    
    def _check_risk_agent(self):
        """Verifica funcionamiento del RiskAgent"""
        print("🛡️ Verificando RiskAgent...")
        
        try:
            agent = RiskAgent()
            
            # Test 1: Operación normal
            result = agent.run({
                "symbol": "EURUSD",
                "type": "BUY",
                "volume": 0.1,
                "signal_strength": 0.75,
                "balance": 1000,
                "equity": 1000,
                "margin_free": 900,
                "open_positions": []
            })
            
            normal_ok = result.success and result.data.get("approved")
            
            # Test 2: Debe bloquear señal débil
            result2 = agent.run({
                "symbol": "EURUSD",
                "type": "BUY",
                "volume": 0.1,
                "signal_strength": 0.1,  # Muy débil
                "balance": 1000,
                "equity": 1000,
                "margin_free": 900,
                "open_positions": []
            })
            
            block_ok = result2.success and not result2.data.get("approved")
            
            passed = normal_ok and block_ok
            
            self.checks.append(ValidationCheck(
                name="RiskAgent",
                passed=passed,
                message="Reglas de bloqueo funcionando" if passed else "Error en reglas",
                details={"normal_approved": normal_ok, "weak_blocked": block_ok}
            ))
            
            if passed:
                print("   ✅ Reglas de bloqueo funcionando correctamente")
            else:
                print("   ❌ Error en reglas de RiskAgent")
                
        except Exception as e:
            self.checks.append(ValidationCheck(
                name="RiskAgent",
                passed=False,
                message=f"Error: {str(e)}"
            ))
            print(f"   ❌ Error: {e}")
    
    def _check_llm(self):
        """Verifica disponibilidad del LLM"""
        print("🧠 Verificando LLM...")
        
        try:
            from agents.llm_provider import get_llm
            llm = get_llm()
            available = llm.is_available()
            
            self.checks.append(ValidationCheck(
                name="LLM (Ollama)",
                passed=available,
                message="LLM disponible" if available else "LLM no disponible"
            ))
            
            if available:
                print("   ✅ LLM disponible")
            else:
                print("   ⚠️ LLM no disponible (sistema funcionará sin análisis de sentimiento)")
                
        except Exception as e:
            self.checks.append(ValidationCheck(
                name="LLM (Ollama)",
                passed=False,
                message=f"Error: {str(e)}"
            ))
            print(f"   ⚠️ LLM no disponible: {e}")
    
    def _check_database(self):
        """Verifica base de datos"""
        print("💾 Verificando base de datos...")
        
        try:
            from scraping.storage import get_storage
            storage = get_storage()
            
            # Intentar obtener estadísticas
            stats = storage.get_trade_stats(days=30)
            
            self.checks.append(ValidationCheck(
                name="Base de Datos",
                passed=True,
                message="SQLite funcionando",
                details=stats
            ))
            
            print("   ✅ Base de datos conectada")
            
        except Exception as e:
            self.checks.append(ValidationCheck(
                name="Base de Datos",
                passed=False,
                message=f"Error: {str(e)}"
            ))
            print(f"   ❌ Error: {e}")
    
    def _check_spreads(self):
        """Verifica que los spreads sean aceptables"""
        print("📏 Verificando spreads...")
        
        try:
            connector = MT5Connector()
            if not connector.connect():
                self.checks.append(ValidationCheck(
                    name="Spreads",
                    passed=False,
                    message="MT5 no conectado"
                ))
                return
            
            spreads = {}
            all_ok = True
            
            for symbol in ["EURUSD", "GBPUSD"]:
                tick = connector.get_symbol_tick(symbol)
                if tick:
                    spread = round((tick.ask - tick.bid) * 10000, 1)
                    spreads[symbol] = spread
                    if spread > 30:  # Spread muy alto
                        all_ok = False
            
            connector.disconnect()
            
            self.checks.append(ValidationCheck(
                name="Spreads",
                passed=all_ok,
                message="Spreads normales" if all_ok else "Spreads elevados",
                details=spreads
            ))
            
            if all_ok:
                spread_str = ", ".join([f"{s}: {v} pips" for s, v in spreads.items()])
                print(f"   ✅ Spreads normales ({spread_str})")
            else:
                print("   ⚠️ Spreads elevados - mercado puede estar cerrado")
                
        except Exception as e:
            self.checks.append(ValidationCheck(
                name="Spreads",
                passed=False,
                message=f"Error: {str(e)}"
            ))
            print(f"   ❌ Error: {e}")
    
    def _generate_report(self) -> Dict[str, Any]:
        """Genera reporte final de validación"""
        
        passed_checks = sum(1 for c in self.checks if c.passed)
        total_checks = len(self.checks)
        
        print()
        print("=" * 60)
        print("📋 RESUMEN DE VALIDACIÓN")
        print("=" * 60)
        print()
        
        for check in self.checks:
            icon = "✅" if check.passed else "❌"
            print(f"  {icon} {check.name}: {check.message}")
        
        print()
        print(f"  Resultado: {passed_checks}/{total_checks} checks pasados")
        
        # Determinar si está listo
        critical_checks = ["Conexión MT5", "RiskAgent", "Base de Datos"]
        critical_passed = all(
            c.passed for c in self.checks if c.name in critical_checks
        )
        
        if critical_passed and passed_checks >= 4:
            status = "READY"
            print()
            print("  🟢 SISTEMA LISTO PARA DEMO")
        elif critical_passed:
            status = "PARTIAL"
            print()
            print("  🟡 SISTEMA FUNCIONAL CON LIMITACIONES")
        else:
            status = "NOT_READY"
            print()
            print("  🔴 SISTEMA NO LISTO - REVISAR ERRORES")
        
        print()
        print("=" * 60)
        
        return {
            "status": status,
            "passed": passed_checks,
            "total": total_checks,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "message": c.message,
                    "details": c.details
                }
                for c in self.checks
            ],
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": (datetime.now() - self.start_time).seconds
        }


def run_validation():
    """Ejecuta validación del sistema"""
    validator = DemoValidator()
    return validator.run_all_checks()


if __name__ == "__main__":
    result = run_validation()
    
    print()
    print("Resultado JSON:")
    import json
    print(json.dumps(result, indent=2, default=str))
