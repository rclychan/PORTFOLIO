import json
import os
import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.express as px
from datetime import datetime

# 設定儲存持倉紀錄的本地檔案檔名與基準日
CONFIG_FILE = "holdings.json"
INIT_DATE_STR = "2026-10-08"

# ---------------------------------------------------------
# 本地 JSON 檔案讀寫函數
# ---------------------------------------------------------
def load_config():
    """讀取本地持倉設定檔，若不存在則回傳預設值"""
    default_config = {
        "betas": {"QTOP": 1.0, "QLD": 2.0, "BOXX": 0.0},
        "shares": {"QTOP": 400, "QLD": 150, "BOXX": 300},
        "new_capital_hkd": 0.0,
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
    """將目前的持倉、Beta 設定、新資金與表現基準寫入本地 JSON 檔案"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=4)

# 讀取已儲存的設定（若無則載入預設值）
saved_config = load_config()

# ---------------------------------------------------------
# 頁面標題與設定
# ---------------------------------------------------------
st.set_page_config(page_title="Beta 組合監控與大盤比對工具 (HKD 版)", layout="wide")
st.title("📈 股票組合 Beta 監控與大盤表現追蹤工具")
st.caption("動態監控組合 Beta、計算再平衡交易股數，並支援自訂資產擴充與 QQQ / SPY 歷史走勢對比")

# ---------------------------------------------------------
# 1. 側邊欄設定：動態新增/刪除資產、Beta 與持股數量設定
# ---------------------------------------------------------
st.sidebar.header("⚙️ 1. 資產配置與動態管理")

# --- 1.1 動態新增資產 ---
with st.sidebar.expander("➕ 新增資產標的", expanded=False):
    new_ticker = st.text_input("股票代碼 (例如: NVDA, TLT, TSLA)").strip().upper()
    new_beta = st.number_input("該資產預設 Beta", value=1.0, step=0.1)
    new_shares = st.number_input("初始持有股數", value=0, min_value=0, step=10)
    
    if st.button("確認新增標的", use_container_width=True):
        if new_ticker:
            if new_ticker in saved_config["shares"]:
                st.warning(f"⚠️ {new_ticker} 已存在於持倉清單中！")
            else:
                saved_config["shares"][new_ticker] = int(new_shares)
                saved_config["betas"][new_ticker] = float(new_beta)
                save_config(saved_config)
                st.success(f"✅ 已成功加入資產 {new_ticker}")
                st.rerun()
        else:
            st.error("請輸入有效的股票代碼！")

# --- 1.2 動態刪除資產 ---
with st.sidebar.expander("🗑️ 刪除現有資產", expanded=False):
    current_asset_list = list(saved_config["shares"].keys())
    if len(current_asset_list) > 0:
        remove_ticker = st.selectbox("選擇要移除的資產", options=current_asset_list)
        if st.button("確認刪除資產", use_container_width=True):
            if len(current_asset_list) <= 1:
                st.error("⚠️ 組合中至少需保留一項資產！")
            else:
                del saved_config["shares"][remove_ticker]
                if remove_ticker in saved_config["betas"]:
                    del saved_config["betas"][remove_ticker]
                save_config(saved_config)
                st.success(f"🗑️ 已移除資產 {remove_ticker}")
                st.rerun()

st.sidebar.subheader("📦 各資產 Beta 與持有股數")

asset_betas = {}
current_shares = {}
tickers = list(saved_config["shares"].keys())

for ticker in tickers:
    st.sidebar.markdown(f"**🔹 {ticker}**")
    col_b, col_s = st.sidebar.columns(2)
    with col_b:
        asset_betas[ticker] = col_b.number_input(
            "Beta",
            value=float(saved_config["betas"].get(ticker, 1.0)),
            step=0.1,
            key=f"beta_{ticker}"
        )
    with col_s:
        current_shares[ticker] = col_s.number_input(
            "持有股數",
            value=int(saved_config["shares"].get(ticker, 0)),
            min_value=0,
            step=10,
            key=f"shares_{ticker}"
        )

st.sidebar.subheader("💵 2. 注入新資金 (HKD)")
new_capital_hkd = st.sidebar.number_input(
    "準備投入的新資金 (HKD)", 
    value=float(saved_config.get("new_capital_hkd", 0.0)), 
    min_value=0.0, 
    step=1000.0,
    help="輸入港幣金額，系統會自動依即時匯率換算成美金計入再平衡資金池。"
)

st.sidebar.subheader("🔢 3. 再平衡紀錄")
rebalance_count = st.sidebar.number_input(
    "觸及再平衡總次數", 
    value=int(saved_config.get("rebalance_count", 0)), 
    min_value=0, 
    step=1
)

# 自動同步側邊欄設定至 saved_config 並寫入本地 JSON
saved_config["betas"] = asset_betas
saved_config["shares"] = current_shares
saved_config["new_capital_hkd"] = new_capital_hkd
saved_config["rebalance_count"] = rebalance_count
save_config(saved_config)

col_inc1, _ = st.sidebar.columns([1, 1])
with col_inc1:
    if st.button("➕ 次數 +1"):
        rebalance_count += 1
        saved_config["rebalance_count"] = rebalance_count
        save_config(saved_config)
        st.rerun()

# ---------------------------------------------------------
# 2. 抓取即時價格數據、大盤標的與 USDHKD 匯率
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_market_data(active_tickers):
    prices = {}
    all_tickers = list(set(active_tickers + ["QQQ", "SPY"]))
    for ticker in all_tickers:
        try:
            data = yf.Ticker(ticker)
            price = data.fast_info['lastPrice']
            prices[ticker] = round(price, 2)
        except Exception:
            fallback_prices = {"QTOP": 100.0, "QLD": 100.0, "BOXX": 100.0, "QQQ": 500.0, "SPY": 570.0}
            prices[ticker] = fallback_prices.get(ticker, 100.0)
    
    try:
        fx = yf.Ticker("USDHKD=X").fast_info['lastPrice']
        usd_hkd = round(fx, 4)
    except Exception:
        usd_hkd = 7.8200

    return prices, usd_hkd

prices, usd_hkd_rate = fetch_market_data(tickers)

# 頂部操作區：刷新股價按鈕與匯率顯示
col_btn, col_fx = st.columns([2, 3])
with col_btn:
    if st.button("🔄 更新當前股價與匯率", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

with col_fx:
    st.caption(f"💱 當前市場即時匯率：**1 USD = {usd_hkd_rate:.4f} HKD**")

# ---------------------------------------------------------
# 3. 計算當前組合狀況
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

if current_portfolio_usd > 0:
    df["當前權重 (%)"] = (df["當前市值 ($USD)"] / current_portfolio_usd) * 100
else:
    df["當前權重 (%)"] = 0.0

current_portfolio_beta = (df["當前權重 (%)"] / 100 * df["個股 Beta"]).sum()

# ---------------------------------------------------------
# 4. 初始化/讀取成立日基準數據
# ---------------------------------------------------------
benchmark_base = saved_config.get("benchmark_base_prices", {})
if not benchmark_base.get("QQQ") or not benchmark_base.get("SPY"):
    benchmark_base = {
        "QQQ": prices.get("QQQ", 500.0),
        "SPY": prices.get("SPY", 570.0)
    }
    saved_config["benchmark_base_prices"] = benchmark_base

initial_hkd = saved_config.get("initial_portfolio_hkd")
if initial_hkd is None or initial_hkd == 0.0:
    initial_hkd = current_portfolio_hkd
    saved_config["initial_portfolio_hkd"] = initial_hkd

save_config(saved_config)

# 計算累積報酬率
portfolio_return_pct = ((current_portfolio_hkd - initial_hkd) / initial_hkd * 100) if initial_hkd > 0 else 0.0
qqq_return_pct = ((prices.get("QQQ", 1) - benchmark_base["QQQ"]) / benchmark_base["QQQ"] * 100) if benchmark_base["QQQ"] > 0 else 0.0
spy_return_pct = ((prices.get("SPY", 1) - benchmark_base["SPY"]) / benchmark_base["SPY"] * 100) if benchmark_base["SPY"] > 0 else 0.0

# ---------------------------------------------------------
# 觸發條件提示：若 Beta 低於 0.9 則顯示強提醒
# ---------------------------------------------------------
if current_portfolio_beta < 0.9:
    st.warning(
        f"🚨 **再平衡警示觸發**：當前組合 Beta 為 **{current_portfolio_beta:.3f}**（低於 0.9 臨界值）！"
        f"建議立即進行再平衡調整。"
    )

# ---------------------------------------------------------
# 5. 美化顯示：組合累積表現與歷史走勢圖
# ---------------------------------------------------------
st.markdown("---")
st.subheader(f"📅 組合累積表現與大盤對比 (成立日期: {INIT_DATE_STR})")

def render_performance_card(title, return_val, subtitle=None):
    if return_val > 0:
        color = "#00C853"
        bg_color = "rgba(0, 200, 83, 0.08)"
        border_color = "#00C853"
        sign = "+"
    elif return_val < 0:
        color = "#D50000"
        bg_color = "rgba(213, 0, 0, 0.08)"
        border_color = "#D50000"
        sign = ""
    else:
        color = "#6c757d"
        bg_color = "rgba(108, 117, 125, 0.08)"
        border_color = "#6c757d"
        sign = "+"

    sub_html = f'<div style="font-size: 0.85rem; color: #888; margin-top: 4px;">{subtitle}</div>' if subtitle else ""

    return f"""
    <div style="
        background-color: {bg_color}; 
        border-left: 4px solid {border_color}; 
        padding: 12px 16px; 
        border-radius: 8px; 
        margin-bottom: 10px;
    ">
        <div style="font-size: 0.9rem; font-weight: 600; color: #555;">{title}</div>
        <div style="font-size: 1.6rem; font-weight: 700; color: {color}; margin-top: 2px;">
            {sign}{return_val:.2f}%
        </div>
        {sub_html}
    </div>
    """

bcol1, bcol2, bcol3, bcol4 = st.columns(4)

with bcol1:
    st.markdown(f"""
    <div style="background-color: rgba(120, 120, 120, 0.08); border-left: 4px solid #6c757d; padding: 12px 16px; border-radius: 8px;">
        <div style="font-size: 0.9rem; font-weight: 600; color: #555;">初始總本金 (HKD)</div>
        <div style="font-size: 1.5rem; font-weight: 700; color: #333; margin-top: 2px;">
            ${initial_hkd:,.2f} HKD
        </div>
    </div>
    """, unsafe_allow_html=True)

with bcol2:
    st.markdown(render_performance_card("本組合累積報酬率", portfolio_return_pct), unsafe_allow_html=True)

with bcol3:
    st.markdown(render_performance_card("QQQ 大盤報酬率", qqq_return_pct, f"現價: ${prices.get('QQQ', 0):.2f}"), unsafe_allow_html=True)

with bcol4:
    st.markdown(render_performance_card("SPY 大盤報酬率", spy_return_pct, f"現價: ${prices.get('SPY', 0):.2f}"), unsafe_allow_html=True)

# --- Plotly 互動式歷史對比走勢圖 ---
@st.cache_data(ttl=3600)
def fetch_historical_trends(active_tickers, start_date):
    """根據指定起始日期抓取歷史股價數據"""
    try:
        all_tickers = list(set(active_tickers + ["QQQ", "SPY"]))
        df_hist = yf.download(all_tickers, start=start_date, progress=False)["Close"]
        if df_hist.empty:
            return None
        if isinstance(df_hist, pd.Series):
            df_hist = df_hist.to_frame()
        df_hist = df_hist.ffill().bfill()
        return df_hist
    except Exception:
        return None

with st.expander("📈 點擊展開/收合：組合歷史累積報酬率 vs QQQ / SPY 走勢對比圖", expanded=True):
    timeframe = st.radio(
        "選擇走勢圖時間範圍：",
        ["近 1 日", "近 1 週", "近 1 個月", "近 3 個月", "成立至今"],
        index=4,
        horizontal=True
    )

    today = datetime.now()
    if timeframe == "近 1 日":
        start_date = (today - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    elif timeframe == "近 1 週":
        start_date = (today - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    elif timeframe == "近 1 個月":
        start_date = (today - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    elif timeframe == "近 3 個月":
        start_date = (today - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    else:
        start_date = INIT_DATE_STR

    df_history = fetch_historical_trends(tickers, start_date)
    
    if df_history is not None and not df_history.empty and len(df_history) >= 2:
        if timeframe == "近 1 日":
            df_history = df_history.tail(2)

        chart_df = pd.DataFrame(index=df_history.index)

        portfolio_daily_val = pd.Series(0.0, index=df_history.index)
        for t in tickers:
            if t in df_history.columns:
                portfolio_daily_val += df_history[t] * current_shares[t]

        base_val = portfolio_daily_val.iloc[0]
        if base_val > 0:
            chart_df["本投資組合 (%)"] = ((portfolio_daily_val - base_val) / base_val) * 100

        if "QQQ" in df_history.columns and df_history["QQQ"].iloc[0] > 0:
            base_qqq = df_history["QQQ"].iloc[0]
            chart_df["QQQ (%)"] = ((df_history["QQQ"] - base_qqq) / base_qqq) * 100

        if "SPY" in df_history.columns and df_history["SPY"].iloc[0] > 0:
            base_spy = df_history["SPY"].iloc[0]
            chart_df["SPY (%)"] = ((df_history["SPY"] - base_spy) / base_spy) * 100

        # [優化點 2] 使用 Plotly 繪製互動式對比圖
        fig = px.line(
            chart_df, 
            x=chart_df.index, 
            y=chart_df.columns,
            labels={"value": "累積報酬率 (%)", "Date": "日期", "variable": "標的"},
            title="累積報酬率 (%) 趨勢比較"
        )
        fig.update_layout(hovermode="x unified", legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("💡 該時間範圍內暫無足夠歷史交易數據可供繪製對比圖。")

# ---------------------------------------------------------
# 6. 當前組合主要指標
# ---------------------------------------------------------
st.markdown("---")
mcol1, mcol2, mcol3, mcol4, mcol5 = st.columns(5)

mcol1.metric("組合當前總市值", f"${current_portfolio_hkd:,.2f} HKD")
mcol2.metric("預計投入新資金", f"${new_capital_hkd:,.2f} HKD")
mcol3.metric("再平衡總資金池", f"${total_rebalance_hkd:,.2f} HKD")
mcol4.metric("當前組合 Beta", f"{current_portfolio_beta:.3f}")
mcol5.metric("已執行再平衡次數", f"第 {rebalance_count} 次")

# 階梯機制建議計算
beta_diff = 1.0 - current_portfolio_beta
steps = int(beta_diff // 0.1) if beta_diff > 0 else 0

auto_target_qld = min(30.0 + (steps * 10.0), 70.0)
auto_target_boxx = max(30.0 - (steps * 10.0), 0.0)
auto_target_qtop = 100.0 - auto_target_qld - auto_target_boxx

# ---------------------------------------------------------
# 7. 再平衡目標權重調整
# ---------------------------------------------------------
st.subheader("🎯 再平衡目標權重調整")

is_default_portfolio = set(tickers) == {"QTOP", "QLD", "BOXX"}

if is_default_portfolio:
    preset_options = {
        "自動階梯建議 (依當前 Beta 自動計算)": "AUTO",
        "40% QTOP / 30% QLD / 30% BOXX  (組合 Beta 1.0)": (40.0, 30.0, 30.0),
        "50% QTOP / 30% QLD / 20% BOXX  (組合 Beta 1.1)": (50.0, 30.0, 20.0),
        "40% QTOP / 40% QLD / 20% BOXX  (組合 Beta 1.2)": (40.0, 40.0, 20.0),
        "50% QTOP / 40% QLD / 10% BOXX  (組合 Beta 1.3)": (50.0, 40.0, 10.0),
        "40% QTOP / 50% QLD / 10% BOXX  (組合 Beta 1.4)": (40.0, 50.0, 10.0),
        "50% QTOP / 50% QLD / 0% BOXX   (組合 Beta 1.5)": (50.0, 50.0, 0.0),
        "自訂手動填寫 (Custom)": "CUSTOM"
    }

    selected_preset_label = st.selectbox(
        "選擇目標配置模組：", 
        options=list(preset_options.keys())
    )

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
    st.info("💡 偵測到自訂持倉組合，請為各資產填寫目標再平衡權重 (%)：")
    targets = {}
    cols = st.columns(min(len(tickers), 4))
    default_w = round(100.0 / len(tickers), 1)
    for idx, t in enumerate(tickers):
        c = cols[idx % len(cols)]
        targets[t] = c.number_input(f"{t} 目標權重 (%)", value=default_w, step=1.0, key=f"target_{t}")

total_target_pct = sum(targets.values())

if abs(total_target_pct - 100.0) > 0.01:
    st.error(f"⚠️ 目標權重總和必須為 100%！（目前總和：{total_target_pct:.1f}%）")
else:
    df["目標權重 (%)"] = df["股票代碼"].map(targets)
    df["目標市值 ($USD)"] = total_rebalance_usd * (df["目標權重 (%)"] / 100)
    df["目標市值 ($HKD)"] = df["目標市值 ($USD)"] * usd_hkd_rate
    df["需調整金額 ($USD)"] = df["目標市值 ($USD)"] - df["當前市值 ($USD)"]
    df["需調整金額 ($HKD)"] = df["需調整金額 ($USD)"] * usd_hkd_rate
    df["建議交易股數"] = (df["需調整金額 ($USD)"] / df["單價 ($USD)"]).round(0).astype(int)
    
    def parse_action(shares):
        if shares > 0:
            return f"🟢 買入 {shares:,} 股"
        elif shares < 0:
            return f"🔴 賣出 {abs(shares):,} 股"
        else:
            return "⚪ 維持不變"

    df["交易動作"] = df["建議交易股數"].apply(parse_action)

    st.subheader("📊 持倉分析與再平衡建議表 (含港幣換算)")
    display_cols = [
        "股票代碼", "單價 ($USD)", "持有股數", "當前權重 (%)", 
        "當前市值 ($HKD)", "目標權重 (%)", "目標市值 ($HKD)", 
        "需調整金額 ($HKD)", "交易動作"
    ]
    
    st.dataframe(df[display_cols].style.format({
        "單價 ($USD)": "${:.2f}",
        "當前權重 (%)": "{:.1f}%",
        "當前市值 ($HKD)": "${:,.2f} HKD",
        "目標權重 (%)": "{:.1f}%",
        "目標市值 ($HKD)": "${:,.2f} HKD",
        "需調整金額 ($HKD)": "${:,.2f} HKD"
    }), use_container_width=True)

    target_beta = (df["目標權重 (%)"] / 100 * df["個股 Beta"]).sum()
    st.info(f"💡 再平衡調整後的預期組合 Beta 將為：**{target_beta:.3f}**")

    # [優化點 1] 新增「一鍵套用再平衡」按鈕
    st.markdown("---")
    if st.button("✅ 確認執行再平衡並更新持倉", use_container_width=True):
        new_shares_dict = {}
        for _, row in df.iterrows():
            t = row["股票代碼"]
            adj_shares = row["建議交易股數"]
            new_shares_dict[t] = int(row["持有股數"] + adj_shares)
        
        saved_config["shares"] = new_shares_dict
        saved_config["new_capital_hkd"] = 0.0  # 注入資金歸零
        saved_config["rebalance_count"] = saved_config.get("rebalance_count", 0) + 1  # 再平衡次數 +1
        save_config(saved_config)
        
        st.success("🎉 再平衡成功套用！持倉股數已更新，注入新資金已重置為 0 HKD，再平衡次數 +1。")
        st.rerun()