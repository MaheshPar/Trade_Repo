import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import date
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="ETF Returns Screener", layout="wide")

conn = st.connection("gsheets", type=GSheetsConnection)

# Initialize ETF tickers from Google Sheets into session state
if "etf_tickers" not in st.session_state:
    try:
        df_etfs = conn.read(worksheet="Sheet1", usecols=[0, 1])
        df_etfs = df_etfs.dropna(subset=["symbol"])
        st.session_state.etf_tickers = df_etfs.to_dict("records")
    except Exception:
        # Fallback to an empty list if sheet read fails entirely
        st.session_state.etf_tickers = []

def save_to_gsheets():
    updated_df = pd.DataFrame(st.session_state.etf_tickers)
    conn.update(worksheet="Sheet1", data=updated_df)
    st.cache_data.clear() # Clears GSheets read cache to ensure fresh reload

# Cache keyed on symbol only to prevent re-downloads when dates shift
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
            if new_sym and new_name and not any(t["symbol"] == new_sym.upper() for t in st.session_state.etf_tickers):
                st.session_state.etf_tickers.append({"symbol": new_sym.upper(), "name": new_name})
                save_to_gsheets()
                st.rerun()
    
    st.divider()
    
    if st.session_state.etf_tickers:
        rem_c1, rem_c2 = st.columns([4, 1])
        with rem_c1:
            rem_sym = st.selectbox("Select ETF to Remove", options=[t["symbol"] for t in st.session_state.etf_tickers])
        with rem_c2:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            if st.button("Remove ETF") and rem_sym:
                st.session_state.etf_tickers = [t for t in st.session_state.etf_tickers if t["symbol"] != rem_sym]
                save_to_gsheets()
                st.rerun()
    else:
        st.info("No tickers found. Add a ticker above.")

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

    with st.spinner("Scanning..."):
        for idx, item in enumerate(st.session_state.etf_tickers):
            sym = item["symbol"]
            series = fetch_ticker_data(sym)
            
            lcp = get_price_on_or_before(series, to_date)
            
            row = {
                "Sr. No.": idx + 1,
                "Ticker": sym,
                "LCP": f"{lcp:.2f}" if lcp is not None else "N/A"
            }
            
            for period, offset in offsets.items():
                past_date = pd.to_datetime(to_date) - offset
                past_price = get_price_on_or_before(series, past_date)
                row[period] = format_return(lcp, past_price)
                
            results.append(row)

    st.success("Scan Completed.")
    
    if results:
        df = pd.DataFrame(results)
        styled_df = df.style.map(color_returns, subset=["1D", "1W", "1M", "3M", "6M", "1Y", "3Y", "5Y", "10Y"])
        
        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Sr. No.": st.column_config.NumberColumn("Sr. No.", width="small"),
                "Ticker": st.column_config.TextColumn("Ticker", width="medium"),
                "LCP": st.column_config.TextColumn("LCP"),
            }
        )
        
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Results as CSV",
            data=csv,
            file_name="etf_returns.csv",
            mime="text/csv",
        )
    else:
        st.warning("No data generated. Please check your ETF ticker list configuration.")
