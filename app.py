import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import date

st.set_page_config(page_title="ETF Returns Screener", layout="wide")

ETF_TICKERS = [
    {"symbol": "NIFTYBEES.NS", "name": "Nippon India ETF Nifty 50 BeES"},
    {"symbol": "BANKBEES.NS", "name": "Nippon India ETF Nifty Bank BeES"},
    {"symbol": "JUNIORBEES.NS", "name": "Nippon India ETF Nifty Next 50 Junior BeES"},
    {"symbol": "ITBEES.NS", "name": "Nippon India ETF Nifty IT"},
    {"symbol": "MID150BEES.NS", "name": "Nippon India ETF Nifty Midcap 150"},
    {"symbol": "PHARMABEES.NS", "name": "Nippon India ETF Nifty Pharma BeES"},
    {"symbol": "ICICIBANKP.NS", "name": "ICICI Prudential Nifty Private Bank ETF"},
    {"symbol": "METALIETF.NS", "name": "ICICI Prudential Nifty Metal ETF"},
    {"symbol": "ICICIFMCG.NS", "name": "ICICI Prudential Nifty FMCG ETF"},
    {"symbol": "OILIETF.NS", "name": "ICICI Prudential Nifty Oil & Gas ETF"},
    {"symbol": "CPSEETF.NS", "name": "CPSE ETF"},
    {"symbol": "AUTOBEES.NS", "name": "Nippon India Nifty Auto ETF"},
    {"symbol": "HNGSNGBEES.NS", "name": "Nippon India ETF Hang Seng BeES"},
    {"symbol": "HEALTHIETF.NS", "name": "ICICI Prudential Nifty Healthcare ETF"},
    {"symbol": "NV20IETF.NS", "name": "ICICI Prudential NV20 ETF"},
]

# Cache keyed by symbol only, fetching max data to avoid redownloading on date changes
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
        for idx, item in enumerate(ETF_TICKERS):
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
