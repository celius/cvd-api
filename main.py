from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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
    url = f"https://api.binance.com/api/v3/trades?symbol={symbol}&limit={limit}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        trades = response.json()
        
        if not trades:
            raise HTTPException(status_code=404, detail=f"No trades found for {symbol}")
        
        buy_volume = sum(float(t['qty']) * float(t['price']) for t in trades if not t['isBuyerMaker'])
        sell_volume = sum(float(t['qty']) * float(t['price']) for t in trades if t['isBuyerMaker'])
        cvd = buy_volume - sell_volume
        total_volume = buy_volume + sell_volume
        buy_pct = (buy_volume / total_volume * 100) if total_volume > 0 else 0
        
        if buy_pct >= 60:
            signal = "STRONG BULLISH"
            interpretation = "🟢 STRONG BULLISH - Strong accumulation detected"
        elif buy_pct >= 52:
            signal = "BULLISH"
            interpretation = "🟢 BULLISH - Accumulation detected"
        elif buy_pct >= 48:
            signal = "NEUTRAL"
            interpretation = "⚪ NEUTRAL - Balanced flow"
        elif buy_pct >= 40:
            signal = "BEARISH"
            interpretation = "🔴 BEARISH - Distribution detected"
        else:
            signal = "STRONG BEARISH"
            interpretation = "🔴 STRONG BEARISH - Strong distribution detected"
        
        return {
            "symbol": symbol,
            "cvd_usd": round(cvd, 2),
            "buy_volume_usd": round(buy_volume, 2),
            "sell_volume_usd": round(sell_volume, 2),
            "buy_percentage": round(buy_pct, 1),
            "signal": signal,
            "trades_analyzed": len(trades),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "interpretation": interpretation
        }
    
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Binance API error: {str(e)}")

@app.get("/")
def root():
    return {
        "service": "Crypto CVD API for Mode 7",
        "usage": "GET /cvd/{symbol} for JSON or /html/{symbol} for HTML",
        "status": "operational"
    }

@app.get("/cvd/{symbol}")
def get_cvd(symbol: str):
    """JSON endpoint"""
    return calculate_cvd(symbol.upper())

@app.get("/html/{symbol}", response_class=HTMLResponse)
def get_cvd_html(symbol: str):
    """HTML endpoint for Mode 7 crawler"""
    data = calculate_cvd(symbol.upper())
    
    emoji_map = {
        "STRONG BULLISH": "🟢",
        "BULLISH": "🟢",
        "NEUTRAL": "⚪",
        "BEARISH": "🔴",
        "STRONG BEARISH": "🔴"
    }
    emoji = emoji_map.get(data['signal'], "⚪")
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{data['symbol']} - CVD Analysis</title>
        <meta charset="utf-8">
        <style>
            body 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: #1a1a1a;
                color: #e0e0e0;
                padding: 20px;
                margin: 0;
            
            .container 
                max-width: 600px;
                margin: 0 auto;
                background: #2a2a2a;
                padding: 30px;
                border-radius: 12px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            
            h1 
                color: #ffffff;
                margin-top: 0;
                font-size: 24px;
            
            .metric 
                background: #1e3a1e;
                padding: 15px;
                margin: 15px 0;
                border-radius: 8px;
                border-left: 4px solid #4caf50;
            
            .metric.bearish 
                background: #3a1e1e;
                border-left-color: #f44336;
            
            .metric.neutral 
                background: #2a2a2a;
                border-left-color: #757575;
            
            .label 
                font-size: 12px;
                color: #999;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 5px;
            
            .value 
                font-size: 20px;
                font-weight: bold;
                color: #ffffff;
            
            .signal 
                background: #2a2a2a;
                padding: 20px;
                margin: 20px 0;
                border-radius: 8px;
                font-size: 18px;
                text-align: center;
                font-weight: bold;
            
            .timestamp 
                text-align: center;
                color: #666;
                font-size: 12px;
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #333;
            
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{emoji} {data['symbol']} - Spot CVD Analysis</h1>
            
            <div class="signal">
                {data['interpretation']}
            </div>
            
            <div class="metric {'bearish' if data['cvd_usd'] < 0 else ''}">
                <div class="label">Cumulative Volume Delta (CVD)</div>
                <div class="value">${data['cvd_usd']:,.2f}</div>
            </div>
            
            <div class="metric">
                <div class="label">Buy Volume</div>
                <div class="value">${data['buy_volume_usd']:,.2f} ({data['buy_percentage']}%)</div>
            </div>
            
            <div class="metric">
                <div class="label">Sell Volume</div>
                <div class="value">${data['sell_volume_usd']:,.2f} ({100 - data['buy_percentage']:.1f}%)</div>
            </div>
            
            <div class="metric neutral">
                <div class="label">Data Window</div>
                <div class="value">{data['trades_analyzed']} trades analyzed</div>
            </div>
            
            <div class="timestamp">
                Last updated: {data['timestamp']}<br>
                Source: Binance Spot REST API
            </div>
        </div>
    </body>
    </html>
    """
    
    return html_content
