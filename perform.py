import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import os
import re
import requests  # 🆕 新增：用於自動抓取證交所API

# 1. 網頁初始設定
st.set_page_config(page_title="🏆 SEPA 雙軌強勢股終端機", layout="wide")

# 🆕 新增：自動抓取上市櫃處置股 API (OpenAPI)
@st.cache_data(ttl=3600)  # 快取1小時，避免頻繁請求官方API
def get_disposition_stocks():
    disposition_map = {}
    
    def format_roc_date(d_str):
        """將民國年 1130614 轉為 113/06/14 方便閱讀"""
        d_str = str(d_str).strip()
        if len(d_str) == 7:
            return f"{d_str[:3]}/{d_str[3:5]}/{d_str[5:]}"
        return d_str

    try:
        # 1. 抓取上市處置股 (TWSE OpenAPI)
        res_twse = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/TWT84U", timeout=10)
        if res_twse.status_code == 200:
            for item in res_twse.json():
                code = str(item.get('Code', '')).strip()
                start = item.get('Disp_Start', '')
                end = item.get('Disp_End', '')
                if code:
                    disposition_map[code] = f"{format_roc_date(start)} - {format_roc_date(end)}"
                    
        # 2. 抓取上櫃處置股 (TPEx OpenAPI)
        res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_disposition_securities", timeout=10)
        if res_tpex.status_code == 200:
            for item in res_tpex.json():
                code = str(item.get('SecuritiesCompanyCode', '')).strip()
                start = item.get('DispositionStart', '')
                end = item.get('DispositionEnd', '')
                if code:
                    disposition_map[code] = f"{format_roc_date(start)} - {format_roc_date(end)}"
    except Exception as e:
        pass # 若 API 異常則忽略，不影響主程式運行
        
    return disposition_map

DISPOSITION_STOCKS = get_disposition_stocks()

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
    1. 在大盤中度修正時，它們跌得最少（甚至逆勢橫盤 or 創高）。
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
        "2337.TW,旺宏\n3028.TW,增你強\n3550.TW,聯穎\n6187.TWO,萬潤\n3037.TW,欣興\n3017.TW,奇鋐\n"
        "8086.TWO,宏捷科\n4749.TWO,新應材\n3680.TWO,家登\n8021.TW,尖點\n3481.TW,群創\n"
        "8438.TW,昶昕\n3691.TWO,碩禾\n2423.TW,固緯\n8147.TWO,正淩\n6716.TWO,應廣\n2428.TW,興勤\n5284.TWO,JPP-KY\n"
        "2493.TW,揚博\n3023.TW,信邦\n6672.TW,騰輝電子\n3044.TW,健鼎\n6134.TWO,萬旭\n2413.TW,環科\n3577.TWO,泓格\n3305.TW,昇貿"
    )
    stock_input = st.text_area("股票清單 (支援複製貼上！系統會自動過濾國籍、財報等非代號雜訊)", value=default_pool, height=300)
    
    st.subheader("【短線逆風照妖鏡參數】")
    lookback_days = st.number_input("自訂照妖鏡觀察天數", min_value=5, max_value=365, value=60, step=1)
    market_threshold = st.slider("大盤恐慌日定義 (單日跌幅 %)", min_value=0.5, max_value=2.5, value=1.0, step=0.1)
    
    # 🆕 新增功能：回溯時間軸與績效回測 (升級精準持有交易日)
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
                
                # 🛠️ 核心修正 1：加上強制 +1 天位移，防止 yfinance 底層 Exclusive 機制吃掉最新一根 K 棒
                download_end_date = real_today + timedelta(days=1)
                df_all = fetch_and_sync_data(tuple(all_tickers), start_date_long.strftime('%Y-%m-%d'), download_end_date.strftime('%Y-%m-%d'))
                
                # 🛠️ 貼近 TradingView 核心修正 1：改以標準收盤價 'Close' 為準（僅調整股票股利/拆股，不扣除現金股利），完全對齊 TV 預設日線
                df_adj = df_all['Close'] if 'Close' in df_all.columns.levels[0] else df_all['Adj Close']
                df_vol = df_all['Volume'] # 提取成交量
                
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

                    # 🛠️ 貼近 TradingView 核心修正 2：大盤基準線 IBD 全面校正為 -64, -127, -190, -253 消除 Off-by-one 偏差，精準還原 Pine Script 的 bars 概念
                    if len(b_c) >= 253:
                        b_now_val = b_c.iloc[-1]
                        b_3m_val = b_c.iloc[-64]
                        b_6m_val = b_c.iloc[-127]
                        b_9m_val = b_c.iloc[-190]
                        b_1y_val = b_c.iloc[-253]
                        benchmark_ibd_score = ((b_now_val/b_3m_val*2) + (b_now_val/b_6m_val) + (b_now_val/b_9m_val) + (b_now_val/b_1y_val)) / 5 * 100
                    else:
                        benchmark_ibd_score = 0.0
                    
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
                        
                        # 🌟 直接提取個股自身最原始、未包含聯合成份股 NaN 填充的純淨序列
                        s_series_raw_all = df_adj[ticker].dropna()
                        s_series_raw = s_series_raw_all.loc[:end_date.strftime('%Y-%m-%d')]
                        
                        # 同步提取成交量
                        v_series_raw_all = df_vol[ticker].dropna()
                        v_series_raw = v_series_raw_all.loc[:end_date.strftime('%Y-%m-%d')]
                        
                        if s_series_raw.empty:
                            skipped_stocks.append(stock["name"])
                            continue
                            
                        p_now = s_series_raw.iloc[-1]
                        
                        # --- 🌟 在純淨的原生時間軸計算 50MA 與 乖離率 ---
                        if len(s_series_raw) >= 50:
                            ma50_val = s_series_raw.rolling(window=50).mean().iloc[-1]
                            bias_50 = ((p_now - ma50_val) / ma50_val) * 100
                        else:
                            bias_50 = 0.0
                            
                        # 🛡️ 轉譯：依據純淨原生K線計算馬克 7 大趨勢模板核心條件
                        if len(s_series_raw) >= 200:
                            sma50_s = s_series_raw.rolling(50).mean()
                            sma150_s = s_series_raw.rolling(150).mean()
                            sma200_s = s_series_raw.rolling(200).mean()
                            
                            m50 = sma50_s.iloc[-1]
                            m150 = sma150_s.iloc[-1]
                            m200 = sma200_s.iloc[-1]
                            
                            # 🛠️ 貼近 TradingView 核心修正 3：m200_22 改採原生 K 線直接提取倒數第 23 根 K 棒
                            m200_22 = sma200_s.iloc[-23] if len(sma200_s) >= 23 else np.nan
                            
                            # 🛠️ 貼近 TradingView 核心修正 4：52週最高最低點改用原生 K 線最後 252 根 K 棒的 Max/Min
                            h252 = s_series_raw.iloc[-252:].max() if len(s_series_raw) >= 252 else s_series_raw.max()
                            l252 = s_series_raw.iloc[-252:].min() if len(s_series_raw) >= 252 else s_series_raw.min()
                            
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

                        # --- 🌟 🛠️ 貼近 TradingView 核心修正 5：個股 IBD 全面校正
                        if len(s_series_raw) >= 253:
                            s_now_val = s_series_raw.iloc[-1]
                            s_3m_val = s_series_raw.iloc[-64]
                            s_6m_val = s_series_raw.iloc[-127]
                            s_9m_val = s_series_raw.iloc[-190]
                            s_1y_val = s_series_raw.iloc[-253]
                            ibd = ((s_now_val/s_3m_val*2) + (s_now_val/s_6m_val) + (s_now_val/s_9m_val) + (s_now_val/s_1y_val)) / 5 * 100
                        else:
                            ibd = 0.0
                        
                        # 🛠️ 核心修正 4：直接計算個股原生 K 線
                        s_ret = s_series_raw.pct_change() * 100
                        outperform = np.sum(s_ret.reindex(panic_dates_list) > b_short_df.loc[panic_dates_list, 'Market_Return'])
                        resilience = (outperform / total_panic_days * 100) if total_panic_days > 0 else 100
                        
                        # ==========================================
                        # 💡 【核心整合】原第 11 欄：VCP 與 動能狀態判定 💡
                        # 🛠️ 修正：引入 Volume 比對以對齊 TradingView 指標
                        # ==========================================
                        is_price_new_high = False
                        is_alpha_new_high = False
                        is_alpha_lagging = False
                        vcp_status_final = "⏳ 數據不足"
                        
                        if len(s_series_raw) >= 30:
                            # 對齊大盤
                            b_c_aligned_to_stock = b_c_all.reindex(s_series_raw.index).ffill()
                            rel_close = s_series_raw / b_c_aligned_to_stock
                            
                            # 雙軌領先/背離偵測
                            is_price_new_high = p_now >= s_series_raw.iloc[-31:-1].max()
                            is_alpha_new_high = rel_close.iloc[-1] >= rel_close.iloc[-31:-1].max()
                            is_alpha_lagging = rel_close.iloc[-1] < rel_close.iloc[-31:-1].max()
                            
                            is_rs_recovering = False
                            if len(rel_close) >= 3:
                                is_rs_recovering = rel_close.iloc[-1] > rel_close.iloc[-2] and rel_close.iloc[-2] > rel_close.iloc[-3]
                            
                            # 🛠️ [關鍵修正] 使用 ddof=0 嚴格對齊 Pine Script 的 ta.stdev
                            roll_std5 = s_series_raw.rolling(5).std(ddof=0)
                            roll_mean5 = s_series_raw.rolling(5).mean()
                            cv_5 = roll_std5 / roll_mean5
                            
                            # 🛠️ [關鍵修正] 同步計算 Volume 以對齊 Pine Script 的 is_quiet_platform
                            if len(v_series_raw) >= 20:
                                vol_sma3 = v_series_raw.rolling(3).mean().iloc[-1]
                                vol_sma20 = v_series_raw.rolling(20).mean().iloc[-1]
                                is_vol_quiet = vol_sma3 < (vol_sma20 * 0.7)
                            else:
                                is_vol_quiet = False

                            if len(cv_5) >= 20:
                                cv_5_ma20 = cv_5.rolling(20).mean()
                                cv_5_now = cv_5.iloc[-1]
                                cv_5_ma20_now = cv_5_ma20.iloc[-1]
                                
                                is_vcp_dead_quiet = is_vol_quiet and (cv_5_now < cv_5_ma20_now * 0.80)
                                is_vcp_80 = cv_5_now < cv_5_ma20_now * 0.80
                                is_vcp_90 = cv_5_now < cv_5_ma20_now * 0.90
                        
                                is_rs_leading = (not is_price_new_high) and is_alpha_new_high
                                is_div_warning = is_price_new_high and is_alpha_lagging
                                
                                # 結構特徵分配
                                if is_vcp_dead_quiet:
                                    struct_status = "💤 價格波動沉寂(Dead Quiet)"
                                elif is_vcp_80:
                                    struct_status = "💎 極致壓縮(80%+CV)"
                                elif is_vcp_90:
                                    struct_status = "🔥 相對壓縮(90%+CV)"
                                elif is_rs_recovering:
                                    struct_status = "📈 動能回復中"
                                else:
                                    struct_status = "⏳ 區間整理"
                                    
                                lead_prefix = ""
                                if is_rs_leading:
                                    lead_prefix = "🌟 雙軌領先 | "
                                elif is_div_warning:
                                    lead_prefix = "⚠️ 雙軌背離 | "
                                    
                                vcp_status_final = lead_prefix + struct_status
                        
                        # 依據判定結果
                        display_name = f"✅ {stock['name']} 【{vcp_status_final}】" if is_trend_template else f"❌ {stock['name']} 【{vcp_status_final}】"
                        
                        # 🚀 推算報酬率
                        if idx_future in s_series_raw_all.index:
                            price_future = s_series_raw_all.loc[idx_future]
                            future_return = ((price_future / p_now) - 1) * 100
                        else:
                            available_future_dates = s_series_raw_all.index[s_series_raw_all.index >= idx_future]
                            if not available_future_dates.empty:
                                price_future = s_series_raw_all.loc[available_future_dates[0]]
                                future_return = ((price_future / p_now) - 1) * 100
                            else:
                                future_return = 0.0

                        perf_col_key = f"後續{holding_days}日實際報酬(%)"

                        # 🆕 新增：帶入 API 抓取的處置資訊
                        code_only = ticker.split(".")[0]
                        disp_info = DISPOSITION_STOCKS.get(code_only, "")

                        integrated_results.append({
                            "股票代號": code_only, 
                            "股票名稱": display_name,
                            "原始名稱": stock['name'],
                            "趨勢模板": "✅" if is_trend_template else "❌",
                            "動能狀態判定": vcp_status_final,
                            "50MA乖離率(%)": bias_50,
                            "處置資訊": disp_info, # 🚀 儲存處置狀態與期間
                            "IBD式 絕對分數": ibd, "對比 0050 超額強度": ibd - benchmark_ibd_score,
                            "短線抗跌韌性分數": resilience, "逆風勝率": f"{outperform} / {total_panic_days} 天",
                            "逆風上漲天數": f"{np.sum(s_ret.reindex(panic_dates_list) > 0)} 天",
                            perf_col_key: future_return
                        })
                    
                    df_final = pd.DataFrame(integrated_results).sort_values("對比 0050 超額強度", ascending=False)
                    
                    cols = df_final.columns.tolist()
                    perf_col_name = f"後續{holding_days}日實際報酬(%)"
                    
                    if "50MA乖離率(%)" in cols:
                        cols.remove("50MA乖離率(%)")
                        cols.append("50MA乖離率(%)")
                    if perf_col_name in cols:
                        cols.remove(perf_col_name)
                        if is_backtesting:
                            cols.insert(2, perf_col_name)
                        else:
                            cols.append(perf_col_name)
                    df_final = df_final[cols]
                    
                    st.subheader(f"📊 雙軌數據交叉比對表 (基準日大盤恐慌日：{total_panic_days} 天)")
                    
                    if is_backtesting:
                        st.warning(f"🕒 目前處於【回溯歷史選股模式】。基準日：{backtest_date.strftime('%Y-%m-%d')}。已為您追蹤其後 {actual_holding_text} 的精準實質報酬。")
                    else:
                        st.info(f"💡 照妖鏡判定：{level_desc}。抗跌合格線：`{dynamic_threshold}%`")
                    
                    with st.expander("🔍 符號意義與馬克趨勢模板 (Trend Template) 說明", expanded=False):
                        st.markdown("""
                        * ✅ 符合標記：代表該股目前完全符合馬克·米奈爾維尼（Mark Minervini）的 7 大趨勢模板核心條件，正處於健康的第二階段（Stage 2）上升趨勢。
                        * ❌ 未符標記：代表該股目前未全數滿足 7 項技術面排列準則。
                        
                        🌀 VCP / 動能狀態動態標籤說明：
                        * 🌟 雙軌領先：個股股價尚未突破30日新高，但相對強度 (Alpha RS 曲線) 已率先刷新30日紀錄，暗示機構暗中強勢吃貨，極具爆發力。
                        * ⚠️ 雙軌背離：股價已創30日新高，但相對強度未同步創高，短線動能呈現隱形落後，需警惕高檔假突破。
                        * 💤 價格波動沉寂(Dead Quiet)：成交量縮至 20 日均值 70% 以下，且 5日價格變異係數收縮，代表波幅極限窄化，即將噴發大行情。
                        * 💎 極致壓縮(80%+CV)：5日價格變異係數收縮至20日均值的 80% 以下，籌碼極度洗淨，多空面臨臨界點。
                        * 🔥 相對壓縮(90%+CV)：5日價格變異係數收縮至20日均值的 90% 以下，進入標準 VCP 波幅收緊軌道。
                        * 📈 動能回復中：短線相對強度曲線扭轉下行趨勢、連續 3 日走揚。
                        * ⏳ 區間整理：股價與動能處於正常箱型、橫盤 or 洗盤沉澱階段，未出現極端信號。
                        """)
                    
                    if skipped_stocks:
                        st.warning(f"⚠️ 以下輸入內容格式正確，但 yfinance 查無交易歷史數據（可能剛上市或打錯）：{', '.join(skipped_stocks)}")
                    
                    column_config_dict = {
                        "50MA乖離率(%)": st.column_config.NumberColumn("50MA乖離率", format="%.2f%%"),
                        "IBD式 絕對分數": st.column_config.NumberColumn("IBD式 絕對強度", format="%.1f"),
                        "短線抗跌韌性分數": st.column_config.ProgressColumn("抗跌得分", min_value=0, max_value=100, format="%.0f分")
                    }
                    if is_backtesting:
                        column_config_dict[perf_col_name] = st.column_config.NumberColumn(f"🎯 後續{holding_days}日報酬", format="%.2f%%")
                    else:
                        column_config_dict[perf_col_name] = st.column_config.NumberColumn("今日至今持平率", format="%.2f%%")
                        
                    # 💡 UI 隱藏原始名稱與輔助欄位，保持表格乾淨
                    display_df = df_final.drop(columns=["原始名稱", "趨勢模板", "動能狀態判定", "處置資訊"], errors="ignore")
                    st.dataframe(display_df, use_container_width=True, hide_index=True, column_config=column_config_dict)
                    
                    st.divider()
                    st.subheader("🏁 Mark Minervini 流派：雙軌交叉戰略部署")
                    st.caption(f"💡 註：括號內為 50MA 乖離率(%)。右側標註為【後續 {holding_days} 日回測實際報酬率】。")
                    true_leaders = df_final[(df_final["對比 0050 超額強度"] > 0) & (df_final["短線抗跌韌性分數"] >= dynamic_threshold)]
                    momentum_only = df_final[(df_final["對比 0050 超額強度"] > 0) & (df_final["短線抗跌韌性分數"] < dynamic_threshold)]
                    defensive_only = df_final[(df_final["對比 0050 超額強度"] <= 0) & (df_final["短線抗跌韌性分數"] >= dynamic_threshold)]
                    laggards = df_final[(df_final["對比 0050 超額強度"] <= 0) & (df_final["短線抗跌韌性分數"] < dynamic_threshold)]
                    
                    def format_stocks(df, show_perf=False):
                        if df.empty: return "無"
                        lines = []
                        for _, row in df.iterrows():
                            perf_str = f" ➡️ 後續報酬: {row[perf_col_name]:.1f}%" if show_perf else ""
                            bias_val = row['50MA乖離率(%)']
                            
                            # 🚀 提取並組合處置期間字串
                            disp_info = row.get("處置資訊", "")
                            disp_str = f" <span style='color: #ff9900; font-weight: bold;'>[🔒處置期間: {disp_info}]</span>" if disp_info else ""
                            
                            bias_str = f"<span style='background-color: #ffcccc; color: #990000; padding: 2px 4px; border-radius: 4px; font-weight: bold;'>{bias_val:.1f}%</span>" if bias_val >= 30.0 else f"{bias_val:.1f}%"
                            formatted_name = f"{row['趨勢模板']} {row['原始名稱']} 【{row['動能狀態判定']}】"
                            
                            # 🚀 完美安插在 50MA 乖離率括號內後方
                            lines.append(f"* {formatted_name} ({bias_str}{disp_str}){perf_str}")
                        return "\n".join(lines)

                    c1, c2 = st.columns(2)
                    c1.success(f"### 👑 第一象限：逆風真龍頭 ({len(true_leaders)} 檔)"); c1.markdown(format_stocks(true_leaders, is_backtesting), unsafe_allow_html=True)
                    c1.info(f"### 🚀 第二象限：高 Beta 攻擊兵 ({len(momentum_only)} 檔)"); c1.markdown(format_stocks(momentum_only, is_backtesting), unsafe_allow_html=True)
                    c2.warning(f"### 🛡️ 第三象限：資金避風港 ({len(defensive_only)} 檔)"); c2.markdown(format_stocks(defensive_only, is_backtesting), unsafe_allow_html=True)
                    c2.error(f"### 🚨 第四象限：無情剔除名單 ({len(laggards)} 檔)"); c2.markdown(format_stocks(laggards, is_backtesting), unsafe_allow_html=True)
                    
        except Exception as e:
            st.error(f"數據錯誤: {e}")
