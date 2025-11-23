from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timezone

app = FastAPI(title="CVD API v8.2 - Actionable Analysis", version="8.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

DOMAIN_SPOT = "https://api.binance.com"
DOMAIN_FUTURES = "https://fapi.binance.com"

async def fetch_url(session, url):
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return None

# --- WHALE & RETAIL ANALYSIS ENGINE (v8.2 ACTIONABLE) ---
def get_signal(price_ch, cvd_val, whale_ls, retail_ls):
    """
    v8.2 ACTIONABLE ANALYSIS:
    - CVD-aware parabolic signals (backed vs fake)
    - Confidence scores for whale signals
    - Entry/Exit guidance in breakdowns
    - Multi-condition checks for capitulation
    - Concrete numbers in all descriptions
    """
    
    # Default
    head = "⚖️ NØYTRAL"; desc = "Ingen klare avvik."; col = "#888"
    
    # PRIORITY 0: EXTREME PARABOLIC MOVES (>20%)
    if abs(price_ch) > 20:
        if price_ch > 0:
            # Parabolic PUMP - check CVD backing
            if cvd_val > 50_000_000:
                head = "🚀 PARABOLIC RALLY (BACKED)"
                desc = f"Ekstrem oppgang +{price_ch:.1f}% MED stor Spot CVD ${cvd_val/1_000_000:+.1f}M. Legitimt momentum, men vurder profit på ekstreme nivåer."
                col = "#00ff00"
            elif cvd_val < -20_000_000:
                head = "⚠️ PARABOLIC FAKE PUMP"
                desc = f"Ekstrem oppgang +{price_ch:.1f}% men CVD negativ ${cvd_val/1_000_000:.1f}M! Retail L/S {retail_ls:.2f}. Reversal imminent - EXIT!"
                col = "#ff6600"
            else:
                head = "🚀 PARABOLIC PUMP"
                desc = f"Ekstrem oppgang +{price_ch:.1f}% - Ofte FOMO-topp. Vurder take profit, CVD nøytral ${cvd_val/1_000_000:+.1f}M."
                col = "#ff00ff"
        else:
            # Parabolic DUMP - check capitulation conditions
            conditions_met = 0
            conditions_text = []
            
            if retail_ls < 0.8:
                conditions_met += 1
                conditions_text.append("Retail L/S < 0.8 ✓")
            else:
                conditions_text.append(f"Retail L/S {retail_ls:.2f} (need < 0.8)")
            
            if cvd_val > 0:
                conditions_met += 1
                conditions_text.append("CVD positiv ✓")
            else:
                conditions_text.append(f"CVD ${cvd_val/1_000_000:.1f}M (need positive)")
            
            if whale_ls > 1.2:
                conditions_met += 1
                conditions_text.append("Whales Long ✓")
            else:
                conditions_text.append(f"Whale L/S {whale_ls:.2f} (need > 1.2)")
            
            head = "💥 PARABOLIC DUMP"
            desc = f"Ekstrem nedgang {price_ch:.1f}% - Kapitulasjon! Entry conditions: {conditions_met}/3 met. "
            desc += " | ".join(conditions_text)
            
            if conditions_met >= 2:
                desc += " → CONSIDER staged entry."
                col = "#00ff9d"
            else:
                desc += " → TOO EARLY, wait."
                col = "#8B0000"
        
        return head, desc, col
    
    # PRIORITY 1: Momentum-divergence FAKE PUMP detection (15%+ rally with negative CVD)
    if price_ch > 15.0 and cvd_val < -20_000_000 and retail_ls > 2.5:
        head = "⚠️ PARABOLIC RALLY (DIVERGENCE)"
        desc = f"Pris +{price_ch:.1f}% men CVD ${cvd_val/1_000_000:.1f}M negativ + Retail overleveraged ({retail_ls:.2f}). FAKE PUMP reverserer snart - EXIT positions!"
        col = "#ff6600"
        return head, desc, col
    
    # PRIORITY 2: Extreme Retail FOMO (>3.0 threshold)
    if retail_ls > 3.0:
        if cvd_val < -50_000_000:
            head = "🚨 FAKE PUMP + RETAIL FOMO PEAK"
            desc = f"Retail ekstremt FOMO (L/S {retail_ls:.2f}), CVD svært negativ ${cvd_val/1_000_000:.1f}M. ADVARSEL-TOPP - EXIT all longs!"
            col = "#ff0000"
        elif cvd_val < 0:
            head = "🚨 RETAIL FOMO PEAK"
            desc = f"Retail ekstremt overleveraged Long (L/S {retail_ls:.2f}) + CVD negativ ${cvd_val/1_000_000:.1f}M. Sannsynlig topp - REDUCE exposure!"
            col = "#ff4d4d"
        else:
            head = "⚠️ RETAIL FOMO EKSTREMT"
            desc = f"Retail L/S {retail_ls:.2f} (>3.0 threshold). Crowd overleveraged Long. CVD ${cvd_val/1_000_000:+.1f}M støtter nå, men vær varsom."
            col = "#ffa500"
        return head, desc, col
    
    # PRIORITY 3: Retail FOMO warning (2.0-3.0) - CONTEXT-AWARE with actionable guidance
    if retail_ls > 2.0:
        if cvd_val < 0:
            if price_ch > 10.0:  # Strong rally
                head = "⚠️ RETAIL FOMO I STERK RALLY"
                desc = f"Pris +{price_ch:.1f}%, Retail overleveraged ({retail_ls:.2f}), CVD ${cvd_val/1_000_000:.1f}M negativ. TOPP nærmer seg - vurder take profit!"
                col = "#ff6b6b"
            elif price_ch > 5.0:  # Moderate rally
                head = "⚠️ RETAIL FOMO I RALLY"
                desc = f"Pris +{price_ch:.1f}%, Retail {retail_ls:.2f}, CVD negativ. Svak oppgang - REDUCE long exposure."
                col = "#ff8888"
            elif price_ch < -10.0:  # Severe breakdown
                # Check capitulation proximity
                if retail_ls < 2.3:
                    head = "⚠️ RETAIL FOMO I BREAKDOWN (LATE)"
                    desc = f"Pris {price_ch:.1f}%, Retail L/S {retail_ls:.2f} synker (fra >2.5). CVD ${cvd_val/1_000_000:.1f}M. Kapitulasjon nærmer seg - WATCH for Retail < 0.8."
                    col = "#ff9999"
                else:
                    head = "⚠️ RETAIL FOMO I BREAKDOWN"
                    desc = f"Pris {price_ch:.1f}%, Retail {retail_ls:.2f} fortsatt høy, CVD ${cvd_val/1_000_000:.1f}M. Kapitulasjon pågår - WAIT, for tidlig!"
                    col = "#ff4d4d"
            elif price_ch < -5.0:  # Moderate decline
                head = "⚠️ RETAIL FOMO I DECLINE"
                desc = f"Pris {price_ch:.1f}%, Retail {retail_ls:.2f}, CVD negativ. Nedgang med svak sentiment - WAIT."
                col = "#ff6b6b"
            else:  # Sideways
                head = "⚠️ RETAIL FOMO + CVD NEGATIV"
                desc = f"Retail overleveraged ({retail_ls:.2f}), CVD ${cvd_val/1_000_000:.1f}M. Mulig topp forming - REDUCE risk."
                col = "#ff6b6b"
        else:
            head = "⚠️ RETAIL FOMO"
            desc = f"Retail L/S {retail_ls:.2f} overleveraged. CVD ${cvd_val/1_000_000:+.1f}M støtter nå, men crowd positioning ekstrem - vær forsiktig."
            col = "#ffa500"
        return head, desc, col
    
    # PRIORITY 4: WHALE DIVERGENCE with confidence scoring
    # Scenario 1: Whale Accumulation
    if price_ch < -0.5 and whale_ls > 1.2:
        conditions_met = 0
        confidence = []
        
        # Check CVD support
        if cvd_val > 10_000_000:
            conditions_met += 1
            confidence.append(f"CVD ${cvd_val/1_000_000:+.1f}M ✓")
            col = "#00ff9d"
        elif cvd_val > 0:
            confidence.append(f"CVD ${cvd_val/1_000_000:+.1f}M (weak)")
            col = "#00ccff"
        else:
            confidence.append(f"CVD ${cvd_val/1_000_000:.1f}M (no support)")
            col = "#0099ff"
        
        # Check retail capitulation
        if retail_ls < 0.8:
            conditions_met += 1
            confidence.append(f"Retail {retail_ls:.2f} capitulating ✓")
        elif retail_ls < 1.5:
            confidence.append(f"Retail {retail_ls:.2f} (neutral)")
        else:
            confidence.append(f"Retail {retail_ls:.2f} (still elevated)")
        
        # Set signal based on confidence
        if conditions_met >= 2:
            head = "🐋 WHALE ACCUMULATION (HIGH CONVICTION)"
            desc = f"Pris {price_ch:.1f}%, Whales loading Longs ({whale_ls:.2f}). {' | '.join(confidence)}. STRONG BUY signal!"
        elif conditions_met == 1:
            head = "🐋 WHALE ACCUMULATION (CONFIRMED)"
            desc = f"Pris {price_ch:.1f}%, Whales accumulating ({whale_ls:.2f}). {' | '.join(confidence)}. CONSIDER entry."
        else:
            head = "🐋 WHALE ACCUMULATION (EARLY)"
            desc = f"Pris {price_ch:.1f}%, Whales L/S {whale_ls:.2f}. {' | '.join(confidence)}. TOO EARLY - wait for confirmation."
        
        return head, desc, col
    
    # Scenario 2: Whale Distribution
    elif price_ch > 0.5 and whale_ls < 0.8:
        head = "🐋 WHALE DISTRIBUTION"
        desc = f"Pris +{price_ch:.1f}%, men Whales shorting ({whale_ls:.2f}). "
        col = "#ff4d4d"
        
        if cvd_val < -10_000_000:
            desc += f"CVD ${cvd_val/1_000_000:.1f}M confirms. EXIT longs!"
            col = "#ff0000"
        else:
            desc += f"CVD ${cvd_val/1_000_000:+.1f}M mixed signal. REDUCE exposure."
        
        if retail_ls > 2.0:
            desc += f" Retail FOMO ({retail_ls:.2f}) buying top."
            col = "#ff0000"
        
        return head, desc, col
    
    # PRIORITY 5: RETAIL CONTRARIAN - Capitulation with entry guidance
    if retail_ls < 0.8:
        conditions_met = 0
        entry_check = []
        
        if price_ch < -0.5:
            conditions_met += 1
            entry_check.append("Price declining ✓")
        else:
            entry_check.append(f"Price +{price_ch:.1f}% (wait for dip)")
        
        if cvd_val > 0:
            conditions_met += 1
            entry_check.append(f"CVD ${cvd_val/1_000_000:+.1f}M ✓")
        else:
            entry_check.append(f"CVD ${cvd_val/1_000_000:.1f}M (wait for positive)")
        
        if whale_ls > 1.2:
            conditions_met += 1
            entry_check.append(f"Whales Long {whale_ls:.2f} ✓")
        else:
            entry_check.append(f"Whales {whale_ls:.2f} (neutral)")
        
        if conditions_met >= 2:
            head = "✅ RETAIL CAPITULATION (HIGH CONVICTION)"
            desc = f"Retail panikk (L/S {retail_ls:.2f}). {' | '.join(entry_check)}. STRONG BUY zone - staged entry!"
            col = "#00ff9d"
        elif cvd_val > 0:
            head = "✅ RETAIL CAPITULATION + SPOT SUPPORT"
            desc = f"Retail panikk ({retail_ls:.2f}), CVD ${cvd_val/1_000_000:+.1f}M. {' | '.join(entry_check)}. CONSIDER entry."
            col = "#00ccff"
        else:
            head = "⚠️ RETAIL CAPITULATION (EARLY)"
            desc = f"Retail panikk ({retail_ls:.2f}), men CVD ${cvd_val/1_000_000:.1f}M negativ. {' | '.join(entry_check)}. Wait for CVD confirmation."
            col = "#ffa500"
        
        return head, desc, col
    
    # PRIORITY 6: SPOT CVD CONFIRMATION (strong moves)
    if price_ch > 2.0 and cvd_val > 50_000_000:
        head = "✅ SPOT DRIVER"
        desc = f"Oppgang +{price_ch:.1f}% med stor Spot CVD ${cvd_val/1_000_000:+.1f}M. Sunn trend - HOLD positions."
        col = "#00ff9d"
        return head, desc, col
    
    if price_ch < -2.0 and cvd_val < -50_000_000:
        head = "❌ SPOT DUMP"
        desc = f"Nedgang {price_ch:.1f}% med stor CVD utstrømming ${cvd_val/1_000_000:.1f}M. Aggressivt salg - EXIT."
        col = "#ff4d4d"
        return head, desc, col
    
    # Spot absorption (reversal setup)
    if price_ch < -1.0 and cvd_val > 10_000_000:
        head = "🛡️ SPOT ABSORBERING"
        desc = f"Pris {price_ch:.1f}% ned men CVD ${cvd_val/1_000_000:+.1f}M positiv. Reversal-setup - WATCH for bounce."
        col = "#0099ff"
        return head, desc, col
    
    if price_ch > 1.0 and cvd_val < -10_000_000:
        head = "⚠️ SVAK OPPGANG"
        desc = f"Pris +{price_ch:.1f}% men CVD ${cvd_val/1_000_000:.1f}M negativ. Mangler kjøpere - mulig felle, REDUCE longs."
        col = "#ffa500"
        return head, desc, col
    
    # Standard classifications for moderate moves
    if price_ch > 0.5:
        if cvd_val > 0:
            head = "🚀 SUNN OPPGANG"
            desc = f"Pris +{price_ch:.1f}% støttet av CVD ${cvd_val/1_000_000:+.1f}M. Retail {retail_ls:.2f}. Trend-following OK."
            col = "#00ff9d"
        else:
            head = "⚠️ SVAK OPPGANG"
            desc = f"Pris +{price_ch:.1f}%, men CVD ${cvd_val/1_000_000:.1f}M negativ. Retail {retail_ls:.2f}. Svak - vær varsom."
            col = "#ffa500"
        return head, desc, col
    
    if price_ch < -0.5:
        if cvd_val > 0:
            head = "🛡️ SPOT ABSORBERING"
            desc = f"Pris {price_ch:.1f}% ned, men CVD ${cvd_val/1_000_000:+.1f}M kjøper imot. Mulig bunn."
            col = "#0099ff"
        else:
            head = "📉 AGGRESSIVT SALG"
            desc = f"Pris {price_ch:.1f}% ned støttet av CVD ${cvd_val/1_000_000:.1f}M. Retail {retail_ls:.2f}. Continued weakness."
            col = "#ffcccc"
        return head, desc, col
    
    # NEUTRAL: Ingen klare signaler
    return head, desc, col

async def get_sentiment_history(session, symbol, period, limit, endpoint):
    """
    Henter sentiment history med DEBUG-logging for å oppdage frosne data
    """
    # Mapping limits
    req_limit = limit
    if period == '1w': period = '1d'; req_limit = limit * 7
    if period == '1M': period = '1d'; req_limit = limit * 30
    if req_limit > 499: req_limit = 499
    
    url = f"{DOMAIN_FUTURES}/futures/data/{endpoint}?symbol={symbol}&period={period}&limit={req_limit}"
    data = await fetch_url(session, url)
    
    res_map = {}
    if data:
        # DEBUG: Check for frozen/identical data
        ratios = [float(item['longShortRatio']) for item in data]
        unique_ratios = set(ratios)
        
        if len(unique_ratios) == 1:
            print(f"⚠️ DEBUG WARNING: All {endpoint} ratios are IDENTICAL ({ratios[0]:.2f}) for {symbol} - Data may be frozen!")
        elif len(unique_ratios) < 3:
            print(f"⚠️ DEBUG WARNING: Only {len(unique_ratios)} unique {endpoint} ratios for {symbol} - Low variance detected!")
        else:
            print(f"✅ DEBUG OK: {endpoint} has {len(unique_ratios)} unique ratios for {symbol} (healthy variance)")
        
        for item in data:
            val = float(item['longShortRatio'])
            res_map[int(item['timestamp'])] = val
    else:
        print(f"❌ DEBUG ERROR: No data returned from {endpoint} for {symbol}")
    
    return res_map

def get_closest(ts, data_map):
    if not data_map: return 0.0
    if ts in data_map: return data_map[ts]
    keys = list(data_map.keys())
    if not keys: return 0.0
    closest_ts = min(keys, key=lambda k: abs(k - ts))
    return data_map[closest_ts]

async def get_kline_analysis(session, symbol, interval, limit):
    # 1. Spot Price & CVD
    kline_url = f"{DOMAIN_SPOT}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    klines = await fetch_url(session, kline_url)
    
    # 2. Whale Sentiment (Top Trader Positions)
    whale_task = get_sentiment_history(session, symbol, interval, limit, "topLongShortPositionRatio")
    # 3. Retail Sentiment (Global Accounts)
    retail_task = get_sentiment_history(session, symbol, interval, limit, "globalLongShortAccountRatio")
    
    whale_map, retail_map = await asyncio.gather(whale_task, retail_task)
    
    rows = []
    if klines:
        for k in klines:
            ts = int(k[0])
            dt_obj = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            
            open_p = float(k[1]); close_p = float(k[4])
            buy_vol = float(k[10]); sell_vol = float(k[7]) - buy_vol
            
            price_ch = ((close_p - open_p) / open_p) * 100
            cvd = buy_vol - sell_vol
            
            # Sentiment Lookup
            w_ls = get_closest(ts, whale_map)
            r_ls = get_closest(ts, retail_map)
            
            # Labels
            if interval == '15m': label = dt_obj.strftime("%d/%m %H:%M")
            elif interval == '1h': label = dt_obj.strftime("%d/%m %H:00")
            elif interval == '1d': label = dt_obj.strftime("%Y-%m-%d")
            elif interval == '1w': label = f"Uke {dt_obj.strftime('%W')}"
            elif interval == '1M': label = dt_obj.strftime("%B")
            else: label = str(ts)
            
            head, desc, col = get_signal(price_ch, cvd, w_ls, r_ls)
            
            rows.append({
                "label": label, "price_ch": price_ch, "cvd": cvd,
                "w_ls": w_ls, "r_ls": r_ls,
                "head": head, "desc": desc, "col": col
            })
    
    return list(reversed(rows))

def render_table_rows(rows):
    html = ""
    for r in rows:
        p_col = "#00ff9d" if r['price_ch'] >= 0 else "#ff4d4d"
        
        if abs(r['cvd']) > 1_000_000: cvd_fmt = f"${r['cvd']/1_000_000:+.1f}M"
        else: cvd_fmt = f"${r['cvd']/1_000:+.0f}k"
        cvd_col = "#00ff9d" if r['cvd'] >= 0 else "#ff4d4d"
        
        # Whale Color: Green if Long Bias (>1.2), Red if Short Bias (<0.8)
        w_col = "#00ff9d" if r['w_ls'] > 1.2 else ("#ff4d4d" if r['w_ls'] < 0.8 else "#aaa")
        
        # Retail Color: Red if overly Long (>2.0 - contrarian), Green if Fearful (<0.8)
        r_col = "#ff4d4d" if r['r_ls'] > 2.0 else ("#00ff9d" if r['r_ls'] < 0.8 else "#aaa")
        
        html += f"""
        <tr style="border-bottom: 1px solid #222;">
        <td style="padding: 8px; color: #aaa; font-size: 0.9em; white-space: nowrap;">{r['label']}</td>
        <td style="padding: 8px; color: {p_col}; font-weight: bold;">{r['price_ch']:+.2f}%</td>
        <td style="padding: 8px; color: {cvd_col}; font-family: monospace;">{cvd_fmt}</td>
        <td style="padding: 8px; color: {w_col}; font-weight: bold;">{r['w_ls']:.2f}</td>
        <td style="padding: 8px; color: {r_col};">{r['r_ls']:.2f}</td>
        <td style="padding: 8px;">
        <div style="color: {r['col']}; font-weight: bold; font-size: 0.8em;">{r['head']}</div>
        <div style="color: #666; font-size: 0.7em;">{r['desc']}</div>
        </td>
        </tr>
        """
    return html

def generate_html_page(symbol, monthly, weekly, daily, hourly, min15):
    return f"""
    <div class="coin-container" style="margin-bottom: 60px; background: #111; padding: 20px; border-radius: 8px; border: 1px solid #333;">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 20px;">
    <h1 style="margin: 0; font-size: 2em;">{symbol.replace('USDT','')} Analysis</h1>
    <div style="font-size: 0.8em; color: #666;">v8.2 Actionable</div>
    </div>
    <style>
    table  width: 100%; border-collapse: collapse; font-size: 0.9em; margin-bottom: 30px; 
    th  text-align: left; padding: 8px; border-bottom: 2px solid #444; color: #aaa; text-transform: uppercase; font-size: 0.7em; 
    </style>
    
    <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">⚡ Siste 48 Timer - Kvarter (Sniper)</h3>
    <table><tr><th width="10%">Tid</th><th width="10%">Pris %</th><th width="15%">Spot CVD</th><th width="10%">🐋 Whale L/S</th><th width="10%">🐟 Retail L/S</th><th width="45%">Mode 7 Analyse</th></tr>{render_table_rows(min15)}</table>
    
    <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">⏱️ Siste 7 Dager - Time (Hourly)</h3>
    <table><tr><th>Tid</th><th>Pris %</th><th>Spot CVD</th><th>🐋 Whale</th><th>🐟 Retail</th><th>Analyse</th></tr>{render_table_rows(hourly)}</table>
    
    <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">📅 Siste 30 Dager - Dag (Daily)</h3>
    <table><tr><th>Dato</th><th>Pris %</th><th>Spot CVD</th><th>🐋 Whale</th><th>🐟 Retail</th><th>Analyse</th></tr>{render_table_rows(daily)}</table>
    
    <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">📆 Siste 24 Uker (Weekly)</h3>
    <table><tr><th>Uke</th><th>Pris %</th><th>Spot CVD</th><th>🐋 Whale</th><th>🐟 Retail</th><th>Analyse</th></tr>{render_table_rows(weekly)}</table>
    
    <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">🌕 Siste 6 Måneder (Monthly)</h3>
    <table><tr><th>Måned</th><th>Pris %</th><th>Spot CVD</th><th>🐋 Whale</th><th>🐟 Retail</th><th>Analyse</th></tr>{render_table_rows(monthly)}</table>
    </div>
    """

BASE_HTML = """<html><head><title>Mode 7: Whale Watch</title><style>body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #050505; color: #e0e0e0; padding: 20px; max-width: 1200px; margin: 0 auto; }</style></head><body>"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_coin_data(session, sym) for sym in symbols]
        results = await asyncio.gather(*tasks)
        html = BASE_HTML + "".join(results) + "</body></html>"
    return html

@app.get("/html/{symbol}", response_class=HTMLResponse)
async def single_coin(symbol: str):
    clean = symbol.upper()
    if "USDT" not in clean: clean += "USDT"
    async with aiohttp.ClientSession() as session:
        html = BASE_HTML + await fetch_coin_data(session, clean) + "</body></html>"
    return html

async def fetch_coin_data(session, sym):
    # 1. Monthly (6 mnd)
    t_mon = get_kline_analysis(session, sym, "1M", 6)
    # 2. Weekly (24 uker)
    t_wek = get_kline_analysis(session, sym, "1w", 24)
    # 3. Daily (30 dager)
    t_day = get_kline_analysis(session, sym, "1d", 30)
    # 4. Hourly (168 timer = 7 dager)
    t_hor = get_kline_analysis(session, sym, "1h", 168)
    # 5. 15-Min (192 intervaller = 48 timer)
    t_min15 = get_kline_analysis(session, sym, "15m", 192)
    
    mon, wek, day, hor, min15 = await asyncio.gather(t_mon, t_wek, t_day, t_hor, t_min15)
    return generate_html_page(sym, mon, wek, day, hor, min15)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
