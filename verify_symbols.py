import sys
import os

# Mock logic since we are running in an environment where we might not want to touch real MT5
from core.symbols import normalize_symbol, TRADING_SYMBOLS

def test_normalization():
    print("Testing Symbol Normalization...")
    
    # Test case 1: Admirals exact match
    company = "Admirals Group AS"
    sym = normalize_symbol("GER40", company)
    print(f"GER40 @ {company} -> {sym} (Expected: GERMANY40)")
    assert sym == "GERMANY40"
    
    # Test case 2: Admirals partial match
    company = "Admirals Limited"
    sym = normalize_symbol("US500", company)
    print(f"US500 @ {company} -> {sym} (Expected: [SP500])")
    assert sym == "[SP500]"
    
    # Test case 3: Fallback (no company)
    sym = normalize_symbol("WTI")
    print(f"WTI @ NoCompany -> {sym} (Expected: #WTI.US)")
    assert sym == "#WTI.US"
    
    # Test case 4: Non-mapped symbol
    sym = normalize_symbol("EURUSD")
    print(f"EURUSD @ Any -> {sym} (Expected: EURUSD)")
    assert sym == "EURUSD"

    # Test case 5: Case insensitivity
    sym = normalize_symbol("ger40", "admirals")
    print(f"ger40 @ admirals -> {sym} (Expected: GERMANY40)")
    assert sym == "GERMANY40"

    print("\n✅ All normalization tests passed!")

if __name__ == "__main__":
    try:
        test_normalization()
    except Exception as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)
