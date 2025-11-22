from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timezone

app = FastAPI(title="CVD API v8.0 - Retail vs Whale Sentiment", version="8.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# --- CONFIG ---
DOMAIN_SPOT = "https://api.binance.com"
DOMAIN_FUTURES = "https://fapi.binance.com"
LIMIT_KLINES = 500  # Nok data for beregninger

# --- HJELPEFUNKSJONER ---

async def fetch_url(session, url, params=None):
    """Henter data asynkront og håndterer feil."""
    try:
        async with session.get(url, params=params) as response:
            if response.status != 200:
                print(f"Error fetching {url}: {response.status}")
                return None
            return await response.json()
    except Exception as e:
        print(f"Exception fetching {url}: {e}")
        return None

def format_number(num):
    """Formaterer store tall til lesbart format (k, M, B)."""
    if abs(num) >= 1_000_000_000:
        return f"{num / 1_000_000_000:.2f}B"
    if abs(num) >= 1_000_000:
        return f"{num / 1_000_000:.2f}M"
    if abs(num) >= 1_000:
        return f"{num / 1_000:.2f}k"
    return f"{num:.2f}"

def interpret_sentiment(global_ratio, top_acc_ratio, top_pos_ratio):
    """
    Analyserer 'Hvem' som gjør hva.
    - Global Ratio høy = Retail er Bullish (ofte contrarian signal hvis pris faller)
    - Top Pos > Top Acc = Whales satser tungt (High Conviction)
    """
    signals = []
    
    # 1. Retail Sentiment
    if global_ratio > 1.5:
        signals.append("Retail er EKSTREMT BULLISH (Crowded Longs)")
    elif global_ratio < 0.6:
        signals.append("Retail er EKSTREMT BEARISH (Crowded Shorts)")
        
    # 2. Whale Conviction (Positions vs Accounts)
    # Hvis posisjons-ratio er mye høyere enn konto-ratio, betyr det at de største whalene tar større veddemål enn de mindre whalene.
    if top_pos_ratio > (top_acc_ratio * 1.1):
        signals.append("Whales satser TUNG LONG (High Conviction)")
    elif top_pos_ratio < (top_acc_ratio * 0.9):
        signals.append("Whales satser TUNG SHORT (High Conviction)")
        
    # 3. Smart Money vs Retail Divergence
    if global_ratio > 1.2 and top_pos_ratio < 0.9:
        signals.append("⚠️ DIVERGENS: Retail kjøper, Whales selger (Smart Money Distribution)")
    elif global_ratio < 0.8 and top_pos_ratio > 1.1:
        signals.append("💎 DIVERGENS: Retail selger, Whales kjøper (Smart Money Accumulation)")
        
    return " + ".join(signals) if signals else "Ingen ekstrem divergens"

# --- MAIN ENDPOINTS ---

@app.get("/view/{ticker}")
async def get_analysis(ticker: str):
    """
    Hovedfunksjonen som Mode 7 kaller. Returnerer HTML-tabell med ferdigtygget analyse.
    """
    symbol = ticker.upper() + "USDT"
    
    async with aiohttp.ClientSession() as session:
        # 1. Hent Spot Klines for CVD (Pris + Volum)
        klines_url = f"{DOMAIN_SPOT}/api/v3/klines"
        klines_params = {"symbol": symbol, "interval": "15m", "limit": 20} # Siste 5 timer
        
        # 2. Hent Sentiment Data (Futures)
        # Merk: period="15m" for å matche klines
        sentiment_params = {"symbol": symbol, "period": "15m", "limit": 1}
        
        task_klines = fetch_url(session, klines_url, klines_params)
        task_global = fetch_url(session, f"{DOMAIN_FUTURES}/futures/data/globalLongShortAccountRatio", sentiment_params)
        task_top_acc = fetch_url(session, f"{DOMAIN_FUTURES}/futures/data/topLongShortAccountRatio", sentiment_params)
        task_top_pos = fetch_url(session, f"{DOMAIN_FUTURES}/futures/data/topLongShortPositionRatio", sentiment_params)
        
        klines, global_data, top_acc_data, top_pos_data = await asyncio.gather(task_klines, task_global, task_top_acc, task_top_pos)

        if not klines or not isinstance(klines, list):
            return HTMLResponse(content=f"<h1>Fant ingen data for {symbol}</h1>", status_code=404)

        # --- BEREGN CVD & ANALYSE ---
        
        # Pakk ut sentiment data (tar nyeste verdi)
        try:
            g_ratio = float(global_data[0]['longShortRatio']) if global_data else 1.0
            ta_ratio = float(top_acc_data[0]['longShortRatio']) if top_acc_data else 1.0
            tp_ratio = float(top_pos_data[0]['longShortRatio']) if top_pos_data else 1.0
        except:
            g_ratio, ta_ratio, tp_ratio = 1.0, 1.0, 1.0

        sentiment_text = interpret_sentiment(g_ratio, ta_ratio, tp_ratio)

        # Bygg HTML
        html_content = f\"\"\"
        <html>
        <head>
            <style>
                body  font-family: -apple-system, sans-serif; padding: 20px; background: #191919; color: #e0e0e0; 
                h2  border-bottom: 1px solid #333; padding-bottom: 10px; 
                .card  background: #252525; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #333; 
                .metric  font-size: 0.8em; color: #888; 
                .val  font-size: 1.2em; font-weight: bold; 
                .bullish  color: #4caf50; 
                .bearish  color: #ff5252; 
                table  width: 100%; border-collapse: collapse; font-size: 0.9em; 
                th  text-align: left; color: #888; border-bottom: 1px solid #333; padding: 8px; 
                td  padding: 8px; border-bottom: 1px solid #2a2a2a; 
                .row-bull  background: rgba(76, 175, 80, 0.1); 
                .row-bear  background: rgba(255, 82, 82, 0.1); 
            </style>
        </head>
        <body>
            <h2>🔭 Mode 7 X-Ray: {symbol}</h2>
            
            <div class="card">
                <div style="font-size: 1.2em; margin-bottom: 10px;"><strong>🧠 Sentiment Analyse (NÅ):</strong></div>
                <div style="color: #FFD700; font-size: 1.1em;">{sentiment_text}</div>
                <br>
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px;">
                    <div>
                        <div class="metric">Retail (Global L/S)</div>
                        <div class="val { 'bullish' if g_ratio > 1.0 else 'bearish' }">{g_ratio}</div>
                    </div>
                    <div>
                        <div class="metric">Whale Accounts</div>
                        <div class="val { 'bullish' if ta_ratio > 1.0 else 'bearish' }">{ta_ratio}</div>
                    </div>
                    <div>
                        <div class="metric">Whale Positions</div>
                        <div class="val { 'bullish' if tp_ratio > 1.0 else 'bearish' }">{tp_ratio}</div>
                    </div>
                </div>
            </div>

            <h3>📊 Siste 5 Timer (15m Candles)</h3>
            <table>
                <tr>
                    <th>Tid</th>
                    <th>Pris</th>
                    <th>CVD (Spot Vol)</th>
                    <th>Signal</th>
                </tr>
        \"\"\"

        cvd_cum = 0
        
        # Vi itererer gjennom klines for å beregne Spot CVD
        # Binance Kline Index: 0=OpenTime, 4=ClosePrice, 5=Vol, 9=TakerBuyBaseVol
        for k in klines:
            close_time = datetime.fromtimestamp(k[0] / 1000, timezone.utc).strftime('%H:%M')
            close_price = float(k[4])
            total_vol = float(k[5])
            taker_buy_vol = float(k[9])
            taker_sell_vol = total_vol - taker_buy_vol
            
            delta = taker_buy_vol - taker_sell_vol
            cvd_cum += delta
            
            # Enkel fargekoding
            row_class = "row-bull" if delta > 0 else "row-bear"
            delta_str = f"{'+' if delta > 0 else ''}{format_number(delta)}"
            
            # Tolkning for tabell
            if delta > 0:
                signal = "Spot Kjøper"
            else:
                signal = "Spot Selger"

            html_content += f\"\"\"
                <tr class="{row_class}">
                    <td>{close_time}</td>
                    <td>${close_price:.2f}</td>
                    <td>{delta_str}</td>
                    <td>{signal}</td>
                </tr>
            \"\"\"

        html_content += \"\"\"
            </table>
            <p style="color: #666; font-size: 0.8em; margin-top: 20px;">v8.0 - Retail vs Whale Edition</p>
        </body>
        </html>
        \"\"\"
        
        return HTMLResponse(content=html_content)

@app.get("/")
def read_root():
    return {"Status": "CVD API v8.0 is Online", "Mode": "Retail vs Whale Sentiment"}
