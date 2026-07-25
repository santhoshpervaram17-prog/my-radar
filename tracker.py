import streamlit as st
import pandas as pd
from fyers_apiv3 import fyersModel
import time
import datetime
import streamlit.components.v1 as components
import requests

# ==========================================
# 1. PAGE CONFIGURATION & THEME INJECTION
# ==========================================
st.set_page_config(page_title="Fyers Institutional Terminal", layout="wide")

st.markdown("""
    <style>
    /* Main Background & Fonts */
    .stApp { background-color: #F8FAFC; }
    h1, h2, h3 { color: #0F172A !important; font-family: 'Inter', sans-serif !important; font-weight: 700 !important; }
    
    /* Premium Metric Card Styling */
    .metric-card { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); margin-bottom: 15px; }
    .metric-label { font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; color: #64748B; font-weight: 600; margin-bottom: 8px; }
    .metric-value { font-size: 28px; font-weight: 800; color: #1E293B; }
    
    /* Sidebar Styling Override */
    section[data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #E2E8F0; }
    
    /* Login Button Styling */
    .login-btn { display: inline-block; padding: 15px 30px; font-size: 18px; font-weight: bold; color: white !important; background-color: #FF5722; border-radius: 8px; text-decoration: none; text-align: center; box-shadow: 0 4px 6px rgba(255, 87, 34, 0.3); transition: background-color 0.3s; }
    .login-btn:hover { background-color: #E64A19; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. INITIALIZE SESSION MEMORY
# ==========================================
if "master_alert_log" not in st.session_state:
    st.session_state.master_alert_log = []
if "oi_velocity_cache" not in st.session_state:
    st.session_state.oi_velocity_cache = {}
if "hz_alert_log" not in st.session_state:
    st.session_state.hz_alert_log = []
if "access_token" not in st.session_state:
    st.session_state.access_token = None

# ==========================================
# 3. SECURE CREDENTIALS (HARDCODE HERE)
# ==========================================
# 👇 PASTE YOUR DETAILS INSIDE THE QUOTES ON THESE 4 LINES 👇

APP_ID = "Z9FB1LHW3W-100"                # <--- LINE 40: Paste Fyers App ID (e.g., "ABC123XYZ-100")
SECRET_KEY = "1I254UJO93"            # <--- LINE 41: Paste Fyers Secret Key (Found next to App ID)
REDIRECT_URI = "https://myradar.streamlit.app"          # <--- LINE 42: URL of your dashboard (e.g., "https://my-radar.streamlit.app/" or "http://localhost:8501/")
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1517513971744374949/_dHMw432cuIMEmEwEt-zSwj3Up8txjHiuKzwQ32TpBmeZmnol408YlxwT0sHkgAWdfjy"   # <--- LINE 43: Paste Discord Webhook URL here

# 👆 ======================================================= 👆

# ==========================================
# 4. FYERS AUTO-LOGIN ENGINE
# ==========================================
def get_fyers_session():
    return fyersModel.SessionModel(
        client_id=APP_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URI,
        response_type="code",
        grant_type="authorization_code"
    )

# Check if we are returning from Fyers with an Auth Code in the URL
if not st.session_state.access_token:
    if "auth_code" in st.query_params:
        auth_code = st.query_params["auth_code"]
        
        try:
            session = get_fyers_session()
            session.set_token(auth_code)
            response = session.generate_token()
            
            if response.get("s") == "ok":
                st.session_state.access_token = response["access_token"]
                # Clear the URL params to prevent re-triggering on refresh
                st.query_params.clear()
                st.rerun()
            else:
                st.error(f"Fyers Login Failed: {response.get('message', 'Unknown Error')}")
                st.stop()
        except Exception as e:
            st.error(f"Authentication Error: {str(e)}")
            st.stop()

# ==========================================
# 5. SIDEBAR SETTINGS & DISCORD ENGINE
# ==========================================
st.sidebar.header("🎯 Watchlist Settings")

default_watchlist = "NSE:NIFTY50-INDEX, NSE:NIFTYBANK-INDEX, NSE:RELIANCE-EQ, NSE:HDFCBANK-EQ, BSE:SENSEX-INDEX"
watchlist_input = st.sidebar.text_area("Symbols (Comma Separated)", value=default_watchlist, height=100)

REFRESH_INTERVAL = st.sidebar.slider("Scan Frequency (Seconds)", min_value=30, max_value=300, value=60, step=10)
VELOCITY_THRESHOLD = st.sidebar.number_input("Velocity Alert Threshold", min_value=100, max_value=500000, value=5000, step=1000)

if st.sidebar.button("🗑️ Clear Audit Trail"):
    st.session_state.master_alert_log = []
    st.session_state.oi_velocity_cache = {}
    st.session_state.hz_alert_log = []
    st.sidebar.success("Database cleared.")

def play_sound_alarm():
    components.html("""<audio autoplay><source src="https://actions.google.com/sounds/v1/animations/notification.ogg" type="audio/ogg"></audio>""", height=0, width=0)

def send_discord_alert(message):
    if DISCORD_WEBHOOK_URL:
        payload = {"content": message}
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=2)
        except Exception:
            pass 

st.sidebar.markdown("---")
if st.sidebar.button("🔔 Test Discord Alert"):
    if DISCORD_WEBHOOK_URL != "":
        send_discord_alert("✅ **SYSTEM TEST:** Your Pro Institutional Radar is connected!")
        st.sidebar.success("Test message sent!")
    else:
        st.sidebar.error("Paste Discord Webhook URL in Line 43 first!")

if st.session_state.access_token:
    if st.sidebar.button("🔒 Logout (Reset Token)"):
        st.session_state.access_token = None
        st.rerun()

# ==========================================
# 6. CORE API FETCH LAYER
# ==========================================
def fetch_symbol_data(fyers_instance, symbol):
    try:
        spot_req = {"symbols": symbol}
        spot_res = fyers_instance.quotes(data=spot_req)
        
        if spot_res and spot_res.get('s') == 'error':
            return 0, None, "Normal", spot_res.get('message', 'API Rejected Quotes Request')

        current_price = 0
        if spot_res and spot_res.get('s') == 'ok':
            data_list = spot_res.get('d', [])
            if data_list and len(data_list) > 0:
                current_price = data_list[0].get('v', {}).get('lp', 0)
            
        payload = {"symbol": symbol, "strikecount": 15}
        chain_res = fyers_instance.optionchain(data=payload)
        
        if chain_res and chain_res.get('s') == 'error':
            return current_price, None, "Normal", chain_res.get('message', 'API Rejected Option Chain Request')
            
        chain_data = chain_res.get('data', {}) if chain_res and chain_res.get('s') == 'ok' else None

        vol_status = "Normal"
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        hist_payload = {"symbol": symbol, "resolution": "5", "date_format": "1", "range_from": today_str, "range_to": today_str, "cont_flag": "1"}
        hist_res = fyers_instance.history(data=hist_payload)
        
        if hist_res and hist_res.get('s') == 'ok' and 'candles' in hist_res and len(hist_res['candles']) > 20:
            df = pd.DataFrame(hist_res['candles'], columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
            latest_vol = df['volume'].iloc[-1]
            avg_vol = df['volume'].iloc[-21:-1].mean()
            if avg_vol > 0:
                vol_ratio = latest_vol / avg_vol
                if vol_ratio >= 2.5: vol_status = f"🚨 {vol_ratio:.1f}x SPIKE"
                elif vol_ratio >= 1.5: vol_status = f"⚠️ {vol_ratio:.1f}x High"
                
        return current_price, chain_data, vol_status, None
    except Exception as e:
        return 0, None, "Normal", f"Internal Script Error: {str(e)}"

# ==========================================
# 7. ANALYTICS ENGINE & MAIN PIPELINE
# ==========================================
def main():
    # If not logged in, show the Login Screen and stop execution
    if not st.session_state.access_token:
        st.title("🎯 Pro Institutional Unwinding Radar")
        if APP_ID and SECRET_KEY and REDIRECT_URI:
            session = get_fyers_session()
            auth_url = session.generate_authcode()
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.markdown(f'<div style="text-align: center;"><a href="{auth_url}" target="_self" class="login-btn">🔐 Click Here to Login to Fyers API</a></div>', unsafe_allow_html=True)
            st.markdown("<br><p style='text-align:center; color:#64748B;'>Fyers will redirect you back here automatically after logging in.</p>", unsafe_allow_html=True)
        else:
            st.warning("⚠️ Waiting for App ID, Secret Key, and Redirect URI. Please enter them in Lines 40-42 of the script.")
        return

    st.title("🎯 Pro Institutional Unwinding Radar")
    current_time_str = time.strftime("%H:%M:%S")
    alert_timestamp = time.strftime("%I:%M:%S %p")
    st.caption(f"✨ Terminal Active | Last Full Scan: **{current_time_str}** (Next cycle in {REFRESH_INTERVAL}s)")
    
    fyers = fyersModel.FyersModel(client_id=APP_ID, token=st.session_state.access_token, is_async=False, log_path="")
    symbols = [s.strip() for s in watchlist_input.split(',') if s.strip()]
    
    radar_results = []
    api_errors = []
    hz_data = [] 
    trigger_alarm_this_cycle = False
    
    my_bar = st.progress(0, text="Iterating market data frameworks...")

    for idx, symbol in enumerate(symbols):
        percent_complete = int(((idx + 1) / len(symbols)) * 100)
        my_bar.progress(percent_complete, text=f"Processing Option Vector: **{symbol}**")
        
        current_price, chain_data, vol_status, error_msg = fetch_symbol_data(fyers, symbol)
        
        if error_msg:
            api_errors.append(f"**{symbol}**: {error_msg}")
            
        time.sleep(0.4) 
        
        if current_price > 0 and chain_data and 'optionsChain' in chain_data:
            options_list = chain_data['optionsChain']
            parsed_calls, parsed_puts = [], []
            
            for contract in options_list:
                strike = contract.get('strike_price', 0)
                opt_type = contract.get('option_type', '')
                oi = contract.get('oi', 0)
                p_oi = contract.get('prev_oi', contract.get('prevOi', oi)) 
                
                if opt_type == 'CE': parsed_calls.append({'strike': strike, 'oi': oi, 'change_oi': oi - p_oi})
                elif opt_type == 'PE': parsed_puts.append({'strike': strike, 'oi': oi, 'change_oi': oi - p_oi})
                    
            df_calls, df_puts = pd.DataFrame(parsed_calls), pd.DataFrame(parsed_puts)
            
            if not df_calls.empty and not df_puts.empty:
                total_call_oi = df_calls['oi'].sum()
                total_put_oi = df_puts['oi'].sum()
                pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0

                all_strikes = sorted(list(set(df_calls['strike']).union(set(df_puts['strike']))))
                min_pain = float('inf')
                max_pain_strike = 0
                for test_strike in all_strikes:
                    call_pain = sum([max(0, test_strike - row['strike']) * row['oi'] for _, row in df_calls.iterrows()])
                    put_pain = sum([max(0, row['strike'] - test_strike) * row['oi'] for _, row in df_puts.iterrows()])
                    if (call_pain + put_pain) < min_pain:
                        min_pain = (call_pain + put_pain)
                        max_pain_strike = test_strike

                i_call_idx = df_calls['change_oi'].idxmax()
                i_put_idx = df_puts['change_oi'].idxmax()
                
                i_call_strike = df_calls.loc[i_call_idx, 'strike']
                call_change = df_calls.loc[i_call_idx, 'change_oi']
                i_put_strike = df_puts.loc[i_put_idx, 'strike']
                put_change = df_puts.loc[i_put_idx, 'change_oi']

                # --- VELOCITY ENGINE (WITH PRICE GUARDRAILS) ---
                current_call_oi = df_calls.loc[i_call_idx, 'oi']
                current_put_oi = df_puts.loc[i_put_idx, 'oi']
                
                cache_key_call = f"{symbol}_CE_{i_call_strike}"
                cache_key_put = f"{symbol}_PE_{i_put_strike}"
                cache_key_price = f"{symbol}_PRICE"
                
                prev_call_oi = st.session_state.oi_velocity_cache.get(cache_key_call, current_call_oi)
                prev_put_oi = st.session_state.oi_velocity_cache.get(cache_key_put, current_put_oi)
                prev_price = st.session_state.oi_velocity_cache.get(cache_key_price, current_price)
                
                call_velocity = current_call_oi - prev_call_oi
                put_velocity = current_put_oi - prev_put_oi
                price_velocity = current_price - prev_price
                
                st.session_state.oi_velocity_cache[cache_key_call] = current_call_oi
                st.session_state.oi_velocity_cache[cache_key_put] = current_put_oi
                st.session_state.oi_velocity_cache[cache_key_price] = current_price
                # -----------------------
                
                danger_zone = current_price * 0.003 
                clean_symbol = symbol.replace("NSE:", "").replace("BSE:", "").replace("MCX:", "").replace("-EQ", "").replace("-INDEX", "").replace("FUT", "")
                
                # ==========================================
                # NEW: HERO-ZERO PREDICTION ALGORITHM
                # ==========================================
                if "NIFTY" in clean_symbol or "SENSEX" in clean_symbol:
                    bias = "NEUTRAL"
                    reasons = []
                    confidence = 50
                    
                    call_pressure = call_change + (call_velocity * 10) 
                    put_pressure = put_change + (put_velocity * 10)
                    
                    if pcr < 0.85 and current_price <= (max_pain_strike + 20) and call_pressure > put_pressure:
                        bias = "BEARISH"
                        hero_strike = f"{int(min(i_put_strike, round(current_price / 50) * 50))} PE"  
                        zero_strike = f"{int(i_call_strike)} CE"
                        trigger = f"Break below {int(current_price - 5)}"
                        
                        reasons.append("✔ Below Max Pain" if current_price < max_pain_strike else "✔ At Max Pain Resistance")
                        reasons.append("✔ Heavy Call Writing" if call_change > 0 else "✔ Call Unwinding Trap Detected")
                        reasons.append("✔ PCR Falling / Bearish")
                        if call_velocity > put_velocity: reasons.append("✔ Aggressive Active CE Selling")
                        
                        confidence += 15 if pcr < 0.7 else 5
                        confidence += 10 if current_price < max_pain_strike else 0
                        confidence += 12 if call_velocity > 50000 else 0
                        
                    elif pcr > 1.15 and current_price >= (max_pain_strike - 20) and put_pressure > call_pressure:
                        bias = "BULLISH"
                        hero_strike = f"{int(max(i_call_strike, round(current_price / 50) * 50))} CE"
                        zero_strike = f"{int(i_put_strike)} PE"
                        trigger = f"Break above {int(current_price + 5)}"
                        
                        reasons.append("✔ Above Max Pain" if current_price > max_pain_strike else "✔ At Max Pain Support")
                        reasons.append("✔ Heavy Put Writing" if put_change > 0 else "✔ Put Unwinding Trap Detected")
                        reasons.append("✔ PCR Rising / Bullish")
                        if put_velocity > call_velocity: reasons.append("✔ Aggressive Active PE Selling")
                        
                        confidence += 15 if pcr > 1.3 else 5
                        confidence += 10 if current_price > max_pain_strike else 0
                        confidence += 12 if put_velocity > 50000 else 0
                        
                    else:
                        bias = "SIDEWAYS"
                        hero_strike = "Avoid (Premium Decay)"
                        zero_strike = f"{int(i_call_strike)} CE & {int(i_put_strike)} PE"
                        trigger = "Wait for Range Breakout"
                        reasons = ["✔ PCR is Neutral (0.85 - 1.15)", "✔ Conflicting Option Walls", "✔ High Theta Decay Risk"]
                        confidence = 45
                        
                    confidence = min(confidence, 99) 
                    
                    hz_data.append({
                        "Symbol": clean_symbol, "Spot": current_price, "Bias": bias,
                        "Hero Strike": hero_strike, "Zero Strike": zero_strike,
                        "Confidence": confidence, "Trigger": trigger, "Reasons": reasons
                    })

                    if bias in ["BULLISH", "BEARISH"]:
                        hz_alert_key = f"{clean_symbol}_{bias}_{hero_strike}"
                        if hz_alert_key not in st.session_state.hz_alert_log:
                            st.session_state.hz_alert_log.append(hz_alert_key)
                            hz_emoji = "🟢" if bias == "BULLISH" else "🔴"
                            hz_msg = (f"🦸‍♂️ **HERO-ZERO ALERT: {clean_symbol}** {hz_emoji}\n**Bias:** {bias} (Confidence: {confidence}%)\n**Spot:** ₹{current_price:,.2f}\n**Hero Strike (BUY):** {hero_strike}\n**Zero Strike (AVOID/SELL):** {zero_strike}\n**Trigger:** {trigger}\n\n**Reasons:**\n" + "\n".join(reasons))
                            send_discord_alert(hz_msg)
                            trigger_alarm_this_cycle = True

                # BREAKOUT/BREAKDOWN LOGIC WITH PRICE GUARDRAILS
                call_unwinding = (call_change < 0 or call_velocity <= -VELOCITY_THRESHOLD) and current_price >= (i_call_strike - danger_zone) and price_velocity >= -2.0
                put_unwinding = (put_change < 0 or put_velocity <= -VELOCITY_THRESHOLD) and current_price <= (i_put_strike + danger_zone) and price_velocity <= 2.0
                
                if call_unwinding:
                    status = "🚀 BREAKOUT EXPECTED"
                    trigger_alarm_this_cycle = True
                    already_logged = any(row['Timestamp'][:5] == alert_timestamp[:5] and row['Symbol'] == clean_symbol for row in st.session_state.master_alert_log)
                    if not already_logged:
                        st.session_state.master_alert_log.append({
                            "Timestamp": alert_timestamp, "Symbol": clean_symbol,
                            "Spot Price": f"₹ {current_price:,.2f}", "Strike": int(i_call_strike),
                            "Profile": "Resistance Collapse", 
                            "Net Volume Outflow": f"{int(call_change):,} (Rapid: {int(call_velocity):,})",
                            "Price Vel (60s)": f"{price_velocity:+.2f}"
                        })
                        msg = (f"🚀 **BREAKOUT ALERT: {clean_symbol}**\n**Resistance Collapse:** Strike {int(i_call_strike)}\n**Spot Price:** ₹{current_price:,.2f}\n**Price Vel (60s):** {price_velocity:+.2f} pts\n**Rapid Outflow:** {int(call_velocity):,}\n\n📊 **LIVE METRICS:**\n• **Live PCR:** {pcr}\n• **Max Pain:** {int(max_pain_strike)}\n• **CE Wall:** {int(call_change):+,} [{int(call_velocity):+,}]\n• **PE Wall:** {int(put_change):+,} [{int(put_velocity):+,}]\n• **Vol Anomaly:** {vol_status}")
                        send_discord_alert(msg)

                elif put_unwinding:
                    status = "🩸 BREAKDOWN EXPECTED"
                    trigger_alarm_this_cycle = True
                    already_logged = any(row['Timestamp'][:5] == alert_timestamp[:5] and row['Symbol'] == clean_symbol for row in st.session_state.master_alert_log)
                    if not already_logged:
                        st.session_state.master_alert_log.append({
                            "Timestamp": alert_timestamp, "Symbol": clean_symbol,
                            "Spot Price": f"₹ {current_price:,.2f}", "Strike": int(i_put_strike),
                            "Profile": "Support Collapse", 
                            "Net Volume Outflow": f"{int(put_change):,} (Rapid: {int(put_velocity):,})",
                            "Price Vel (60s)": f"{price_velocity:+.2f}"
                        })
                        msg = (f"🩸 **BREAKDOWN ALERT: {clean_symbol}**\n**Support Collapse:** Strike {int(i_put_strike)}\n**Spot Price:** ₹{current_price:,.2f}\n**Price Vel (60s):** {price_velocity:+.2f} pts\n**Rapid Outflow:** {int(put_velocity):,}\n\n📊 **LIVE METRICS:**\n• **Live PCR:** {pcr}\n• **Max Pain:** {int(max_pain_strike)}\n• **CE Wall:** {int(call_change):+,} [{int(call_velocity):+,}]\n• **PE Wall:** {int(put_change):+,} [{int(put_velocity):+,}]\n• **Vol Anomaly:** {vol_status}")
                        send_discord_alert(msg)
                else:
                    status = "✅ Stable Profile"
                    
                radar_results.append({
                    "Symbol": clean_symbol,
                    "Spot Price": f"₹ {current_price:,.2f}",
                    "Live PCR": pcr,
                    "Max Pain": float(max_pain_strike), 
                    "Res. Strike": float(i_call_strike),
                    "Call Change OI [60s Vel]": f"{int(call_change):+,} [{int(call_velocity):+,}]",
                    "Supp. Strike": float(i_put_strike),
                    "Put Change OI [60s Vel]": f"{int(put_change):+,} [{int(put_velocity):+,}]",
                    "5M Vol Anomaly": vol_status,
                    "Engine Status": status
                })

    my_bar.empty()
    if trigger_alarm_this_cycle: play_sound_alarm()

    # ==========================================
    # 8. PRO UI RENDER LAYER
    # ==========================================
    st.markdown("### 🖥️ Real-Time Institutional Asset Grid")
    
    if radar_results:
        radar_df = pd.DataFrame(radar_results)
        
        def style_master_grid(row):
            styles = [''] * len(row)
            pcr_val, status_val = row['Live PCR'], row['Engine Status']
            call_text, put_text = str(row['Call Change OI [60s Vel]']), str(row['Put Change OI [60s Vel]'])
            vol_text = str(row['5M Vol Anomaly'])
            
            if pcr_val > 1.2: styles[2] = 'color: #10B981; font-weight: 800;'
            elif pcr_val < 0.6: styles[2] = 'color: #EF4444; font-weight: 800;'
            else: styles[2] = 'color: #475569; font-weight: 600;'
            
            styles[3] = 'color: #4F46E5; font-weight: 800; background-color: #EEF2FF;'

            if "🚀" in status_val: styles[9] = 'background-color: #ECFDF5; color: #065F46; font-weight: 800;'
            elif "🩸" in status_val: styles[9] = 'background-color: #FEF2F2; color: #991B1B; font-weight: 800;'
            else: styles[9] = 'background-color: #F1F5F9; color: #475569; font-weight: 600;'
                
            styles[5] = 'color: #EF4444; font-weight: 700;' if call_text.startswith('-') else 'color: #10B981; font-weight: 600;'
            styles[7] = 'color: #EF4444; font-weight: 700;' if put_text.startswith('-') else 'color: #10B981; font-weight: 600;'
            
            if "🚨" in vol_text: styles[8] = 'color: #EF4444; font-weight: 800;'
            elif "⚠️" in vol_text: styles[8] = 'color: #F59E0B; font-weight: 700;'
            else: styles[8] = 'color: #64748B;'

            styles[0] = 'font-weight: 700; color: #0F172A;'
            styles[1] = 'font-weight: 700; color: #1E293B;'
            
            return styles

        styled_df = radar_df.style.apply(style_master_grid, axis=1)
        st.dataframe(styled_df, use_container_width=True, hide_index=True, height=350)
    else:
        if api_errors:
            st.error("🚨 Fyers API Errors Detected!")
            for err in set(api_errors):
                st.write(err)
            st.info("💡 Your Access Token might have expired. Click the Logout button in the sidebar to re-authenticate.")
        else:
            st.warning("⚠️ Market data pipeline ingestion failed or is empty. Please ensure the market is open.")

    # ==========================================
    # 9. HERO-ZERO PREDICTION ENGINE UI
    # ==========================================
    if hz_data:
        st.markdown("---")
        st.markdown("### 🦸‍♂️ Hero-Zero Expiry Predictor")
        st.caption("Algorithmic bias calculations for major indices.")
        
        cols = st.columns(len(hz_data))
        for idx, col in enumerate(cols):
            data = hz_data[idx]
            bias_color = "#10B981" if data['Bias'] == "BULLISH" else "#EF4444" if data['Bias'] == "BEARISH" else "#F59E0B"
            reasons_html = "".join([f"<li style='margin-bottom: 4px;'>{r}</li>" for r in data['Reasons']])
            
            col.markdown(f"""
            <div class="metric-card" style="border-top: 5px solid {bias_color};">
                <h3 style="margin-top: 0; color: #0F172A; text-align: center;">{data['Symbol']}</h3>
                <div style="font-family: monospace; font-size: 15px; color: #1E293B; line-height: 1.8;">
                    <span style="display:inline-block; width: 120px; color:#64748B;">Spot:</span> <b>{data['Spot']:,.2f}</b><br>
                    <span style="display:inline-block; width: 120px; color:#64748B;">Bias:</span> <b style="color: {bias_color};">{data['Bias']}</b><br>
                    <span style="display:inline-block; width: 120px; color:#64748B;">Hero Strike:</span> <b style="color: #4F46E5;">{data['Hero Strike']}</b><br>
                    <span style="display:inline-block; width: 120px; color:#64748B;">Zero Strike:</span> <b>{data['Zero Strike']}</b><br>
                    <span style="display:inline-block; width: 120px; color:#64748B;">Confidence:</span> <b>{data['Confidence']}%</b><br>
                    <span style="display:inline-block; width: 120px; color:#64748B;">Trigger:</span> <b>{data['Trigger']}</b>
                </div>
                <hr style="margin: 12px 0; border: 0; border-top: 1px solid #E2E8F0;">
                <p style="margin: 0 0 8px 0; font-weight: bold; color: #0F172A; font-size: 14px;">Reasons:</p>
                <ul style="margin: 0; padding-left: 20px; font-size: 13.5px; color: #475569; list-style-type: none; padding-left: 0;">
                    {reasons_html}
                </ul>
            </div>
            """, unsafe_allow_html=True)

    # ==========================================
    # 10. HISTORICAL AUDIT LOG
    # ==========================================
    st.markdown("---")
    st.markdown("### 📋 Automated Breakout Registry (Audit Trail)")
    
    if st.session_state.master_alert_log:
        history_df = pd.DataFrame(st.session_state.master_alert_log)
        col_c1, col_c2 = st.columns(2)
        with col_c1: st.markdown(f"""<div class="metric-card"><div class="metric-label">Total Logs Generated</div><div class="metric-value">{len(history_df)}</div></div>""", unsafe_allow_html=True)
        with col_c2: st.markdown(f"""<div class="metric-card"><div class="metric-label">Unique Volatility Strikes Hit</div><div class="metric-value">{history_df['Symbol'].nunique()}</div></div>""", unsafe_allow_html=True)
        st.dataframe(history_df, use_container_width=True, hide_index=True)
    else:
        st.info("No institutional exceptions logged today. Terminal monitoring stable boundaries.")

    # ==========================================
    # 11. LIVE COUNTDOWN & SAFE RERUN
    # ==========================================
    timer_placeholder = st.empty()
    for i in range(REFRESH_INTERVAL, 0, -1):
        timer_placeholder.caption(f"⏳ Next radar scan in **{i}** seconds...")
        time.sleep(1)

    st.rerun()

if __name__ == "__main__":
    main()
