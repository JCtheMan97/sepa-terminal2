import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import os
import re

# 1. 網頁初始設定
st.set_page_config(page_title="🏆 SEPA 雙軌強勢股終端機", layout="wide")

# 2. 自動載入後台字典 (相容 UTF-8-sig)
@st.cache_data
def load_stock_dict():
    stock_dict = {}
    file_path = "stocks_list.txt"
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                for line in f:
                    if ',' in line:
                        code, name = line.strip().split(',', 1)
                        stock_dict[code.strip()] = name.strip()
            # ➡️ 選項二：【量化研究流】內斂灰色小字，加上金融專用千分位格式
            st.sidebar.caption(f"📊 核心引擎：台股標的資料庫已就緒 (已同步 {len(stock_dict):,} 檔成分股)")
        except Exception as e:
            st.sidebar.error(f"系統資料庫讀取失敗: {e}")
    return stock_dict

STOCK_DICT = load_stock_dict()

# --- 🎯 快取下載與運算引擎 ---
@st.cache_data(ttl=3600)  # 快取1小時，避免重複請求
def fetch_and_sync_data(tickers, start_date, end_date):
    """將 yfinance 下載與基本資料同步邏輯獨立並進行快取"""
    df_all = yf.download(tickers, start=start_date, end=end_date, progress=False, auto_adjust=False)
    return df_all

# --- 🎯 網頁標題與馬克心法區塊 ---
st.title("🏆 SEPA 技術面篩選模組 - 雙軌相對強度決策終端機")

# 🌟 新增：馬克·米奈爾維尼 核心格言
st.info("🔥 「逆風不倒的韌性，就是下一波超級飆股的邀請函。」—— 馬克·米奈爾維尼 (Mark Minervini)")

# 🌟 新增：SEPA 核心心法展開區塊
with st.expander("📖 閱讀 SEPA 系統核心心法 (Trade Like a Stock Market Wizard)", expanded=True):
    st.markdown("""
    大盤修正（Market Correction）或熊市，正是篩選「下一波超級飆股（Next Superperformers）」的黃金時間。當平庸的投資人因恐慌而遠離市場時，我們必須密切緊盯那些「抗跌並拒絕下跌」的個股，因為這正代表了機構法人正在瘋狂暗中吃貨。

    🎯 真正能創造數倍暴利的市場領導股（Market Leaders），通常具有以下三個特質：
    1. 在大盤中度修正時，它們跌得最少（甚至逆勢橫盤或創高）。
    2. 在大盤觸底時，它們是最先拔地而起、率先突破的個股。
    3. 大盤的跌勢，是在幫這些強勢股清洗浮額（Weak hands），並讓其完美的 VCP（波動率收縮型態） 成型。
    """)

st.markdown("""
---
本系統完美融合 IBD式 長線動能指標 與 短線逆風防守照妖鏡：
* 📈 長線動能：採用經典權重公式 (`3M*2 + 6M + 9M + 12M`)，並以 元大台灣50 (0050) 為比較基準。
* 🔍 短線抗跌：系統將根據大盤回檔天數，動態計算抗跌合格門檻，完美避開極短線的分母效應。
""")

# --- ⚙️ 側邊欄控制面板 ---
with st.sidebar.form("sepa_integrated_form"):
    st.header("⚙️ 雙軌指標參數設定")
    
    default_pool = (
        "2337.TW,旺宏\n3406.TW,玉晶光\n3550.TW,聯穎\n6187.TWO,萬潤\n3037.TW,欣興\n3017.TW,奇鋐\n"
        "8086.TWO,宏捷科\n4749.TWO,新應材\n3680.TWO,家登\n8021.TW,尖點\n3481.TW,群創\n"
        "8438.TW,昶昕\n3691.TWO,碩禾\n2423.TW,固緯\n8147.TWO,正淩\n5284.TW,JPP-KY\n"
        "2493.TW,揚博\n3023.TW,信邦\n6672.TW,騰輝電子\n3044.TW,健鼎\n6134.TWO,萬旭\n2413.TW,環科\n3577.TWO,泓格\n3305.TW,昇貿"
    )
    stock_input = st.text_area("股票清單 (支援複製貼上！系統會自動過濾國籍、財報等非代號雜訊)", value=default_pool, height=300)
    
    st.subheader("【短線逆風照妖鏡參數】")
    lookback_days = st.number_input("自訂照妖鏡觀察天數", min_value=5, max_value=365, value=60, step=1)
    market_threshold = st.slider("大盤恐慌日定義 (單日跌幅 %)", min_value=0.5, max_value=2.5, value=1.0, step=0.1)
    
    # ==========================================
    # 🆕 新增功能：回溯時間軸與績效回測 (升級精準持有交易日)
    # ==========================================
    st.subheader("【🕒 歷史回溯與績效回測】")
    backtest_date = st.date_input("選擇回溯基準日 (以此日視為當時的今天)", value=datetime.today())
    
    # 🆕 新增：自訂持有天數（交易日）
    holding_days = st.number_input("回溯後預計持有天數 (交易日)", min_value=1, max_value=120, value=20, step=1)
    
    is_backtesting = backtest_date < datetime.today().date()
    
    submit_btn = st.form_submit_button("🚀 執行雙軌交叉選股分析")

def get_stocks_pool(text):
    """智能掃描器：自動比對輸入文字與 STOCK_DICT 名稱"""
    pool = []
    
    # 將每一行切割處理
    for line in text.split('\n'):
        line = line.strip()
        if not line: continue
        
        # 1. 第一優先：Regex 抓代號 (最準確)
        code_match = re.search(r'\b\d{4,6}\b', line)
        if code_match:
            code = code_match.group()
            # 檢查 code 或 code.TW / code.TWO
            found = False
            for suffix in ["", ".TW", ".TWO"]:
                target = f"{code}{suffix}" if suffix else code
                if target in STOCK_DICT:
                    pool.append({"id": target, "name": STOCK_DICT[target]})
                    found = True
                    break
            if found: continue

        # 2. 第二優先：掃描全資料庫進行「模糊匹配」
        # 只要輸入的文字「包含」在正式名稱裡，就算抓到
        found_name = False
        for code, official_name in STOCK_DICT.items():
            # 檢查：使用者的輸入是否在正式名稱中 (例如: 輸入 "金居" 在 "金居開發" 內)
            if line in official_name or official_name in line:
                pool.append({"id": code, "name": official_name})
                found_name = True
                break # 找到一個符合的就跳出
        
        if not found_name:
            # 側邊欄提示哪些沒抓到，方便您除錯
            st.sidebar.warning(f"⚠️ 找不到此標的: {line}")
            
    # 移除重複 (防止多種匹配結果)
    return list({item['id']: item for item in pool}.values())

if 'first_run' not in st.session_state:
    st.session_state.first_run = True

if submit_btn or st.session_state.first_run:
    STOCKS_POOL = get_stocks_pool(stock_input)
    st.session_state.first_run = False
    
    # 將原本的 end_date 錨定在使用者選擇的 backtest_date
    end_date = datetime.combine(backtest_date, datetime.min.time())
    real_today = datetime.today() # 真正的今天，用來計算回測報酬率
    
    # 🌟 貼近 TradingView 的改動：長線回溯擴展至 730 天（2年），提供足夠的 warm-up 歷史資料供 200MA 計算與平穩
    start_date_long = end_date - timedelta(days=730) 
    start_date_short = end_date - timedelta(days=int(lookback_days))
    
    with st.spinner("量化引擎計算中... 正在進行一鍵式批次下載與時間軸同步校正..."):
        try:
            if not STOCKS_POOL:
                st.error("❌ 過濾雜訊後，未偵測到任何有效的股票代號，請重新輸入。")
            else:
                all_tickers = ["0050.TW"] + [stock["id"] for stock in STOCKS_POOL]
                
                # 核心改動：為了計算後續績效，下載範圍必須延伸到真正的今日 (real_today)
                df_all = fetch_and_sync_data(tuple(all_tickers), start_date_long.strftime('%Y-%m-%d'), real_today.strftime('%Y-%m-%d'))
                
                df_adj = df_all['Adj Close'] if 'Adj Close' in df_all.columns.levels[0] else df_all['Close']
                
                # 這裡過濾出回溯基準日前的歷史大盤數據，用作當時篩選的基準線
                b_c_all = df_adj["0050.TW"].dropna()
                b_c = b_c_all.loc[:end_date.strftime('%Y-%m-%d')]
                
                if b_c.empty:
                    st.error("❌ 回溯基準日無交易數據或超出歷史範圍，請重新選擇。")
                else:
                    # 🚀 新增：精準定位歷史基準日在完整時間軸的位置，以推算後續固定天數的交易日
                    idx_now = b_c.index[-1]
                    loc_now = b_c_all.index.get_loc(idx_now)
                    
                    # 🚀 新增：推算後續第 X 個交易日的日期
                    if loc_now + holding_days < len(b_c_all):
                        idx_future = b_c_all.index[loc_now + holding_days]
                        actual_holding_text = f"後續 {holding_days} 個交易日 (至 {idx_future.strftime('%Y-%m-%d')})"
                    else:
                        idx_future = b_c_all.index[-1]
                        actual_holding_text = f"後續 {len(b_c_all) - 1 - loc_now} 個交易日 (資料庫極限至今日 {idx_future.strftime('%Y-%m-%d')})"

                    # 大盤基準線
                    idx_3m, idx_6m, idx_9m, idx_1y = b_c.index[-63], b_c.index[-126], b_c.index[-189], b_c.index[-252]
                    b_now, b_3m, b_6m, b_9m, b_1y = b_c.loc[idx_now], b_c.loc[idx_3m], b_c.loc[idx_6m], b_c.loc[idx_9m], b_c.loc[idx_1y]
                    benchmark_ibd_score = ((b_now/b_3m*2) + (b_now/b_6m) + (b_now/b_9m) + (b_now/b_1y)) / 5 * 100
                    
                    # 短線照妖鏡
                    b_short_df = pd.DataFrame(b_c.loc[start_date_short.strftime('%Y-%m-%d'):])
                    b_short_df.columns = ['Close_Price']
                    b_short_df['Market_Return'] = b_short_df['Close_Price'].pct_change() * 100
                    panic_days = b_short_df[b_short_df['Market_Return'] <= -market_threshold]
                    total_panic_days = len(panic_days)
                    panic_dates_list = panic_days.index.tolist()
                    
                    dynamic_threshold = 55.0 if total_panic_days <= 5 else (70.0 if total_panic_days <= 15 else 80.0)
                    level_desc = "⚡ 極短線回檔（採取寬鬆防守標準，勝率過半即合格）" if total_panic_days <= 5 else ("⚖️ 標準波段修正（採取黃金 70% 機構防守標準）" if total_panic_days <= 15 else "🚨 空頭大屠殺 / 系統性風險（採取極嚴苛 80% 沙裡淘金標準）")
                    
                    integrated_results = []
                    skipped_stocks = []
                    
                    for stock in STOCKS_POOL:
                        ticker = stock["id"]
                        
                        if ticker not in df_adj.columns:
                            skipped_stocks.append(stock["name"])
                            continue
                        
                        # 🌟 貼近 TradingView 的核心改動：直接提取個股自身最原始、未包含聯合成份股 NaN 填充的純淨序列
                        s_series_raw_all = df_adj[ticker].dropna()
                        s_series_raw = s_series_raw_all.loc[:end_date.strftime('%Y-%m-%d')]
                        
                        if s_series_raw.empty:
                            skipped_stocks.append(stock["name"])
                            continue
                            
                        p_now = s_series_raw.iloc[-1]
                        
                        # --- 🌟 貼近 TradingView 改動：在純淨的原生時間軸計算 50MA 與 乖離率 ---
                        if len(s_series_raw) >= 50:
                            ma50_val = s_series_raw.rolling(window=50).mean().iloc[-1]
                            bias_50 = ((p_now - ma50_val) / ma50_val) * 100
                        else:
                            bias_50 = 0.0
                            
                        # 🛡️ 轉譯：依據純淨原生K線計算馬克 7 大趨勢模板核心條件，徹底排除對齊帶來的盲點
                        if len(s_series_raw) >= 200:
                            sma50_s = s_series_raw.rolling(50).mean()
                            sma150_s = s_series_raw.rolling(150).mean()
                            sma200_s = s_series_raw.rolling(200).mean()
                            
                            m50 = sma50_s.iloc[-1]
                            m150 = sma150_s.iloc[-1]
                            m200 = sma200_s.iloc[-1]
                            m200_22 = sma200_s.shift(22).iloc[-1] if len(sma200_s) > 22 else np.nan
                            
                            h252 = s_series_raw.rolling(252, min_periods=1).max().iloc[-1]
                            l252 = s_series_raw.rolling(252, min_periods=1).min().iloc[-1]
                            
                            cond1 = (p_now > m150) and (p_now > m200)
                            cond2 = m150 > m200
                            cond3 = (m200 > m200_22) if not pd.isna(m200_22) else False
                            cond4 = (m50 > m150) and (m50 > m200)
                            cond5 = p_now > m50
                            cond6 = ((p_now / l252) - 1) * 100 >= 25 if l252 > 0 else False
                            cond7 = (1 - (p_now / h252)) * 100 <= 25 if h252 > 0 else False
                            
                            is_trend_template = cond1 and cond2 and cond3 and cond4 and cond5 and cond6 and cond7
                        else:
                            is_trend_template = False

                        # --- 🌟 相對強度指標（Alpha RS / IBD 分數 / 抗跌韌性）部分：對齊大盤基準線進行跨主體比對 ---
                        s_series_aligned = s_series_raw.reindex(b_c.index).ffill()
                        
                        def get_v(s, idx): 
                            valid = s.dropna()
                            if valid.empty: return np.nan
                            return valid.loc[valid.index[np.argmin(np.abs(valid.index - idx))]]
                        
                        s_n, s_3, s_6, s_9, s_1 = get_v(s_series_aligned, idx_now), get_v(s_series_aligned, idx_3m), get_v(s_series_aligned, idx_6m), get_v(s_series_aligned, idx_9m), get_v(s_series_aligned, idx_1y)
                        
                        if not pd.isna(s_n) and s_3 > 0 and s_6 > 0 and s_9 > 0 and s_1 > 0:
                            ibd = ((s_n/s_3*2) + (s_n/s_6) + (s_n/s_9) + (s_n/s_1)) / 5 * 100
                        else:
                            ibd = 0.0
                        
                        s_ret = s_series_aligned.pct_change() * 100
                        outperform = np.sum(s_ret.reindex(panic_dates_list) > b_short_df.loc[panic_dates_list, 'Market_Return'])
                        resilience = (outperform / total_panic_days * 100) if total_panic_days > 0 else 100
                        
                        # ==========================================
                        # 💡 【核心整合】原第 11 欄：VCP 與 動能狀態判定 💡
                        # ==========================================
                        is_price_new_high = False
                        is_alpha_new_high = False
                        is_alpha_lagging = False
                        is_vcp_80 = False
                        is_vcp_90 = False
                        is_rs_recovering = False
                        
                        if len(s_series_aligned.dropna()) >= 30:
                            valid_aligned = s_series_aligned.dropna()
                            same_idx_b = b_c.reindex(valid_aligned.index).ffill()
                            rel_close = valid_aligned / same_idx_b
                            
                            # 雙軌領先/背離偵測 (以30日為基準軸)
                            is_price_new_high = p_now >= valid_aligned.iloc[-31:-1].max()
                            is_alpha_new_high = rel_close.iloc[-1] >= rel_close.iloc[-31:-1].max()
                            is_alpha_lagging = rel_close.iloc[-1] < rel_close.iloc[-31:-1].max()
                            
                            # 短線動能回復 (Relative RS 連續3日走揚)
                            if len(rel_close) >= 3:
                                is_rs_recovering = rel_close.iloc[-1] > rel_close.iloc[-2] and rel_close.iloc[-2] > rel_close.iloc[-3]
                            
                            # VCP 緊縮指標量化計算 (5日價格波動度 / 20日均值)
                            roll_std5 = valid_aligned.rolling(5).std()
                            roll_mean5 = valid_aligned.rolling(5).mean()
                            cv_5 = roll_std5 / roll_mean5
                            if len(cv_5) >= 20:
                                cv_5_ma20 = cv_5.rolling(20).mean()
                                cv_5_now = cv_5.iloc[-1]
                                cv_5_ma20_now = cv_5_ma20.iloc[-1]
                                is_vcp_80 = cv_5_now < cv_5_ma20_now * 0.80
                                is_vcp_90 = cv_5_now < cv_5_ma20_now * 0.90
                        
                        is_rs_leading = (not is_price_new_high) and is_alpha_new_high
                        is_div_warning = is_price_new_high and is_alpha_lagging
                        
                        # 結構特徵分配
                        if is_vcp_80:
                            struct_status = "💎 極致壓縮(80%+CV)"
                        elif is_vcp_90:
                            struct_status = "🔥 相對壓縮(90%+CV)"
                        elif is_vcp_1y := is_rs_recovering:
                            struct_status = "📈 動能回復中"
                        else:
                            struct_status = "⏳ 區間整理"
                            
                        # 領先與背離狀態首碼
                        lead_prefix = ""
                        if is_rs_leading:
                            lead_prefix = "🌟 雙軌領先 | "
                        elif is_div_warning:
                            lead_prefix = "⚠️ 雙軌背離 | "
                            
                        vcp_status_final = lead_prefix + struct_status
                        
                        # 依據判定結果在股票名稱前標記 ✅ 或 ❌，並在後方結合 VCP/動能 綜合狀態字串
                        display_name = f"✅ {stock['name']} 【{vcp_status_final}】" if is_trend_template else f"❌ {stock['name']} 【{vcp_status_final}】"
                        
                        # ==========================================
                        # 🚀 核心修改：精準推算「後續指定交易日內」的實質報酬率（增加未來交易日的存在性查驗與容錯映射）
                        # ==========================================
                        if idx_future in s_series_raw_all.index:
                            price_future = s_series_raw_all.loc[idx_future]
                            future_return = ((price_future / p_now) - 1) * 100
                        else:
                            # 容錯處理：若個股當日無資料（可能因停牌或特殊休市），尋找大於等於該日期的最近一個有效報價
                            available_future_dates = s_series_raw_all.index[s_series_raw_all.index >= idx_future]
                            if not available_future_dates.empty:
                                price_future = s_series_raw_all.loc[available_future_dates[0]]
                                future_return = ((price_future / p_now) - 1) * 100
                            else:
                                future_return = 0.0

                        perf_col_key = f"後續{holding_days}日實際報酬(%)"

                        integrated_results.append({
                            "股票代號": ticker.split(".")[0], "股票名稱": display_name,
                            "50MA乖離率(%)": bias_50,
                            "IBD式 絕對分數": ibd, "對比 0050 超額強度": ibd - benchmark_ibd_score,
                            "短線抗跌韌性分數": resilience, "逆風勝率": f"{outperform} / {total_panic_days} 天",
                            "逆風上漲天數": f"{np.sum(s_ret.reindex(panic_dates_list) > 0)} 天",
                            perf_col_key: future_return # 儲存自訂持有期的績效數據
                        })
                    
                    # --- 修改：核心排序邏輯變更為「對比 0050 超額強度」由高到低（ascending=False） ---
                    df_final = pd.DataFrame(integrated_results).sort_values("對比 0050 超額強度", ascending=False)
                    
                    # 🛠️ 核心改動：調整欄位順序，把「50MA乖離率(%)」與「後續X日實際報酬(%)」放到後面
                    cols = df_final.columns.tolist()
                    perf_col_name = f"後續{holding_days}日實際報酬(%)"
                    
                    if "50MA乖離率(%)" in cols:
                        cols.remove("50MA乖離率(%)")
                        cols.append("50MA乖離率(%)")
                    if perf_col_name in cols:
                        cols.remove(perf_col_name)
                        # 如果在回測模式，就把實際報酬往前移到第三欄顯眼處，否則放最後
                        if is_backtesting:
                            cols.insert(2, perf_col_name)
                        else:
                            cols.append(perf_col_name)
                    df_final = df_final[cols]
                    
                    st.subheader(f"📊 雙軌數據交叉比對表 (基準日大盤恐慌日：{total_panic_days} 天)")
                    
                    # 提示當前半溯狀態
                    if is_backtesting:
                        st.warning(f"🕒 目前處於【回溯歷史選股模式】。基準日：{backtest_date.strftime('%Y-%m-%d')}。已為您追蹤其後 {actual_holding_text} 的精準實質報酬。")
                    else:
                        st.info(f"💡 照妖鏡判定：{level_desc}。抗跌合格線：`{dynamic_threshold}%`")
                    
                    # 🌟 新增：符號意義說明區塊 (是否符合馬克選股模板 + VCP 狀態註解)
                    with st.expander("🔍 符號意義與馬克趨勢模板 (Trend Template) 說明", expanded=False):
                        st.markdown("""
                        * ✅ 符合標記：代表該股目前完全符合馬克·米奈爾維尼（Mark Minervini）的 7 大趨勢模板核心條件，正處於健康的第二階段（Stage 2）上升趨勢。
                        * ❌ 未符標記：代表該股目前未全數滿足 7 項技術面排列準則（可能均線結構仍待修復，或距 52 週高低點比例未達標）。
                        
                        🌀 VCP / 動能狀態動態標籤說明：
                        * 🌟 雙軌領先：個股股價尚未突破30日新高，但相對強度 (Alpha RS 曲線) 已率先刷新30日紀錄，暗示機構暗中強勢吃貨，極具爆發力。
                        * ⚠️ 雙軌背離：股價已創30日新高，但相對強度未同步創高，短線動能呈現隱形落後，需警惕高檔假突破。
                        * 💎 極致壓縮(80%+CV)：5日價格變異係數收縮至20日均值的 80% 以下，籌碼極度洗淨，多空面臨臨界點。
                        * 🔥 相對壓縮(90%+CV)：5日價格變異係數收縮至20日均值的 90% 以下，進入標準 VCP 波幅收緊軌道。
                        * 📈 動能回復中：短線相對強度曲線扭轉下行趨勢、連續 3 日走揚，代表短期動能正由弱轉強。
                        * ⏳ 區間整理：股價與動能處於正常箱型、橫盤 or 洗盤沉澱階段，未出現極端信號。
                        
                        📝 馬克選股 7 大趨勢模板核心準則：
                        1. 現價 > 150MA 且 現價 > 200MA（股價站長線均線之上）
                        2. 150MA > 200MA（長線均線維持多頭排列）
                        3. 200MA 處於上升趨勢（至少上揚 1 個月，此系統比對 22 天前數據）
                        4. 50MA > 150MA 且 50MA > 200MA（中期均線多頭黃金交叉）
                        5. 現價 > 50MA（股價站穩中期生命線）
                        6. 現價較過去 52 週最低點高出至少 25%（展現強勁築底反彈力道）
                        7. 現價距離過去 52 週最高點在 25% 以內（高檔強勢整理，伺機向上突破樞紐點）
                        """)
                    
                    if skipped_stocks:
                        st.warning(f"⚠️ 以下輸入內容格式正確，但 yfinance 查無交易歷史數據（可能剛上市或打錯）：{', '.join(skipped_stocks)}")
                    
                    # --- 新增：將 50MA乖離率 顯示在主表格中 ---
                    column_config_dict = {
                        "50MA乖離率(%)": st.column_config.NumberColumn("50MA乖離率", format="%.2f%%"),
                        "IBD式 絕對分數": st.column_config.NumberColumn("IBD式 絕對強度", format="%.1f"),
                        "短線抗跌韌性分數": st.column_config.ProgressColumn("抗跌得分", min_value=0, max_value=100, format="%.0f分")
                    }
                    if is_backtesting:
                        column_config_dict[perf_col_name] = st.column_config.NumberColumn(f"🎯 後續{holding_days}日報酬", format="%.2f%%")
                    else:
                        column_config_dict[perf_col_name] = st.column_config.NumberColumn("今日至今持平率", format="%.2f%%")
                        
                    # 直接將未更動底色的原生 Dataframe 傳入 st.dataframe
                    st.dataframe(df_final, use_container_width=True, hide_index=True, column_config=column_config_dict)
                    
                    # 四象限戰略部署
                    st.divider()
                    st.subheader("🏁 Mark Minervini 流派：雙軌交叉戰略部署")
                    st.caption(f"💡 註：括號內為 50MA 乖離率(%)。右側標註為【後續 {holding_days} 日回測實際報酬率】。")
                    true_leaders = df_final[(df_final["對比 0050 超額強度"] > 0) & (df_final["短線抗跌韌性分數"] >= dynamic_threshold)]
                    momentum_only = df_final[(df_final["對比 0050 超額強度"] > 0) & (df_final["短線抗跌韌性分數"] < dynamic_threshold)]
                    defensive_only = df_final[(df_final["對比 0050 超額強度"] <= 0) & (df_final["短線抗跌韌性分數"] >= dynamic_threshold)]
                    laggards = df_final[(df_final["對比 0050 超額強度"] <= 0) & (df_final["短線抗跌韌性分數"] < dynamic_threshold)]
                    
                    # --- 核心修改：自訂輸出格式函式，當乖離率 >= 30% 時，在括號內以內嵌 HTML 進行淡紅色底色標註 ---
                    def format_stocks(df, show_perf=False):
                        if df.empty:
                            return "無"
                        lines = []
                        for _, row in df.iterrows():
                            perf_str = f" ➡️ 後續報酬: {row[perf_col_name]:.1f}%" if show_perf else ""
                            bias_val = row['50MA乖離率(%)']
                            
                            # 判斷乖離率是否大於等於 30%，若是則加入淡紅色底色樣式標註
                            if bias_val >= 30.0:
                                bias_str = f"<span style='background-color: #ffcccc; color: #990000; padding: 2px 4px; border-radius: 4px; font-weight: bold;'>{bias_val:.1f}%</span>"
                            else:
                                bias_str = f"{bias_val:.1f}%"
                                
                            lines.append(f"* {row['股票名稱']} ({bias_str}){perf_str}")
                        return "\n".join(lines)

                    c1, c2 = st.columns(2)
                    # 💡 注意：由於使用了 HTML 標籤樣式，此處輸出調整為 st.write / st.markdown 以支援 HTML 渲染
                    c1.success(f"### 👑 第一象限：逆風真龍頭 ({len(true_leaders)} 檔)"); c1.markdown(format_stocks(true_leaders, is_backtesting), unsafe_allow_html=True); c1.caption("👉 戰略部署：長線動能擊敗大盤，且短線抗跌表現達到當前動態合格線以上。隨時注意 VCP 出量突破。")
                    c1.info(f"### 🚀 第二象限：高 Beta 攻擊兵 ({len(momentum_only)} 檔)"); c1.markdown(format_stocks(momentum_only, is_backtesting), unsafe_allow_html=True); c1.caption("👉 戰略部署：長線極強，但修正波動高於大盤. 一旦大盤止穩，這群股票往往是右側出量追擊的首選。")
                    c2.warning(f"### 🛡️ 第三象限：資金避風港 ({len(defensive_only)} 檔)"); c2.markdown(format_stocks(defensive_only, is_backtesting), unsafe_allow_html=True); c2.caption("👉 戰略部署：短線極度抗跌，長線動能尚未完全追上。若有打底完成標的，高抗跌意味主力在低檔死守，值得關注！")
                    c2.error(f"### 🚨 第四象限：無情剔除名單 ({len(laggards)} 檔)"); c2.markdown(format_stocks(laggards, is_backtesting), unsafe_allow_html=True); c2.caption("👉 戰略部署：長短線皆跑輸大盤，在馬克系統中屬於弱勢標的，建議審慎評估資金配置與汰弱留強。")
                    
        except Exception as e:
            st.error(f"數據錯誤: {e}")
