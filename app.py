import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import date
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="ETF Returns Screener", layout="wide")

conn = st.connection("gsheets", type=GSheetsConnection)

# Initialize ETF tickers with robust header cleanup and default Nifty 50 Injection
if "etf_tickers" not in st.session_state:
    try:
        df_etfs = conn.read(usecols=[0, 1])
        df_etfs.columns = [str(col).strip().lower() for col in df_etfs.columns]
        
        if "symbol" in df_etfs.columns and "name" in df_etfs.columns:
            df_etfs = df_etfs.dropna(subset=["symbol"])
            df_etfs["symbol"] = df_etfs["symbol"].astype(str).str.strip().str.upper()
            df_etfs["name"] = df_etfs["name"].astype(str).str.strip()
            
            # Filter out ^NSEI from the incoming list to prevent any duplicate bugs
            user_list = [t for t in df_etfs[["symbol", "name"]].to_dict("records") if t["symbol"] != "^NSEI"]
            
            # Inject Nifty 50 Index firmly at index 0
            st.session_state.etf_tickers = [{"symbol": "^NSEI", "name": "Nifty 50 Index"}] + user_list
        else:
            st.error("Sheet must contain 'symbol' and 'name' columns.")
            st.session_state.etf_tickers = [{"symbol": "^NSEI", "name": "Nifty 50 Index"}]
    except Exception as e:
        st.error(f"Google Sheets connection failed: {str(e)}")
        st.session_state.etf_tickers = [{"symbol": "^NSEI", "name": "Nifty 50 Index"}]

def save_to_gsheets():
    # Keep Google Sheet database clean by filtering out the default embedded index
    user_tickers = [t for t in st.session_state.etf_tickers if t["symbol"] != "^NSEI"]
    updated_df = pd.DataFrame(user_tickers)
    conn.update(data=updated_df)
    st.cache_data.clear()

@st.cache_data(show_spinner=False)
def fetch_ticker_data(symbol):
    try:
        hist = yf.Ticker(symbol).history(period="15y")
        if hist.empty:
            return None
        hist.index = hist.index.tz_localize(None)
        return hist['Close']
    except Exception:
        return None

def get_price_on_or_before(series, target_date):
    if series is None or series.empty:
        return None
    target_dt = pd.to_datetime(target_date)
    valid_dates = series.index[series.index <= target_dt]
    if valid_dates.empty:
        return None
    return float(series.loc[valid_dates.max()])

def get_ema_on_or_before(series, span, target_date):
    if series is None or series.empty or len(series) < span:
        return None
    ema_series = series.ewm(span=span, adjust=False).mean()
    return get_price_on_or_before(ema_series, target_date)

def format_return(current_price, past_price):
    if current_price is None or past_price is None or past_price == 0:
        return "N/A"
    ret = ((current_price - past_price) / past_price) * 100
    return f"+{ret:.2f}%" if ret > 0 else f"{ret:.2f}%"

def color_returns(val):
    if not isinstance(val, str):
        return ""
    if val.startswith("+"):
        return "color: green;"
    elif val.startswith("-"):
        return "color: red;"
    return ""

st.title("ETF Returns Screener")

col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    from_date = st.date_input("From Date", value=pd.to_datetime("today").date() - pd.DateOffset(years=10))
with col2:
    to_date = st.date_input("To Date", value=pd.to_datetime("today").date())

with st.expander("Manage ETFs"):
    add_c1, add_c2, add_c3 = st.columns([2, 3, 1])
    with add_c1:
        new_sym = st.text_input("New Symbol (e.g., INFRABEES.NS)")
    with add_c2:
        new_name = st.text_input("New ETF Name")
    with add_c3:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("Add ETF"):
            if new_sym and new_name:
                clean_sym = new_sym.strip().upper()
                if not any(t["symbol"] == clean_sym for t in st.session_state.etf_tickers):
                    st.session_state.etf_tickers.append({"symbol": clean_sym, "name": new_name.strip()})
                    save_to_gsheets()
                    st.rerun()
    
    st.divider()
    
    rem_options = [t["symbol"] for t in st.session_state.etf_tickers if t["symbol"] != "^NSEI"]
    if rem_options:
        rem_c1, rem_c2 = st.columns([4, 1])
        with rem_c1:
            rem_sym = st.selectbox("Select ETF to Remove", options=rem_options)
        with rem_c2:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            if st.button("Remove ETF") and rem_sym:
                st.session_state.etf_tickers = [t for t in st.session_state.etf_tickers if t["symbol"] != rem_sym]
                save_to_gsheets()
                st.rerun()
    else:
        st.info("No custom tickers found. Add your specific ETFs above.")

if st.button("SCAN"):
    if to_date < from_date:
        st.error("Error: 'To Date' cannot be before 'From Date'.")
        st.stop()
    if to_date > date.today():
        st.error("Error: 'To Date' cannot be in the future.")
        st.stop()

    results = []
    
    offsets = {
        "1D": pd.DateOffset(days=1),
        "1W": pd.DateOffset(days=7),
        "1M": pd.DateOffset(months=1),
        "3M": pd.DateOffset(months=3),
        "6M": pd.DateOffset(months=6),
        "1Y": pd.DateOffset(years=1),
        "3Y": pd.DateOffset(years=3),
        "5Y": pd.DateOffset(years=5),
        "10Y": pd.DateOffset(years=10),
    }

    with st.spinner("Scanning markets..."):
        # 1. Fetch Nifty 50 Index upfront to configure global Trend Regime Filter
        nifty_series = fetch_ticker_data("^NSEI")
        n_lcp = get_price_on_or_before(nifty_series, to_date)
        n_ema100 = get_ema_on_or_before(nifty_series, 100, to_date)
        nifty_regime_bullish = (n_lcp > n_ema100) if (n_lcp is not None and n_ema100 is not None) else False

        # 2. Iterate and process all tickers
        for idx, item in enumerate(st.session_state.etf_tickers):
            sym = item["symbol"]
            
            # Reuse pre-fetched Nifty 50 data to save API latency
            series = nifty_series if sym == "^NSEI" else fetch_ticker_data(sym)
            
            lcp = get_price_on_or_before(series, to_date)
            ema50 = get_ema_on_or_before(series, 50, to_date)
            ema100 = get_ema_on_or_before(series, 100, to_date)
            ema200 = get_ema_on_or_before(series, 200, to_date)
            
            # 3. Evaluate criteria checks using floating-point decimals
            c1 = (lcp > ema100) if (lcp is not None and ema100 is not None) else False
            c2 = (ema50 > ema100) if (ema50 is not None and ema100 is not None) else False
            c3 = (ema100 > ema200) if (ema100 is not None and ema200 is not None) else False
            c4 = nifty_regime_bullish
            
            is_screened = c1 and c2 and c3 and c4
            
            row = {
                "Sr. No.": idx + 1,
                "Ticker": sym,
                "LCP": f"{lcp:.2f}" if lcp is not None else "N/A",
                "50 EMA": f"{ema50:.2f}" if ema50 is not None else "N/A",
                "100 EMA": f"{ema100:.2f}" if ema100 is not None else "N/A",
                "200 EMA": f"{ema200:.2f}" if ema200 is not None else "N/A",
                "_is_screened": is_screened  # Hidden metadata column for filtering
            }
            
            for period, offset in offsets.items():
                past_date = pd.to_datetime(to_date) - offset
                past_price = get_price_on_or_before(series, past_date)
                row[period] = format_return(lcp, past_price)
                
            results.append(row)

    st.success("Scan Completed.")
    
    if results:
        df = pd.DataFrame(results)
        columns_order = [
            "Sr. No.", "Ticker", "LCP", "50 EMA", "100 EMA", "200 EMA", 
            "1D", "1W", "1M", "3M", "6M", "1Y", "3Y", "5Y", "10Y", "_is_screened"
        ]
        df = df[columns_order]
        
        # Create UI Tabbed Layout
        tab1, tab2 = st.tabs(["📋 All ETFs", "🎯 Screened ETFs (Bullish Trend)"])
        
        # TAB 1: ALL TICKERS
        with tab1:
            df_display = df.drop(columns=["_is_screened"])
            styled_df = df_display.style.map(color_returns, subset=["1D", "1W", "1M", "3M", "6M", "1Y", "3Y", "5Y", "10Y"])
            
            st.dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Sr. No.": st.column_config.NumberColumn("Sr. No.", width="small"),
                    "Ticker": st.column_config.TextColumn("Ticker", width="medium"),
                }
            )
        
        # TAB 2: CRITERIA SCREENER
        with tab2:
            st.markdown("### 🚦 Screener Status")
            col_a, col_b, col_c, col_d = st.columns(4)
            with col_a:
                st.metric("1. Close > 100 EMA", "Active")
            with col_b:
                st.metric("2. 50 EMA > 100 EMA", "Active")
            with col_c:
                st.metric("3. 100 EMA > 200 EMA", "Active")
            with col_d:
                st.metric("4. Nifty 50 > 100 EMA", "🟢 Bullish" if nifty_regime_bullish else "🔴 Bearish")
            
            st.divider()

            if not nifty_regime_bullish:
                st.warning("⚠️ **Market Shield Active:** Nifty 50 is trading below its 100 EMA. Long setups are temporarily blocked to protect trading capital.")
            else:
                # Filter out the underlying index from the screened list for clear trading choices
                df_filtered = df[(df["_is_screened"] == True) & (df["Ticker"] != "^NSEI")].copy()
                
                if not df_filtered.empty:
                    # Clean up Serial Numbers sequentially for the screened list
                    df_filtered["Sr. No."] = range(1, len(df_filtered) + 1)
                    df_filtered_display = df_filtered.drop(columns=["_is_screened"])
                    
                    styled_filtered = df_filtered_display.style.map(color_returns, subset=["1D", "1W", "1M", "3M", "6M", "1Y", "3Y", "5Y", "10Y"])
                    
                    st.dataframe(
                        styled_filtered,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Sr. No.": st.column_config.NumberColumn("Sr. No.", width="small"),
                            "Ticker": st.column_config.TextColumn("Ticker", width="medium"),
                        }
                    )
                else:
                    st.info("No ETFs currently meet all 4 Bullish Trend criteria.")
        
        # Download Results setup
        csv = df.drop(columns=["_is_screened"]).to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Complete Results as CSV",
            data=csv,
            file_name="etf_returns.csv",
            mime="text/csv",
        )
    else:
        st.warning("No data generated. Please check your ETF ticker list configuration.")
