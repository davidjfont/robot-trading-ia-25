"""
Telegram Notifier - Envía alertas de trading a Telegram
"""

import requests
from typing import Optional, Dict, Any
from datetime import datetime
import yaml
from pathlib import Path
from loguru import logger


class TelegramNotifier:
    """Clase para enviar notificaciones de trading a Telegram"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """Inicializa el notificador con la configuración"""
        self.enabled = False
        self.bot_token = None
        self.chat_id = None
        
        self._load_config(config_path)
    
    def _load_config(self, config_path: str):
        """Carga configuración de Telegram desde config.yaml"""
        try:
            config_file = Path(config_path)
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                
                telegram_config = config.get('notifications', {}).get('telegram', {})
                self.enabled = telegram_config.get('enabled', False)
                self.bot_token = telegram_config.get('bot_token', '')
                self.chat_id = telegram_config.get('chat_id', '')
                
                if self.enabled and self.bot_token and self.chat_id:
                    logger.info("TelegramNotifier configurado correctamente")
                else:
                    logger.warning("TelegramNotifier: Faltan credenciales o está deshabilitado")
        except Exception as e:
            logger.error(f"Error cargando config de Telegram: {e}")
    
    def _send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """Envía un mensaje a Telegram"""
        if not self.enabled or not self.bot_token or not self.chat_id:
            logger.debug("Telegram no configurado, mensaje no enviado")
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info("Mensaje de Telegram enviado correctamente")
                return True
            else:
                logger.error(f"Error enviando a Telegram: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error enviando mensaje Telegram: {e}")
            return False
    
    def send_test(self) -> bool:
        """Envía mensaje de prueba"""
        message = """
🤖 <b>Trading Bot - Test de Conexión</b>

✅ Conexión con Telegram establecida correctamente.

📊 El bot está listo para enviar alertas de:
• Apertura/cierre de operaciones
• Señales de trading
• Alertas de riesgo
• Resúmenes diarios

<i>Configuración completada: {}</i>
        """.format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        return self._send_message(message)
    
    def send_trade_opened(self, symbol: str, order_type: str, volume: float, 
                          price: float, sl: float, tp: float) -> bool:
        """Notifica apertura de operación"""
        emoji = "📈" if order_type.upper() == "BUY" else "📉"
        
        message = f"""
{emoji} <b>OPERACIÓN ABIERTA</b>

<b>Símbolo:</b> {symbol}
<b>Tipo:</b> {order_type.upper()}
<b>Volumen:</b> {volume} lotes
<b>Precio:</b> {price}
<b>Stop Loss:</b> {sl}
<b>Take Profit:</b> {tp}

⏰ {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        """
        
        return self._send_message(message)
    
    def send_trade_closed(self, symbol: str, order_type: str, volume: float,
                          open_price: float, close_price: float, profit: float) -> bool:
        """Notifica cierre de operación"""
        emoji = "💰" if profit > 0 else "💸"
        profit_text = f"+{profit:.2f}" if profit > 0 else f"{profit:.2f}"
        
        message = f"""
{emoji} <b>OPERACIÓN CERRADA</b>

<b>Símbolo:</b> {symbol}
<b>Tipo:</b> {order_type.upper()}
<b>Volumen:</b> {volume} lotes
<b>Precio apertura:</b> {open_price}
<b>Precio cierre:</b> {close_price}
<b>Profit:</b> {profit_text} €

⏰ {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        """
        
        return self._send_message(message)
    
    def send_signal_alert(self, symbol: str, direction: str, 
                          strength: float, score: float) -> bool:
        """Notifica señal de trading fuerte"""
        emoji = "🟢" if direction.upper() == "BUY" else "🔴" if direction.upper() == "SELL" else "🟡"
        
        message = f"""
🔔 <b>SEÑAL DE TRADING</b>

<b>Símbolo:</b> {symbol}
<b>Dirección:</b> {emoji} {direction.upper()}
<b>Fuerza:</b> {strength*100:.0f}%
<b>Score:</b> {score:.3f}

<i>Analizado por IA</i>
⏰ {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        """
        
        return self._send_message(message)
    
    def send_risk_alert(self, alert_type: str, message: str, 
                        current_value: float, limit_value: float) -> bool:
        """Notifica alerta de riesgo"""
        
        alert_message = f"""
⚠️ <b>ALERTA DE RIESGO</b>

<b>Tipo:</b> {alert_type}
<b>Mensaje:</b> {message}

<b>Valor actual:</b> {current_value:.2f}%
<b>Límite:</b> {limit_value:.2f}%

🚨 <i>Revisa tus operaciones</i>
⏰ {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        """
        
        return self._send_message(alert_message)
    
    def send_daily_summary(self, total_trades: int, winning_trades: int,
                           total_profit: float, win_rate: float,
                           balance: float, equity: float) -> bool:
        """Envía resumen diario"""
        emoji = "📈" if total_profit > 0 else "📉" if total_profit < 0 else "➖"
        profit_text = f"+{total_profit:.2f}" if total_profit > 0 else f"{total_profit:.2f}"
        
        message = f"""
📊 <b>RESUMEN DIARIO</b>

<b>Operaciones:</b> {total_trades}
<b>Ganadas:</b> {winning_trades}
<b>Win Rate:</b> {win_rate*100:.1f}%

{emoji} <b>Profit del día:</b> {profit_text} €

💰 <b>Balance:</b> {balance:.2f} €
💎 <b>Equity:</b> {equity:.2f} €

📅 {datetime.now().strftime("%Y-%m-%d")}
        """
        
        return self._send_message(message)
    
    def send_llm_analysis(self, symbol: str, analysis: str, 
                          recommendation: str, confidence: float) -> bool:
        """Envía análisis del LLM"""
        emoji = "🟢" if recommendation.upper() == "BUY" else "🔴" if recommendation.upper() == "SELL" else "🟡"
        
        message = f"""
🧠 <b>ANÁLISIS IA - {symbol}</b>

{emoji} <b>Recomendación:</b> {recommendation.upper()}
<b>Confianza:</b> {confidence*100:.0f}%

<b>Análisis:</b>
<i>{analysis[:300]}...</i>

⏰ {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        """
        
        return self._send_message(message)


# Test standalone
if __name__ == "__main__":
    notifier = TelegramNotifier()
    
    if notifier.enabled:
        print("Enviando mensaje de prueba...")
        result = notifier.send_test()
        print(f"Resultado: {'Éxito' if result else 'Error'}")
    else:
        print("Telegram no está configurado.")
        print("Añade las credenciales en config.yaml:")
        print("""
notifications:
  telegram:
    enabled: true
    bot_token: "TU_BOT_TOKEN"
    chat_id: "TU_CHAT_ID"
        """)
