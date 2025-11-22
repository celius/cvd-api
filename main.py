from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime

app = FastAPI(title="CVD API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

def calculate_cvd(symbol: str, limit: int = 1000):
    """Henter trades fra Binance og beregner CVD."""
    url = f"https://api.binance.com/api/v3/trades"
    params = {"symbol": symbol, "limit": limit}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        trades = response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    
    # Beregn CVD
    cvd = 0
    buy_vol = 0
    sell_vol = 0
    
    for trade in trades:
        price = float(trade['price'])
        qty = float(trade['qty'])
        vol_usd = price * qty
        
        if trade['isBuyerMaker']:  # Market sell
            sell_vol += vol_usd
            cvd -= vol_usd
        else:  # Market buy
            buy_vol += vol_usd
            cvd += vol_usd
    
    total = buy_vol + sell_vol
    buy_pct = (buy_vol / total * 100) if total > 0 else 0
    
    # Bestem signal
    if buy_pct > 60:
        signal = "STRONG BULLISH"
    elif buy_pct > 55:
        signal = "BULLISH"
    elif buy_pct < 40:
        signal = "STRONG BEARISH"
    elif buy_pct < 45:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"
    
    emoji = "🟢" if "BULLISH" in signal else "🔴" if "BEARISH" in signal else "⚪"
    
    return {
        "symbol": symbol,
        "cvd_usd": round(cvd, 2),
        "buy_volume_usd": round(buy_vol, 2),
        "sell_volume_usd": round(sell_vol, 2),
        "buy_percentage": round(buy_pct, 1),
        "signal": signal,
        "trades_analyzed": len(trades),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "interpretation": f"{emoji} {signal} - {'Accumulation detected' if 'BULLISH' in signal else 'Distribution detected' if 'BEARISH' in signal else 'Balanced market'}"
    }

@app.get("/")
def root():
    return {
        "service": "Crypto CVD API for Mode 7",
        "usage": "GET /cvd/{symbol} (example: /cvd/BTCUSDT)",
        "data_source": "Binance Spot Market",
        "status": "operational"
    }

@app.get("/cvd/{symbol}")
def get_cvd(symbol: str):
    """Hovedendpoint - Mode 7 søker etter denne."""
    symbol = symbol.upper()
    if not (symbol.endswith("USDT") or symbol.endswith("BUSD")):
        raise HTTPException(400, "Symbol must end with USDT or BUSD")
    
    return calculate_cvd(symbol, limit=1000)

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
