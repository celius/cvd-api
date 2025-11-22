from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone

app = FastAPI(title="CVD API v5.0 - Whale Hunter", version="5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Binance bruker aggTrades for presisjon, men for 90 dager bruker vi klines (candles) for effektivitet
BASE_URL = "https://api.binance.com/api/v3/klines"

async def fetch_candles(session, symbol, interval, limit):
    """Henter candles (Open, High, Low, Close, Volume, QuoteVol)."""
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        async with session.get(BASE_URL, params=params, timeout=10) as resp:
            if resp.status != 200: return []
            data = await resp.json()
            # Binance kline format: [time, open, high, low, close, vol, close_time, quote_vol, trades, taker_buy_base, taker_buy_quote, ignore]
            # Vi er interessert i Taker Buy Volume for å beregne CVD (Kjøpspress)
            # Taker Buy Quote Asset Volume er index 10. Total Quote Asset Volume er index 7.
            # Buy Vol = Index 10. Sell Vol = Index 7 - Index 10.
            processed = []
            for k in data:
                total_vol = float(k[7]) # Quote volume (USDT/USDC)
                buy_vol = float(k[10])  # Taker buy quote volume
                sell_vol = total_vol - buy_vol
                net_flow = buy_vol - sell_vol
                processed.append({"time": k[0], "net_flow": net_flow})
            return processed
    except: return []

def calculate_cvd(data, days=None):
    """Summerer Net Flow for en gitt periode."""
    if not data: return 0
    
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    if days:
        cutoff = now_ms - (days * 24 * 60 * 60 * 1000)
        filtered = [d['net_flow'] for d in data if d['time'] >= cutoff]
    else:
        filtered = [d['net_flow'] for d in data] # All data
        
    return sum(filtered)

async def analyze_whale_trends(ticker):
    async with aiohttp.ClientSession() as session:
        # 1. Hent MACRO data (4h candles, ca 90 dager = 540 candles)
        # Vi henter 600 for å være sikre.
        usdt_task = fetch_candles(session, f"{ticker}USDT", "4h", 600)
        usdc_task = fetch_candles(session, f"{ticker}USDC", "4h", 600)
        
        # 2. Hent MICRO data (15m candles, siste 24t = 96 candles)
        # Vi bruker dette for "X-Ray" kortsiktig
        usdt_micro_task = fetch_candles(session, f"{ticker}USDT", "15m", 96)
        usdc_micro_task = fetch_candles(session, f"{ticker}USDC", "15m", 96)
        
        results = await asyncio.gather(usdt_task, usdc_task, usdt_micro_task, usdc_micro_task)
        
    macro_usdt, macro_usdc = results[0], results[1]
    micro_usdt, micro_usdc = results[2], results[3]
    
    # Beregn trender ved å skjære i samme datasett (Macro)
    trends = {
        "90d": {"retail": calculate_cvd(macro_usdt, 90), "insti": calculate_cvd(macro_usdc, 90)},
        "30d": {"retail": calculate_cvd(macro_usdt, 30), "insti": calculate_cvd(macro_usdc, 30)},
        "7d":  {"retail": calculate_cvd(macro_usdt, 7),  "insti": calculate_cvd(macro_usdc, 7)},
        "24h": {"retail": calculate_cvd(micro_usdt),     "insti": calculate_cvd(micro_usdc)} # Bruker micro for presisjon siste døgn
    }
    
    return {"ticker": ticker, "trends": trends}

@app.get("/html/{ticker}", response_class=HTMLResponse)
async def get_whale_dashboard(ticker: str):
    data = await analyze_whale_trends(ticker.upper())
    t = data["trends"]
    
    # Helper for å fargelegge tall
    def fmt(val, is_insti=False):
        color = "red" if val < 0 else "green"
        # Hvis Institusjoner kjøper (+) og Retail selger (-), gjør det GULL (Bullish Divergence)
        bg = ""
        return f"<span style='color:{color}; font-weight:bold;'>${val/1_000_000:.1f}M</span>"

    # Bygg HTML Dashboard
    html = f"""
    <html><body style="font-family: sans-serif; background: #f0f2f5; padding: 20px;">
        <div style="background: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); max-width: 700px; margin: auto;">
            <h2 style="text-align:center; margin-bottom: 5px;">🐋 {data['ticker']} Whale Hunter Dashboard</h2>
            <p style="text-align:center; color:#666; font-size:12px; margin-top:0;">Smart Money (USDC) vs Retail (USDT)</p>
            
            <table style="width:100%; border-collapse: collapse; margin-top: 20px;">
                <tr style="background:#fafafa; text-align:left; color:#888;">
                    <th style="padding:10px;">Periode</th>
                    <th style="padding:10px;">🛒 Retail (USDT)</th>
                    <th style="padding:10px;">🏦 Smart Money (USDC)</th>
                    <th style="padding:10px;">Signal</th>
                </tr>
    """
    
    labels = [("90 Dager (Macro)", "90d"), ("30 Dager (Måned)", "30d"), ("7 Dager (Uke)", "7d"), ("24 Timer (Micro)", "24h")]
    
    for label, key in labels:
        ret = t[key]["retail"]
        ins = t[key]["insti"]
        
        # Tolk Signalet
        sig = "Neutral"
        bg_row = "white"
        
        if ins > 0 and ret < 0:
            sig = "🐋 ACCUMULATION"
            bg_row = "#e8f5e9" # Light green
        elif ins < 0 and ret > 0:
            sig = "⚠️ DISTRIBUTION"
            bg_row = "#ffebee" # Light red
        elif ins > 0 and ret > 0:
            sig = "🚀 MOMENTUM"
        elif ins < 0 and ret < 0:
            sig = "🩸 DUMP"
            
        html += f"""
            <tr style="border-bottom: 1px solid #eee; background: {bg_row};">
                <td style="padding:12px;">{label}</td>
                <td style="padding:12px;">{fmt(ret)}</td>
                <td style="padding:12px;">{fmt(ins, True)}</td>
                <td style="padding:12px; font-weight:bold; font-size:12px;">{sig}</td>
            </tr>
        """
        
    html += """
            </table>
            <div style="margin-top:15px; font-size:11px; color:#999; text-align:center;">
                Data source: Binance API (Taker Buy Volume). Analyzed across multiple timeframes instantly.
            </div>
        </div>
    </body></html>
    """
    return html
