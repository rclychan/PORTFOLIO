import json
import os
import textwrap
import pandas as pd
import numpy as np
import streamlit as st
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 設定儲存持倉紀錄與複利設定的本地檔案檔名
CONFIG_FILE = "holdings.json"
COMPOUND_CONFIG_FILE = "compound_config.json"
INIT_DATE_STR = "2026-10-08"
TRANSACTION_FILE = "transactions.csv"

# ---------------------------------------------------------
# 本地 JSON 檔案讀寫函數
# ---------------------------------------------------------
def load_config():
    default_config = {
        "betas": {"QTOP": 1.0, "QLD": 2.0, "BOXX": 0.0},
        "shares": {"QTOP": 400, "QLD": 150, "BOXX": 300},
        "new_capital_hkd": 0.0,
        "cumulative_new_capital_hkd": 0.0,
        "rebalance_count": 0,
        "initial_portfolio_hkd": None,
        "benchmark_base_prices": {}
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                for k, v in default_config.items():
                    if k not in config:
                        config[k] = v
                return config
        except Exception:
            return default_config
    return default_config

def save_config(config_data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=4)

def load_compound_config():
    default_compound = {
        "p1_name": "組合一 (固定定投)",
        "p1_init": 100000.0,
        "p1_monthly": 5000.0,
        "p1_rate": 10.0,
        "p1_years": 10,
        "p2_name": "組合二 (每年定投不同)",
        "p2_init": 100000.0,
        "p2_rate": 15.0,
        "p2_years": 10,
        "p2_schedule": [3000.0] * 10
    }
    if os.path.exists(COMPOUND_CONFIG_FILE):
        try:
            with open(COMPOUND_CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                for k, v in default_compound.items():
                    if k not in config:
                        config[k] = v
                return config
        except Exception:
            return default_compound
    return default_compound

def save_compound_config(data):
    with open(COMPOUND_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

saved_config = load_config()
saved_compound = load_compound_config()

# ---------------------------------------------------------
# 數值格式化與安全防呆輔助函數
# ---------------------------------------------------------
def fmt_money(val):
    try:
        return f"${val:,.2f} HKD"
    except Exception:
        return "$0.00 HKD"

def fmt_price(val):
    try:
        return f"${val:,.2f} USD"
    except Exception:
        return "$0.00 USD"

def is_valid_positive(val):
    try:
        return val is not None and np.isfinite(float(val)) and float(val) > 0
    except Exception:
        return False

def as_number_or_nan(val):
    try:
        return float(val)
    except Exception:
        return np.nan

# ---------------------------------------------------------
# 頁面標題與佈局設定
# ---------------------------------------------------------
st.set_page_config(
    page_title="Beta 組合監控與大盤比對工具", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------
# 側邊欄：佈景主題切換開關與完整深色/淺色 CSS 樣式控制
# ---------------------------------------------------------
st.sidebar.header("🎨 顯示設定")
is_dark_mode = st.sidebar.toggle("🌙 啟用深色模式 (Dark Mode)", value=False)

if is_dark_mode:
    st.markdown("""
    <style>
        /* 全局背景與主畫面深色化 */
        .main, .stApp { background-color: #0e1117 !important; color: #f8fafc !important; }
        
        /* 側邊欄全面深色與強制所有內部文字轉為淺色 */
        [data-testid="stSidebar"] { background-color: #111827 !important; color: #f8fafc !important; }
        [data-testid="stSidebar"] * { color: #f8fafc !important; }

        /* 全域文字、標題、標籤與說明強制轉為淺色 */
        h1, h2, h3, h4, h5, h6, p, span, label, div, .stMarkdown, .stCaption, .streamlit-expanderHeader { 
            color: #f8fafc !important; 
        }
        
        /* 區塊英文小標題 */
        .section-eyebrow {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: #94a3b8 !important;
            font-weight: 600;
            margin-bottom: 0.2rem;
        }
        
        /* 現代化深色微浮動卡片 */
        .metric-card {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid #334155;
            padding: 20px;
            border-radius: 16px;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            margin-bottom: 12px;
        }
        .metric-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.4);
        }

        /* 輸入框與選擇器深色適配 */
        div[data-baseweb="select"] > div, div[data-baseweb="input"] input, .stTextInput input, .stNumberInput input {
            background-color: #1e293b !important;
            color: #f8fafc !important;
            border-color: #334155 !important;
        }

        hr { border-color: #334155; margin: 1.5rem 0; }
    </style>
    """, unsafe_allow_html=True)
    plotly_template = "plotly_dark"
else:
    st.markdown("""
    <style>
        .main { background-color: #f8fafc; color: #0f172a; }
        h1, h2, h3, h4 { color: #0f172a; }
        
        .section-eyebrow {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: #64748b;
            font-weight: 600;
            margin-bottom: 0.2rem;
        }
        
        .metric-card {
            background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
            border: 1px solid #e2e8f0;
            padding: 20px;
            border-radius: 16px;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.03), 0 4px 6px -2px rgba(0, 0, 0, 0.02);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            margin-bottom: 12px;
        }
        .metric-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.05), 0 10px 10px -5px rgba(0, 0, 0, 0.02);
        }
        
        hr { border-color: #e2e8f0; margin: 1.5rem 0; }
    </style>
    """, unsafe_allow_html=True)
    plotly_template = "plotly_white"

st.title("📈 股票組合 Beta 監控與大盤表現追蹤儀表板")
st.caption("✨ 動態監控組合 Beta、壓力測試、多週期盈虧分析、雙組合複利試算與退休提領規劃")

# ---------------------------------------------------------
# 1. 側邊欄設定：動態新增/刪除資產、Beta、持股與偏離度閾值
# ---------------------------------------------------------
st.sidebar.header("⚙️ 1. 資產配置與管理")

with st.sidebar.expander("➕ 新增資產標的", expanded=False):
    new_ticker = st.text_input("股票代碼 (例: NVDA, TLT)").strip().upper()
    new_beta = st.number_input("預設 Beta", value=1.0, step=0.1)
    new_shares = st.number_input("初始持有股數", value=0, min_value=0, step=10)
    
    if st.button("確認新增標的", use_container_width=True):
        if new_ticker:
            if new_ticker in saved_config["shares"]:
                st.warning(f"⚠️ {new_ticker} 已存在！")
            else:
                saved_config["shares"][new_ticker] = int(new_shares)
                saved_config["betas"][new_ticker] = float(new_beta)
                save_config(saved_config)
                st.success(f"✅ 已加入 {new_ticker}")
                st.rerun()

with st.sidebar.expander("🗑️ 刪除現有資產", expanded=False):
    current_asset_list = list(saved_config["shares"].keys())
    if len(current_asset_list) > 0:
        remove_ticker = st.selectbox("選擇要移除的資產", options=current_asset_list)
        if st.button("確認刪除", use_container_width=True):
            if len(current_asset_list) <= 1:
                st.error("⚠️ 至少需保留一項資產！")
            else:
                del saved_config["shares"][remove_ticker]
                saved_config["betas"].pop(remove_ticker, None)
                save_config(saved_config)
                st.success(f"🗑️ 已移除 {remove_ticker}")
                st.rerun()

st.sidebar.subheader("📦 各資產 Beta 與股數")
asset_betas = {}
current_shares = {}
tickers = list(saved_config["shares"].keys())

for ticker in tickers:
    st.sidebar.markdown(f"**🔹 {ticker}**")
    col_b, col_s = st.sidebar.columns(2)
    with col_b:
        asset_betas[ticker] = col_b.number_input("Beta", value=float(saved_config["betas"].get(ticker, 1.0)), step=0.1, key=f"beta_{ticker}")
    with col_s:
        current_shares[ticker] = col_s.number_input("股數", value=int(saved_config["shares"].get(ticker, 0)), min_value=0, step=10, key=f"shares_{ticker}")

st.sidebar.subheader("💵 2. 資金與警示設定")
new_capital_hkd = st.sidebar.number_input("準備投入的新資金 (HKD)", value=float(saved_config.get("new_capital_hkd", 0.0)), min_value=0.0, step=1000.0)
cumulative_new_capital_hkd = st.sidebar.number_input("累積已投入新資金 (HKD)", value=float(saved_config.get("cumulative_new_capital_hkd", 0.0)), min_value=0.0, step=1000.0)
drift_threshold = st.sidebar.slider("🚨 權重偏離度警示閾值 (%)", value=5.0, min_value=1.0, max_value=20.0, step=0.5)

st.sidebar.subheader("🔢 3. 再平衡紀錄")
rebalance_count = st.sidebar.number_input("觸及再平衡總次數", value=int(saved_config.get("rebalance_count", 0)), min_value=0, step=1)

saved_config["betas"] = asset_betas
saved_config["shares"] = current_shares
saved_config["new_capital_hkd"] = new_capital_hkd
saved_config["cumulative_new_capital_hkd"] = cumulative_new_capital_hkd
saved_config["rebalance_count"] = rebalance_count
save_config(saved_config)

if st.sidebar.button("➕ 再平衡次數 +1", use_container_width=True):
    saved_config["rebalance_count"] = rebalance_count + 1
    save_config(saved_config)
    st.rerun()

# ---------------------------------------------------------
# 2. 抓取市場即時價格、詳細價位差值、漲跌幅與匯率
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_market_data(active_tickers):
    prices = {}
    price_diffs = {}
    price_changes = {}
    all_tickers = sorted(list(set(active_tickers + ["QTOP", "QLD", "QQQ", "SPY"])))
    try:
        df_m = yf.download(all_tickers, period="5d", progress=False)["Close"]
        if isinstance(df_m, pd.Series):
            df_m = df_m.to_frame()
        df_m = df_m.ffill().bfill()
        for ticker in all_tickers:
            if ticker in df_m.columns and len(df_m) >= 2:
                curr = float(df_m[ticker].iloc[-1])
                prev = float(df_m[ticker].iloc[-2])
                diff = curr - prev
                change_pct = ((curr - prev) / prev) * 100 if prev > 0 else 0.0
                prices[ticker] = round(curr, 2)
                price_diffs[ticker] = round(diff, 2)
                price_changes[ticker] = round(change_pct, 2)
            else:
                data = yf.Ticker(ticker)
                price = data.fast_info.get('lastPrice', 100.0)
                prices[ticker] = round(float(price if price else 100.0), 2)
                price_diffs[ticker] = 0.0
                price_changes[ticker] = 0.0
    except Exception:
        for ticker in all_tickers:
            prices[ticker] = 100.0
            price_diffs[ticker] = 0.0
            price_changes[ticker] = 0.0
    
    try:
        fx = yf.Ticker("USDHKD=X").fast_info.get('lastPrice', 7.82)
        usd_hkd = round(float(fx), 4)
    except Exception:
        usd_hkd = 7.8200

    return prices, price_diffs, price_changes, usd_hkd

prices, price_diffs, price_changes, usd_hkd_rate = fetch_market_data(tickers)

# 頂部操作列
col_btn, col_fx = st.columns([2, 3])
with col_btn:
    if st.button("🔄 更新當前股價與匯率", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
with col_fx:
    st.markdown(f"<div style='text-align: right; padding-top: 5px; opacity: 0.8;'>💱 即時匯率：<b>1 USD = {usd_hkd_rate:.4f} HKD</b></div>", unsafe_allow_html=True)

# ---------------------------------------------------------
# 3. 組合數值與總投入成本預先計算
# ---------------------------------------------------------
df = pd.DataFrame({
    "股票代碼": tickers,
    "單價 ($USD)": [prices.get(t, 100.0) for t in tickers],
    "持有股數": [current_shares[t] for t in tickers],
    "個股 Beta": [asset_betas[t] for t in tickers]
})

df["當前市值 ($USD)"] = df["單價 ($USD)"] * df["持有股數"]
df["當前市值 ($HKD)"] = df["當前市值 ($USD)"] * usd_hkd_rate

current_portfolio_usd = df["當前市值 ($USD)"].sum()
current_portfolio_hkd = current_portfolio_usd * usd_hkd_rate

new_capital_usd = new_capital_hkd / usd_hkd_rate if usd_hkd_rate > 0 else 0.0
total_rebalance_usd = current_portfolio_usd + new_capital_usd
total_rebalance_hkd = total_rebalance_usd * usd_hkd_rate

df["當前權重佔比"] = (df["當前市值 ($USD)"] / current_portfolio_usd * 100) if current_portfolio_usd > 0 else 0.0
current_portfolio_beta = (df["當前權重佔比"] / 100 * df["個股 Beta"]).sum()

is_default_portfolio = set(tickers) == {"QTOP", "QLD", "BOXX"}
beta_diff = 1.0 - current_portfolio_beta
steps = int(beta_diff // 0.1) if beta_diff > 0 else 0
auto_target_qld = min(30.0 + (steps * 10.0), 70.0)
auto_target_boxx = max(30.0 - (steps * 10.0), 0.0)
auto_target_qtop = 100.0 - auto_target_qld - auto_target_boxx

if is_default_portfolio:
    default_targets = {"QTOP": auto_target_qtop, "QLD": auto_target_qld, "BOXX": auto_target_boxx}
else:
    default_w = round(100.0 / len(tickers), 1)
    default_targets = {t: default_w for t in tickers}

df["目標權重佔比"] = df["股票代碼"].map(default_targets)
df["權重差值"] = df["當前權重佔比"] - df["目標權重佔比"]

initial_hkd = saved_config.get("initial_portfolio_hkd")
if initial_hkd is None or initial_hkd == 0.0:
    initial_hkd = current_portfolio_hkd
    saved_config["initial_portfolio_hkd"] = initial_hkd
    save_config(saved_config)

total_invested_hkd = initial_hkd + cumulative_new_capital_hkd
portfolio_pnl_hkd = current_portfolio_hkd - total_invested_hkd
portfolio_return_pct = (portfolio_pnl_hkd / total_invested_hkd * 100) if total_invested_hkd > 0 else 0.0

market_data_complete = len(prices) > 0
baseline_is_valid = initial_hkd is not None and initial_hkd > 0

if current_portfolio_beta < 0.9:
    st.warning(f"🚨 **再平衡警示**：當前組合 Beta 為 **{current_portfolio_beta:.3f}**（低於 0.9 臨界值），建議調整！")

# ---------------------------------------------------------
# 4. 建立 5 個分頁標籤導航 (Tabs)
# ---------------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 投組總覽與歷史走勢", 
    "🎯 再平衡與交易日誌",
    "🌪️ 壓力測試與情境模擬",
    "📈 複利試算與組合預估",
    "🏖️ 退休提領與現金流規劃"
])

# =========================================================
# 📌 頁籤一：投組總覽與歷史走勢
# =========================================================
with tab1:
    st.markdown('<div class="section-eyebrow">01 / Market Quotes & Overview</div>', unsafe_allow_html=True)
    st.subheader("核心標的與大盤即時行情")
    
    col_q1, col_q2, col_q3, col_q4 = st.columns(4)

    def render_quote_card(col, label, price, diff, change):
        with col:
            with st.container(border=True):
                if not is_valid_positive(price):
                    st.markdown(f"**{label}**")
                    st.markdown("暫無有效報價")
                    st.caption("行情不可用")
                    return
                
                if diff is None or change is None or not np.isfinite(as_number_or_nan(diff)) or not np.isfinite(as_number_or_nan(change)):
                    color = "#94a3b8"
                    diff_str = "日漲跌不可用"
                    change_str = "0.00%"
                elif diff > 0:
                    color = "#00C853"  # 綠漲
                    diff_str = f"+${diff:,.2f}"
                    change_str = f"+{change:.2f}%"
                elif diff < 0:
                    color = "#D50000"  # 紅跌
                    diff_str = f"-${abs(diff):,.2f}"
                    change_str = f"{change:.2f}%"
                else:
                    color = "#94a3b8"
                    diff_str = "$0.00"
                    change_str = "0.00%"

                st.markdown(f"<div style='font-size: 0.85rem; font-weight: 600; opacity: 0.8;'>{label}</div>", unsafe_allow_html=True)
                st.markdown(f"<div style='font-size: 1.35rem; font-weight: 700; margin: 4px 0;'>${price:,.2f} USD</div>", unsafe_allow_html=True)
                st.markdown(f"<div style='font-size: 0.85rem; font-weight: 600; color: {color};'>{diff_str} ({change_str})</div>", unsafe_allow_html=True)

    render_quote_card(col_q1, "QTOP · 原型", prices.get("QTOP"), price_diffs.get("QTOP"), price_changes.get("QTOP"))
    render_quote_card(col_q2, "QLD · 2 倍槓桿", prices.get("QLD"), price_diffs.get("QLD"), price_changes.get("QLD"))
    render_quote_card(col_q3, "QQQ · Nasdaq 100", prices.get("QQQ"), price_diffs.get("QQQ"), price_changes.get("QQQ"))
    render_quote_card(col_q4, "SPY · S&P 500", prices.get("SPY"), price_diffs.get("SPY"), price_changes.get("SPY"))

    st.markdown("---")
    st.subheader("📅 組合表現總覽")

    drifted_df_tab1 = df[df["權重差值"].abs() > drift_threshold]
    if not drifted_df_tab1.empty:
        drift_details_t1 = ", ".join([f"**{row['股票代碼']}** (實際 {row['當前權重佔比']:.1f}% / 目標 {row['目標權重佔比']:.1f}%)" for _, row in drifted_df_tab1.iterrows()])
        st.warning(f"⚠️ **[配置失衡提醒]** 以下資產偏離度超過 ±{drift_threshold}%：{drift_details_t1}。請前往「再平衡與交易日誌」頁籤進行調整！")

    overview_period = st.selectbox(
        "選擇表現總覽的時間週期：",
        ["近 1 日", "近 1 個月", "近 3 個月", "近 6 個月", "近 1 年", "YTD", "成立至今"],
        index=6,
        key="overview_sb"
    )

    today = datetime.now()
    if overview_period == "近 1 日":
        overview_start = (today - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    elif overview_period == "近 1 個月":
        overview_start = (today - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    elif overview_period == "近 3 個月":
        overview_start = (today - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    elif overview_period == "近 6 個月":
        overview_start = (today - pd.Timedelta(days=180)).strftime("%Y-%m-%d")
    elif overview_period == "近 1 年":
        overview_start = (today - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
    elif overview_period == "YTD":
        overview_start = datetime(today.year, 1, 1).strftime("%Y-%m-%d")
    else:
        overview_start = INIT_DATE_STR

    @st.cache_data(ttl=3600)
    def fetch_overview_data(active_tickers, start_date):
        try:
            all_tickers = list(set(active_tickers + ["QQQ", "SPY"]))
            df_hist = yf.download(all_tickers, start=start_date, progress=False)["Close"]
            if df_hist.empty: return None
            if isinstance(df_hist, pd.Series): df_hist = df_hist.to_frame()
            return df_hist.ffill().bfill()
        except Exception:
            return None

    df_ov = fetch_overview_data(tickers, overview_start)

    if overview_period == "成立至今":
        port_r = portfolio_return_pct
        port_diff_hkd = portfolio_pnl_hkd
        port_baseline_val = total_invested_hkd
        port_current_val = current_portfolio_hkd
        port_baseline_label = "🕒 總投入成本 (初始+新資金)"
        port_current_label = "💰 當前總市值 (HKD)"
    else:
        if df_ov is not None and len(df_ov) >= 2:
            start_row = df_ov.iloc[0]
            end_row = df_ov.iloc[-1]
            port_start_usd = sum(start_row.get(t, 0) * current_shares.get(t, 0) for t in tickers)
            port_end_usd = sum(end_row.get(t, 0) * current_shares.get(t, 0) for t in tickers)
            port_r = ((port_end_usd - port_start_usd) / port_start_usd * 100) if port_start_usd > 0 else 0.0
            port_diff_hkd = (port_end_usd - port_start_usd) * usd_hkd_rate
            port_baseline_val = port_start_usd * usd_hkd_rate
            port_current_val = current_portfolio_hkd
        else:
            port_r = 0.0
            port_diff_hkd = 0.0
            port_baseline_val = total_invested_hkd
            port_current_val = current_portfolio_hkd
        port_baseline_label = "🕒 期間起始市值 (HKD)"
        port_current_label = "💰 當前總市值 (HKD)"

    def get_benchmark_metrics(df_data):
        if df_data is None or len(df_data) < 2:
            return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        start_row = df_data.iloc[0]
        end_row = df_data.iloc[-1]
        
        qqq_start = start_row.get("QQQ", 1.0)
        qqq_end = end_row.get("QQQ", qqq_start)
        qqq_ret = ((qqq_end - qqq_start) / qqq_start * 100) if qqq_start > 0 else 0.0
        
        spy_start = start_row.get("SPY", 1.0)
        spy_end = end_row.get("SPY", spy_start)
        spy_ret = ((spy_end - spy_start) / spy_start * 100) if spy_start > 0 else 0.0
        return qqq_ret, qqq_start, qqq_end, spy_ret, spy_start, spy_end

    qqq_r, qq_s, qq_e, spy_r, sp_s, sp_e = get_benchmark_metrics(df_ov)

    def render_gradient_card(title, period_val, period_sub, baseline_label, baseline_val, current_label, current_val):
        is_pos = period_val > 0
        color = "#00C853" if is_pos else ("#D50000" if period_val < 0 else "#94a3b8")
        sign = "+" if period_val > 0 else ""

        return f"""
        <div class="metric-card">
            <div style="font-size: 0.9rem; font-weight: 700; margin-bottom: 8px; border-bottom: 1px solid rgba(148, 163, 184, 0.2); padding-bottom: 6px;">{title}</div>
            <div style="font-size: 0.8rem; opacity: 0.8; margin-top: 4px;">📌 {overview_period}表現</div>
            <div style="font-size: 1.3rem; font-weight: 700; color: {color};">{sign}{period_val:.2f}%</div>
            <div style="font-size: 0.78rem; opacity: 0.6;">{period_sub}</div>
            <div style="font-size: 0.8rem; opacity: 0.8; margin-top: 10px;">{baseline_label}</div>
            <div style="font-size: 0.95rem; font-weight: 600;">${baseline_val:,.2f}</div>
            <div style="font-size: 0.8rem; opacity: 0.8; margin-top: 6px;">{current_label}</div>
            <div style="font-size: 0.95rem; font-weight: 600; color: #38bdf8;">${current_val:,.2f}</div>
        </div>
        """

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(textwrap.dedent(f"""
        <div class="metric-card" style="border-left: 4px solid #38bdf8;">
            <div style="font-size: 0.9rem; font-weight: 700; margin-bottom: 8px;">本金結構</div>
            <div style="font-size: 0.8rem; opacity: 0.8; margin-top: 4px;">初始本金: ${initial_hkd:,.2f}</div>
            <div style="font-size: 0.8rem; opacity: 0.8;">累積新資金: ${cumulative_new_capital_hkd:,.2f}</div>
            <div style="font-size: 0.8rem; opacity: 0.8; margin-top: 8px;">總投入成本</div>
            <div style="font-size: 1.2rem; font-weight: 700;">${total_invested_hkd:,.2f} HKD</div>
        </div>
        """).strip(), unsafe_allow_html=True)

    with c2:
        pnl_sign = "+" if port_diff_hkd > 0 else ""
        st.markdown(render_gradient_card(
            "本組合盈虧",
            port_r,
            f"淨盈虧: {pnl_sign}${port_diff_hkd:,.2f} HKD",
            port_baseline_label,
            port_baseline_val,
            port_current_label,
            port_current_val
        ), unsafe_allow_html=True)

    with c3:
        st.markdown(render_gradient_card(
            "QQQ 大盤表現",
            qqq_r,
            f"現價: ${prices.get('QQQ', 0):.2f}",
            "🕒 期間起始價",
            qq_s,
            "📈 期間結束價",
            qq_e
        ), unsafe_allow_html=True)

    with c4:
        st.markdown(render_gradient_card(
            "SPY 大盤表現",
            spy_r,
            f"現價: ${prices.get('SPY', 0):.2f}",
            "🕒 期間起始價",
            sp_s,
            "📈 期間結束價",
            sp_e
        ), unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("📊 組合核心指標與歷史走勢")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("組合當前總市值", f"${current_portfolio_hkd:,.2f} HKD")
    m2.metric("總投入成本", f"${total_invested_hkd:,.2f} HKD")
    m3.metric("再平衡總資金池", f"${total_rebalance_hkd:,.2f} HKD")
    m4.metric("當前組合 Beta", f"{current_portfolio_beta:.3f}")
    m5.metric("已執行再平衡", f"第 {rebalance_count} 次")

    @st.cache_data(ttl=3600)
    def fetch_historical_trends(active_tickers, start_date):
        try:
            all_tickers = list(set(active_tickers + ["QQQ", "SPY"]))
            df_hist = yf.download(all_tickers, start=start_date, progress=False)["Close"]
            if df_hist.empty: return None
            if isinstance(df_hist, pd.Series): df_hist = df_hist.to_frame()
            return df_hist.ffill().bfill()
        except Exception:
            return None

    timeframe = st.radio(
        "選擇圖表時間範圍：", 
        ["近 1 日", "近 1 個月", "近 3 個月", "近 6 個月", "近 1 年", "YTD", "成立至今"], 
        index=2, 
        horizontal=True,
        key="chart_tf"
    )

    if timeframe == "近 1 日": 
        chart_start = (today - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    elif timeframe == "近 1 個月": 
        chart_start = (today - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    elif timeframe == "近 3 個月": 
        chart_start = (today - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    elif timeframe == "近 6 個月": 
        chart_start = (today - pd.Timedelta(days=180)).strftime("%Y-%m-%d")
    elif timeframe == "近 1 年": 
        chart_start = (today - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
    elif timeframe == "YTD": 
        chart_start = datetime(today.year, 1, 1).strftime("%Y-%m-%d")
    else: 
        chart_start = INIT_DATE_STR

    df_history = fetch_historical_trends(tickers, chart_start)
    
    if df_history is not None and not df_history.empty and len(df_history) >= 2:
        if timeframe == "近 1 日": df_history = df_history.tail(2)
        chart_df = pd.DataFrame(index=df_history.index)

        portfolio_daily_val = pd.Series(0.0, index=df_history.index)
        for t in tickers:
            if t in df_history.columns:
                portfolio_daily_val += df_history[t] * current_shares[t]

        port_returns = portfolio_daily_val.pct_change().dropna()
        if not port_returns.empty:
            ann_volatility = port_returns.std() * np.sqrt(252) * 100
            rolling_max = portfolio_daily_val.cummax()
            drawdown = (portfolio_daily_val - rolling_max) / rolling_max
            max_drawdown = drawdown.min() * 100
        else:
            ann_volatility = 0.0
            max_drawdown = 0.0

        rc1, rc2 = st.columns(2)
        rc1.metric("📉 組合年化波動率 (Volatility)", f"{ann_volatility:.2f}%")
        rc2.metric("⚠️ 最大回撤 (MDD)", f"{max_drawdown:.2f}%")

        base_val = portfolio_daily_val.iloc[0]
        if base_val > 0: chart_df["本投資組合 (%)"] = ((portfolio_daily_val - base_val) / base_val) * 100
        if "QQQ" in df_history.columns and df_history["QQQ"].iloc[0] > 0:
            chart_df["QQQ (%)"] = ((df_history["QQQ"] - df_history["QQQ"].iloc[0]) / df_history["QQQ"].iloc[0]) * 100
        if "SPY" in df_history.columns and df_history["SPY"].iloc[0] > 0:
            chart_df["SPY (%)"] = ((df_history["SPY"] - df_history["SPY"].iloc[0]) / df_history["SPY"].iloc[0]) * 100

        fig = px.line(chart_df, x=chart_df.index, y=chart_df.columns, labels={"value": "報酬率 (%)", "Date": "日期", "variable": "標的"}, template=plotly_template)
        fig.update_layout(hovermode="x unified", legend_title_text="", margin=dict(t=20, b=20, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("💡 該時間範圍內暫無足夠歷史數據。")


# =========================================================
# 📌 頁籤二：再平衡與交易日誌
# =========================================================
with tab2:
    st.subheader("🎯 再平衡目標權重調整與執行")

    if is_default_portfolio:
        preset_options = {
            "自動階梯建議 (依當前 Beta 自動計算)": "AUTO",
            "40% QTOP / 30% QLD / 30% BOXX (Beta 1.0)": (40.0, 30.0, 30.0),
            "50% QTOP / 30% QLD / 20% BOXX (Beta 1.1)": (50.0, 30.0, 20.0),
            "40% QTOP / 40% QLD / 20% BOXX (Beta 1.2)": (40.0, 40.0, 20.0),
            "50% QTOP / 40% QLD / 10% BOXX (Beta 1.3)": (50.0, 40.0, 10.0),
            "40% QTOP / 50% QLD / 10% BOXX (Beta 1.4)": (40.0, 50.0, 10.0),
            "50% QTOP / 50% QLD / 0% BOXX  (Beta 1.5)": (50.0, 50.0, 0.0),
            "自訂手動填寫 (Custom)": "CUSTOM"
        }
        selected_preset_label = st.selectbox("選擇目標配置模組：", options=list(preset_options.keys()))
        selected_preset = preset_options[selected_preset_label]
        
        col_t1, col_t2, col_t3 = st.columns(3)
        if selected_preset == "AUTO":
            target_qtop = col_t1.number_input("QTOP 目標 (%)", value=float(auto_target_qtop), disabled=True)
            target_qld = col_t2.number_input("QLD 目標 (%)", value=float(auto_target_qld), disabled=True)
            target_boxx = col_t3.number_input("BOXX 目標 (%)", value=float(auto_target_boxx), disabled=True)
        elif selected_preset == "CUSTOM":
            target_qtop = col_t1.number_input("QTOP 目標 (%)", value=40.0, step=1.0)
            target_qld = col_t2.number_input("QLD 目標 (%)", value=30.0, step=1.0)
            target_boxx = col_t3.number_input("BOXX 目標 (%)", value=30.0, step=1.0)
        else:
            qtop_p, qld_p, boxx_p = selected_preset
            target_qtop = col_t1.number_input("QTOP 目標 (%)", value=float(qtop_p), disabled=True)
            target_qld = col_t2.number_input("QLD 目標 (%)", value=float(qld_p), disabled=True)
            target_boxx = col_t3.number_input("BOXX 目標 (%)", value=float(boxx_p), disabled=True)

        targets = {"QTOP": target_qtop, "QLD": target_qld, "BOXX": target_boxx}
    else:
        st.info("💡 偵測到自訂持倉組合，請填寫各資產目標權重：")
        targets = {}
        cols = st.columns(min(len(tickers), 4))
        default_w = round(100.0 / len(tickers), 1)
        for idx, t in enumerate(tickers):
            c = cols[idx % len(cols)]
            targets[t] = c.number_input(f"{t} 目標 (%)", value=default_w, step=1.0, key=f"target_{t}")

    total_target_pct = sum(targets.values())

    if abs(total_target_pct - 100.0) > 0.01:
        st.error(f"⚠️ 目標權重總和必須為 100%！（目前總和：{total_target_pct:.1f}%）")
    else:
        df["目標權重佔比"] = df["股票代碼"].map(targets)
        df["權重差值"] = df["當前權重佔比"] - df["目標權重佔比"]
        
        drifted_df = df[df["權重差值"].abs() > drift_threshold]
        if not drifted_df.empty:
            drift_details = ", ".join([f"**{row['股票代碼']}** (實際 {row['當前權重佔比']:.1f}% / 目標 {row['目標權重佔比']:.1f}%)" for _, row in drifted_df.iterrows()])
            st.warning(f"⚠️ **資產配置偏離警示**：以下標的權重偏離度超過 ±{drift_threshold}%：{drift_details}，建議優先執行再平衡調整！")

        df["目標市值 ($USD)"] = total_rebalance_usd * (df["目標權重佔比"] / 100)
        df["目標市值 ($HKD)"] = df["目標市值 ($USD)"] * usd_hkd_rate
        df["需調整金額 ($USD)"] = df["目標市值 ($USD)"] - df["當前市值 ($USD)"]
        df["需調整金額 ($HKD)"] = df["需調整金額 ($USD)"] * usd_hkd_rate
        df["建議交易股數"] = (df["需調整金額 ($USD)"] / df["單價 ($USD)"]).round(0).astype(int)
        
        # 修正交易動作中的多餘 $ 符號
        df["交易動作"] = df["建議交易股數"].apply(lambda s: f"🟢 買入 {s:,} 股" if s > 0 else (f"🔴 賣出 {abs(s):,} 股" if s < 0 else "⚪ 維持不變"))

        col_pie1, col_pie2 = st.columns(2)
        with col_pie1:
            fig_curr = px.pie(df, names="股票代碼", values="當前權重佔比", title="🍩 當前資產實際佔比", hole=0.4, template=plotly_template)
            fig_curr.update_layout(margin=dict(t=30, b=10, l=10, r=10), height=300)
            st.plotly_chart(fig_curr, use_container_width=True)
        with col_pie2:
            fig_target = px.pie(df, names="股票代碼", values="目標權重佔比", title="🎯 目標資產配置佔比", hole=0.4, template=plotly_template)
            fig_target.update_layout(margin=dict(t=30, b=10, l=10, r=10), height=300)
            st.plotly_chart(fig_target, use_container_width=True)

        display_cols = ["股票代碼", "單價 ($USD)", "持有股數", "當前權重佔比", "目標權重佔比", "權重差值", "當前市值 ($HKD)", "目標市值 ($HKD)", "需調整金額 ($HKD)", "交易動作"]
        
        def highlight_drift(row):
            if abs(row["權重差值"]) > drift_threshold:
                return ['background-color: rgba(213, 0, 0, 0.12)'] * len(row)
            return [''] * len(row)

        st.dataframe(df[display_cols].style.apply(highlight_drift, axis=1).format({
            "單價 ($USD)": "${:.2f}",
            "當前權重佔比": "{:.1f}%",
            "目標權重佔比": "{:.1f}%",
            "權重差值": "{:+.1f}%",
            "當前市值 ($HKD)": "${:,.2f} HKD",
            "目標市值 ($HKD)": "${:,.2f} HKD",
            "需調整金額 ($HKD)": "${:,.2f} HKD"
        }), use_container_width=True)

        target_beta = (df["目標權重佔比"] / 100 * df["個股 Beta"]).sum()
        st.info(f"💡 再平衡調整後的預期組合 Beta 將為：**{target_beta:.3f}**")

        st.markdown("---")
        if st.button("✅ 確認執行再平衡並更新持倉", use_container_width=True):
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_rows = []
            for _, row in df.iterrows():
                shares_diff = row["建議交易股數"]
                if shares_diff != 0:
                    action = "買入" if shares_diff > 0 else "賣出"
                    log_rows.append({
                        "日期": now_str,
                        "股票代碼": row["股票代碼"],
                        "動作": action,
                        "成交股數": abs(shares_diff),
                        "成交價(USD)": row["單價 ($USD)"],
                        "手續費(USD)": 0.0
                    })
            
            if log_rows:
                log_df = pd.DataFrame(log_rows)
                if not os.path.exists(TRANSACTION_FILE):
                    log_df.to_csv(TRANSACTION_FILE, index=False, encoding="utf-8-sig")
                else:
                    log_df.to_csv(TRANSACTION_FILE, mode='a', header=False, index=False, encoding="utf-8-sig")

            new_shares_dict = {}
            for _, row in df.iterrows():
                new_shares_dict[row["股票代碼"]] = int(row["持有股數"] + row["建議交易股數"])
            
            added_new_cap = saved_config.get("new_capital_hkd", 0.0)
            if added_new_cap > 0:
                saved_config["cumulative_new_capital_hkd"] = saved_config.get("cumulative_new_capital_hkd", 0.0) + added_new_cap

            saved_config["shares"] = new_shares_dict
            saved_config["new_capital_hkd"] = 0.0
            saved_config["rebalance_count"] = saved_config.get("rebalance_count", 0) + 1
            save_config(saved_config)
            
            # 清除 sidebar widget state 確保持倉股數順利更新
            for t in new_shares_dict.keys():
                if f"shares_{t}" in st.session_state:
                    del st.session_state[f"shares_{t}"]

            st.success("🎉 再平衡成功套用！新資金已自動累計至總投入成本中，持倉股數已更新，新資金已歸零。")
            st.rerun()

    st.markdown("---")
    st.subheader("📜 歷史交易日誌 (Transaction Log - 可編輯)")
    if os.path.exists(TRANSACTION_FILE):
        try:
            trans_df = pd.read_csv(TRANSACTION_FILE, encoding="utf-8-sig")
            
            # 使用 st.data_editor 讓歷史紀錄可直接修改、新增或刪除
            edited_trans_df = st.data_editor(
                trans_df, 
                num_rows="dynamic", 
                use_container_width=True,
                key="transaction_history_editor"
            )
            
            if st.button("💾 儲存歷史交易修改", use_container_width=True):
                edited_trans_df.to_csv(TRANSACTION_FILE, index=False, encoding="utf-8-sig")
                st.success("✅ 歷史交易紀錄已成功更新並儲存！")
                st.rerun()
        except Exception as e:
            st.info(f"💡 暫時無法讀取或編輯交易日誌檔案：{e}")
    else:
        st.info("💡 目前尚無任何再平衡交易紀錄。點擊上方「確認執行再平衡」後會自動產生紀錄。")


# =========================================================
# 📌 頁籤三：壓力測試與情境模擬
# =========================================================
with tab3:
    st.subheader("🌪️ 壓力測試與極端行情情境模擬 (Stress Testing)")
    st.caption("模擬當納斯達克大盤 (QQQ) 發生不同幅度下跌時，本組合各資產與總市值受 Beta 聯動影響的預估表現。")

    col_st1, col_st2 = st.columns([1, 2])
    with col_st1:
        sim_drop_pct = st.selectbox(
            "選擇 QQQ 模擬跌幅情境：",
            [-5.0, -10.0, -20.0, -30.0, -50.0],
            index=2,
            format_func=lambda x: f"QQQ 下跌 {abs(x)}%"
        )
        custom_drop = st.slider("或自訂 QQQ 下跌百分比 (%)", min_value=0.0, max_value=70.0, value=abs(sim_drop_pct), step=1.0)
        effective_drop = -custom_drop

    with col_st2:
        st.markdown(f"**🔬 模擬情境：QQQ 下跌 {abs(effective_drop):.1f}%**")
        sim_df = df.copy()
        sim_df["資產預估跌幅 (%)"] = sim_df["個股 Beta"] * effective_drop
        sim_df["模擬跌後單價 ($USD)"] = sim_df["單價 ($USD)"] * (1 + sim_df["資產預估跌幅 (%)"] / 100)
        sim_df["模擬跌後市值 ($USD)"] = sim_df["模擬跌後單價 ($USD)"] * sim_df["持有股數"]
        sim_df["模擬跌後市值 ($HKD)"] = sim_df["模擬跌後市值 ($USD)"] * usd_hkd_rate
        sim_df["預估盈虧金額 ($HKD)"] = sim_df["模擬跌後市值 ($HKD)"] - sim_df["當前市值 ($HKD)"]

        sim_total_usd = sim_df["模擬跌後市值 ($USD)"].sum()
        sim_total_hkd = sim_total_usd * usd_hkd_rate
        sim_total_pnl_hkd = sim_total_hkd - current_portfolio_hkd
        sim_total_return_pct = (sim_total_pnl_hkd / current_portfolio_hkd * 100) if current_portfolio_hkd > 0 else 0.0

        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("模擬後組合總市值", f"${sim_total_hkd:,.2f} HKD")
        sc2.metric("預估最大虧損金額", f"${sim_total_pnl_hkd:,.2f} HKD", delta_color="inverse")
        sc3.metric("預估組合總報酬率", f"{sim_total_return_pct:.2f}%")

        sim_display_cols = ["股票代碼", "個股 Beta", "資產預估跌幅 (%)", "當前市值 ($HKD)", "模擬跌後市值 ($HKD)", "預估盈虧金額 ($HKD)"]
        st.dataframe(sim_df[sim_display_cols].style.format({
            "個股 Beta": "{:.1f}",
            "資產預估跌幅 (%)": "{:+.1f}%",
            "當前市值 ($HKD)": "${:,.2f} HKD",
            "模擬跌後市值 ($HKD)": "${:,.2f} HKD",
            "預估盈虧金額 ($HKD)": "${:+,.2f} HKD"
        }), use_container_width=True)


# =========================================================
# 📌 頁籤四：複利試算與組合預估
# =========================================================
with tab4:
    st.subheader("📈 組合複利試算與資產成長預估")
    st.caption("透過分頁管理各組合參數，並在總和頁籤檢視家庭總資產規模與成長軌跡。")

    def calc_compound_growth_fixed(principal, monthly_contrib, annual_rate, years):
        months = years * 12
        monthly_rate = annual_rate / 100.0 / 12.0
        data = []
        current_val = principal
        total_invested = principal
        
        for m in range(months + 1):
            if m > 0:
                current_val = (current_val + monthly_contrib) * (1 + monthly_rate)
                total_invested += monthly_contrib
            
            if m % 12 == 0:
                year = m // 12
                profit = 0.0 if year == 0 else current_val - total_invested
                data.append({
                    "年份": year,
                    "總投入本金": round(total_invested, 2),
                    "資產總市值": round(current_val, 2),
                    "累積獲利": round(profit, 2)
                })
        return pd.DataFrame(data)

    def calc_compound_growth_variable(principal, yearly_monthly_contribs, annual_rate, years):
        months = years * 12
        monthly_rate = annual_rate / 100.0 / 12.0
        data = []
        current_val = principal
        total_invested = principal
        
        for m in range(months + 1):
            if m > 0:
                year_idx = (m - 1) // 12
                current_year = year_idx + 1
                monthly_contrib = yearly_monthly_contribs.get(current_year, 0.0)
                current_val = (current_val + monthly_contrib) * (1 + monthly_rate)
                total_invested += monthly_contrib
            
            if m % 12 == 0:
                year = m // 12
                profit = 0.0 if year == 0 else current_val - total_invested
                data.append({
                    "年份": year,
                    "總投入本金": round(total_invested, 2),
                    "資產總市值": round(current_val, 2),
                    "累積獲利": round(profit, 2)
                })
        return pd.DataFrame(data)

    sub_tab1, sub_tab2, sub_tab3 = st.tabs([
        "🟢 組合一設定與明細", 
        "🔵 組合二設定與明細", 
        "💰 雙組合總和與對比"
    ])

    with sub_tab1:
        p1_default_name = saved_compound.get("p1_name", "組合一 (固定定投)")
        p1_name = st.text_input("🟢 組合一自訂名稱 / 角色", value=p1_default_name, key="input_p1_name")
        
        col_p1_set, col_p1_summary = st.columns([2, 1], gap="medium")
        with col_p1_set:
            with st.container(border=True):
                p1_init = st.number_input(f"{p1_name}：初始本金 (HKD)", value=float(saved_compound.get("p1_init", 100000.0)), step=10000.0, key="p1_init")
                p1_monthly = st.number_input(f"{p1_name}：每月定投 (HKD)", value=float(saved_compound.get("p1_monthly", 5000.0)), step=1000.0, key="p1_monthly")
                p1_rate = st.slider(f"{p1_name}：預估年化報酬率 (%)", min_value=0.0, max_value=30.0, value=float(saved_compound.get("p1_rate", 10.0)), step=0.5, key="p1_rate")
                p1_years = st.slider(f"{p1_name}：投資年限 (年)", min_value=1, max_value=30, value=int(saved_compound.get("p1_years", 10)), step=1, key="p1_years")

        df_p1 = calc_compound_growth_fixed(p1_init, p1_monthly, p1_rate, p1_years)
        final_p1 = df_p1.iloc[-1]

        with col_p1_summary:
            st.markdown(f"**📌 {p1_name} 預估摘要**")
            st.metric("預估總市值", f"${final_p1['資產總市值']:,.2f}")
            st.metric("總投入本金", f"${final_p1['總投入本金']:,.2f}")
            st.metric("累積獲利", f"${final_p1['累積獲利']:,.2f}")

        st.markdown(f"##### 📋 {p1_name} 年度成長明細")
        st.dataframe(df_p1, use_container_width=True, hide_index=True)

    with sub_tab2:
        p2_default_name = saved_compound.get("p2_name", "組合二 (每年定投不同)")
        p2_name = st.text_input("🔵 組合二自訂名稱 / 角色", value=p2_default_name, key="input_p2_name")

        col_p2_set, col_p2_summary = st.columns([2, 1], gap="medium")
        with col_p2_set:
            with st.container(border=True):
                p2_init = st.number_input(f"{p2_name}：初始本金 (HKD)", value=float(saved_compound.get("p2_init", 100000.0)), step=10000.0, key="p2_init")
                p2_rate = st.slider(f"{p2_name}：預估年化報酬率 (%)", min_value=0.0, max_value=30.0, value=float(saved_compound.get("p2_rate", 15.0)), step=0.5, key="p2_rate")

                st.markdown(f"📅 **設定 {p2_name} 每年每月定投金額 (HKD)**")
                saved_schedule_list = saved_compound.get("p2_schedule", [3000.0] * 10)

                schedule_key = "p2_schedule_dynamic_df"
                if schedule_key not in st.session_state:
                    st.session_state[schedule_key] = pd.DataFrame({
                        "年份": [f"第 {i} 年" for i in range(1, len(saved_schedule_list) + 1)],
                        "每月定投金額 (HKD)": saved_schedule_list
                    })

                edited_schedule = st.data_editor(
                    st.session_state[schedule_key],
                    num_rows="dynamic",
                    use_container_width=True,
                    key="editor_p2_dynamic"
                )
                st.session_state[schedule_key] = edited_schedule

        p2_years = len(edited_schedule)

        yearly_contribs = {}
        for idx, (_, row) in enumerate(edited_schedule.iterrows(), start=1):
            yearly_contribs[idx] = float(row["每月定投金額 (HKD)"])

        df_p2 = calc_compound_growth_variable(p2_init, yearly_contribs, p2_rate, p2_years)
        final_p2 = df_p2.iloc[-1]

        with col_p2_summary:
            st.markdown(f"**📌 {p2_name} 預估摘要 (共 {p2_years} 年)**")
            st.metric("預估總市值", f"${final_p2['資產總市值']:,.2f}")
            st.metric("總投入本金", f"${final_p2['總投入本金']:,.2f}")
            st.metric("累積獲利", f"${final_p2['累積獲利']:,.2f}")

        st.markdown(f"##### 📋 {p2_name} 年度成長明細")
        st.dataframe(df_p2, use_container_width=True, hide_index=True)

    with sub_tab3:
        st.subheader(f"💰 組合總和與資產成長總覽 ({p1_name} + {p2_name})")
        st.caption("以下數據自動加總兩個組合在各個投資年度的表現，幫助你全面掌握家庭總資產規模。")

        max_eval_years = min(p1_years, p2_years)
        df_combined = pd.DataFrame()
        df_combined["年份"] = range(max_eval_years + 1)
        
        merged_df = pd.merge(df_p1, df_p2, on="年份", suffixes=("_p1", "_p2"))
        merged_df["總投入本金"] = merged_df["總投入本金_p1"] + merged_df["總投入本金_p2"]
        merged_df["資產總市值"] = merged_df["資產總市值_p1"] + merged_df["資產總市值_p2"]
        merged_df["累積獲利"] = merged_df["累積獲利_p1"] + merged_df["累積獲利_p2"]
        
        df_total_summary = merged_df[["年份", "總投入本金", "資產總市值", "累積獲利"]]
        global final_total_val
        final_total = df_total_summary.iloc[-1]
        final_total_val = final_total['資產總市值']

        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("💎 雙組合最終總市值", f"${final_total['資產總市值']:,.2f} HKD")
        mc2.metric("💵 雙組合總投入本金", f"${final_total['總投入本金']:,.2f} HKD")
        mc3.metric("🚀 雙組合累積總獲利", f"${final_total['累積獲利']:,.2f} HKD")

        st.markdown("##### 📈 成長軌跡對比與總和趨勢")
        fig_compare = go.Figure()
        fig_compare.add_trace(go.Scatter(x=df_p1["年份"], y=df_p1["資產總市值"], mode='lines+markers', name=p1_name, line=dict(color='#00C853', width=2)))
        fig_compare.add_trace(go.Scatter(x=df_p2["年份"], y=df_p2["資產總市值"], mode='lines+markers', name=p2_name, line=dict(color='#2563eb', width=2)))
        fig_compare.add_trace(go.Scatter(x=df_total_summary["年份"], y=df_total_summary["資產總市值"], mode='lines+markers', name='雙組合總和市值', line=dict(color='#f59e0b', width=4, dash='dash')))
        
        fig_compare.update_layout(
            title="未來資產總市值成長趨勢與總和比較 (HKD)",
            xaxis_title="投資年數 (年)",
            yaxis_title="資產總市值 (HKD)",
            hovermode="x unified",
            template=plotly_template,
            margin=dict(t=40, b=20, l=20, r=20),
            height=450
        )
        st.plotly_chart(fig_compare, use_container_width=True)

        st.markdown("##### 📋 雙組合加總年度明細表")
        st.dataframe(df_total_summary, use_container_width=True, hide_index=True)

    st.markdown("---")
    col_save_btn1, col_save_btn2, col_save_btn3 = st.columns([1, 2, 1])
    with col_save_btn2:
        if st.button("💾 儲存目前雙組合複利設定與名稱", use_container_width=True):
            new_compound_data = {
                "p1_name": str(p1_name),
                "p1_init": float(p1_init),
                "p1_monthly": float(p1_monthly),
                "p1_rate": float(p1_rate),
                "p1_years": int(p1_years),
                "p2_name": str(p2_name),
                "p2_init": float(p2_init),
                "p2_rate": float(p2_rate),
                "p2_years": int(p2_years),
                "p2_schedule": [float(row["每月定投金額 (HKD)"]) for _, row in edited_schedule.iterrows()]
            }
            save_compound_config(new_compound_data)
            st.success("🎉 複利試算設定與動態排程已成功儲存至本地檔案 (`compound_config.json`)！")


# =========================================================
# 📌 頁籤五：退休提領與現金流規劃 (Retirement Withdrawal)
# =========================================================
with tab5:
    st.subheader("🏖️ 退休提領與現金流模擬規劃")
    st.caption("模擬當您退休時，資產在固定提領、通膨調整與保守報酬下的續航力與剩餘價值變化。")

    default_ret_corpus = float(final_total_val) if 'final_total_val' in globals() else 2000000.0

    col_ret1, col_ret2 = st.columns([1, 2], gap="large")

    with col_ret1:
        with st.container(border=True):
            st.markdown("##### ⚙️ 退休提領參數設定")
            ret_initial_corpus = st.number_input("退休起始總資產 (HKD)", value=default_ret_corpus, step=100000.0)
            
            withdrawal_mode = st.radio("提領計算模式", ["自訂每年提領金額", "依 4% 法則自動計算 (SWR)"])
            
            if withdrawal_mode == "依 4% 法則自動計算 (SWR)":
                ret_annual_withdrawal = ret_initial_corpus * 0.04
                st.info(f"💡 4% 法則建議每年提領：**${ret_annual_withdrawal:,.2f} HKD**")
            else:
                ret_annual_withdrawal = st.number_input("每年預計提領金額 (HKD)", value=80000.0, step=10000.0)

            ret_annual_rate = st.slider("退休後資產預估年化報酬率 (%)", min_value=0.0, max_value=15.0, value=6.0, step=0.5)
            ret_inflation_rate = st.slider("預估每年通貨膨脹率 (%)", min_value=0.0, max_value=10.0, value=2.5, step=0.5)
            ret_years = st.slider("退休規劃年限 (年)", min_value=5, max_value=50, value=30, step=1)

    def calc_retirement_withdrawal(initial_corpus, annual_withdrawal, annual_rate, inflation_rate, years):
        data = []
        corpus = initial_corpus
        current_withdrawal = annual_withdrawal
        
        for y in range(years + 1):
            if y == 0:
                data.append({
                    "退休年份": f"第 {y} 年 (退休當下)",
                    "期初資產": round(corpus, 2),
                    "當年提領": 0.0,
                    "投資收益": 0.0,
                    "期末資產": round(corpus, 2)
                })
            else:
                withdrawal = current_withdrawal
                if corpus <= 0:
                    data.append({
                        "退休年份": f"第 {y} 年",
                        "期初資產": 0.0,
                        "當年提領": 0.0,
                        "投資收益": 0.0,
                        "期末資產": 0.0
                    })
                    continue

                remaining_after_withdrawal = max(0, corpus - withdrawal)
                return_gain = remaining_after_withdrawal * (annual_rate / 100.0)
                end_corpus = max(0, remaining_after_withdrawal + return_gain)
                
                data.append({
                    "退休年份": f"第 {y} 年",
                    "期初資產": round(corpus, 2),
                    "當年提領": round(withdrawal, 2),
                    "投資收益": round(return_gain, 2),
                    "期末資產": round(end_corpus, 2)
                })
                
                corpus = end_corpus
                current_withdrawal *= (1 + inflation_rate / 100.0)
        return pd.DataFrame(data)

    df_ret = calc_retirement_withdrawal(ret_initial_corpus, ret_annual_withdrawal, ret_annual_rate, ret_inflation_rate, ret_years)
    final_ret_row = df_ret.iloc[-1]
    
    exhausted_year = None
    for idx, row in df_ret.iterrows():
        if row["期末資產"] <= 0 and idx > 0:
            exhausted_year = row["退休年份"]
            break

    with col_ret2:
        st.markdown("##### 📊 退休資產續航力摘要")
        rk1, rk2, rk3 = st.columns(3)
        rk1.metric("起始總資產", f"${ret_initial_corpus:,.2f} HKD")
        rk2.metric("首年提領金額", f"${ret_annual_withdrawal:,.2f} HKD")
        
        if exhausted_year:
            rk3.metric("⚠️ 資金耗盡預警", f"約在 {exhausted_year} 耗盡", delta="注意風險", delta_color="inverse")
            st.error(f"🚨 **退休安全警示**：在當前設定下，您的退休資產大約會在 **{exhausted_year}** 用盡，建議降低提領金額或提高投資報酬率！")
        else:
            rk3.metric("💎 規劃期末剩餘資產", f"${final_ret_row['期末資產']:,.2f} HKD", delta="資產充裕")
            st.success("🎉 **恭喜！** 在當前設定下，您的退休資產能夠穩健度過整個退休規劃年限，且期末仍有結餘！")

        fig_ret = go.Figure()
        fig_ret.add_trace(go.Scatter(x=df_ret["退休年份"], y=df_ret["期末資產"], mode='lines+markers', name='期末資產餘額', line=dict(color='#38bdf8', width=3)))
        fig_ret.add_trace(go.Bar(x=df_ret["退休年份"], y=df_ret["當年提領"], name='當年提領金額', marker_color='#f59e0b', opacity=0.7))
        
        fig_ret.update_layout(
            title="退休期間資產餘額與年度提領金額走勢 (HKD)",
            xaxis_title="退休年限",
            yaxis_title="金額 (HKD)",
            hovermode="x unified",
            barmode='group',
            template=plotly_template,
            margin=dict(t=40, b=20, l=20, r=20),
            height=400
        )
        st.plotly_chart(fig_ret, use_container_width=True)

    st.markdown("##### 📋 退休現金流年度明細表")
    st.dataframe(df_ret, use_container_width=True, hide_index=True)