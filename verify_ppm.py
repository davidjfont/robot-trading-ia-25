import sys
import os

# Añadir el directorio raíz al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scalping.swing_detector import SwingDetector

def test_swing_detector():
    detector = SwingDetector(lookback=20)
    
    # Simular una tendencia alcista (Low -> High)
    rates = [
        {'high': 1.1000 + i*0.0001, 'low': 1.0990 + i*0.0001, 'close': 1.0995 + i*0.0001}
        for i in range(20)
    ]
    
    context = detector.detect_last_swing(rates)
    
    print(f"Dirección: {context['direction']}")
    print(f"R: {context['R']:.5f}")
    print(f"Niveles: {context['levels']}")
    
    assert context['direction'] == "BULLISH"
    assert abs(context['R'] - 0.0029) < 0.0001 # high[19]=1.1019, low[0]=1.0990 -> diff 0.0029
    
    # 0.5R level check
    expected_05r = 1.0990 + (0.0029 * 0.5)
    assert abs(context['levels']['0.5R'] - expected_05r) < 0.0001
    
    print("✅ Test de SwingDetector Completado con Éxito")

if __name__ == "__main__":
    test_swing_detector()
