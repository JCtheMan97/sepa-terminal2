import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import os
import re

# 1. 網頁初始設定
st.set_page_config(page_title="🏆 SEPA 雙軌強勢股終端機", layout="wide")

# ══════════════════════════════════════════════
# 【新增 A】歷史追蹤：Session 容器初始化（只在第一次載入時執行）
# ══════════════════════════════════════════════
if "scan_history" not in st.session_state:
    st.session_state.scan_history = []   # list of dict，每次掃描存一個快照

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
            st.sidebar.caption(f"📊 核心引擎：台股標的資料庫已就緒 (已同步 {len(stock_dict):,} 檔成分股)")
        except Exception as e:
            st.sidebar.error(f"系統資料庫讀取失敗: {e}")
    return stock_dict

STOCK_DICT = load_stock_dict()

# --- 🎯 快取下載與運算引擎 ---
@st.cache_data(ttl=3600)
def fetch_and_sync_data(tickers, start_date, end_date):
    df_all = yf.download(tickers, start=start_date, end=end_date, progress=False, auto_adjust=False)
    return df_all

# --- 🎯 網頁標題與馬克心法區塊 ---
st.title("🏆 SEPA 技術面篩選模組 - 雙軌相對強度 (RS) 決策終端機")

st.info("🔥 「逆風不倒的韌性，就是下一波超級飆股的邀請函。」—— 馬克·米奈爾維尼 (Mark Minervini)")

with st.expander("📖 閱讀 SEPA 系統核心心法 (Trade Like a Stock Market Wizard)", expanded=True):
    st.markdown("""
    大盤修正（Market Correction）或熊市，正是篩選「下一波超級飆股（Next Superperformers）」的黃金時間。當平庸的投資人因恐慌而遠離市場時，我們必須密切緊盯那些「抗跌並拒絕下跌」的個股，因為這正代表了機構法人正在瘋狂暗中吃貨。

    🎯 真正能創造數倍暴利的市場領導股（Market Leaders），通常具有以下三個特質：
    1. 在大盤中度修正時，它們跌得最少（甚至逆勢橫盤或創高）。
    2. 在大盤觸底時，它們是最先拔地而起、率先突破的個股。
    3. 大盤的跌勢，是在幫 these 強勢股清洗浮額（Weak hands），並讓其完美的 VCP（波動率收縮型態） 成型。
    """)

st.markdown("""
---
本系統完美融合 IBD式 長線動能指標 與 短線逆風防守照妖鏡：
* 📈 長線動能：採用經典 Pine Script 權重公式 (`3M*2 + 6M + 9M + 12M`)，並以 元大台灣50 (0050) 為比較基準。
* 🔍 短線抗跌：系統將根據大盤回檔天數，動態計算抗跌合格門檻，完美避開極短線的分母效應。
""")

# --- ⚙️ 側邊欄控制面板 ---
with st.sidebar.form("sepa_integrated_form"):
    st.header("⚙️ 雙軌指標參數設定")
    
    default_pool = (
        "2337.TW,旺宏\n3406.TW,玉晶光\n3550.TW,聯穎\n6187.TWO,萬潤\n3037.TW,欣興\n3017.TW,奇鋐\n"
        "8086.TWO,宏捷科\n4749.TWO,新應材\n3680.TWO,家登\n8021.TW,尖點\n3481.TW,群創\n"
        "8438.TW,昶昕\n3691.TWO,碩禾\n2423.TW,固緯\n8147.TWO,正淩\n5284.TW,JPP-KY\n"
        "2493.TW,揚博\n3023.TW,信邦\n6672.TW,騰輝電子\n3044.TW,健鼎\n6134.TWO,萬旭\n2413.TW,環科\n3577.TWO,泓格\n3305.TW,昇貿\n2428.TW,興勤\n6716.TWO,應廣"
    )
    stock_input = st.text_area("股票清單 (支援複製貼上！系統會自動過濾國籍、財報等非代號雜訊)", value=default_pool, height=300)
    
    st.subheader("【短線逆風照妖鏡參數】")
    lookback_days = st.number_input("自訂照妖鏡觀察天數", min_value=5, max_value=365, value=60, step=1)
    market_threshold = st.slider("大盤恐慌日定義 (單日跌幅 %)", min_value=0.5, max_value=2.5, value=1.0, step=0.1)
    
    submit_btn = st.form_submit_button("🚀 執行雙軌交叉選股分析")

def get_stocks_pool(text):
    pool = []
    for line in text.split('\n'):
        line = line.strip()
        if not line: continue
        code_match = re.search(r'\b\d{4,6}\b', line)
        if code_match:
            code = code_match.group()
            found = False
            for suffix in ["", ".TW", ".TWO"]:
                target = f"{code}{suffix}" if suffix else code
                if target in STOCK_DICT:
                    pool.append({"id": target, "name": STOCK_DICT[target]})
                    found = True
                    break
            if found: continue
        found_name = False
        for code, official_name in STOCK_DICT.items():
            if line in official_name or official_name in line:
                pool.append({"id": code, "name": official_name})
                found_name = True
                break
        if not found_name:
            st.sidebar.warning(f"⚠️ 找不到此標的: {line}")
    return list({item['id']: item for item in pool}.values())

if 'first_run' not in st.session_state:
    st.session_state.first_run = True

if submit_btn or st.session_state.first_run:
    STOCKS_POOL = get_stocks_pool(stock_input)
    st.session_state.first_run = False
    
    end_date = datetime.today()
    start_date_long = end_date - timedelta(days=550) 
    start_date_short = end_date - timedelta(days=int(lookback_days))
    
    with st.spinner("量化引擎計算中... 正在進行一鍵式批次下載與時間軸同步校正..."):
        try:
            if not STOCKS_POOL:
                st.error("❌ 過濾雜訊後，未偵測到任何有效的股票代號，請重新輸入。")
            else:
                all_tickers = ["0050.TW"] + [stock["id"] for stock in STOCKS_POOL]
                
                df_all = fetch_and_sync_data(tuple(all_tickers), start_date_long.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                
                df_adj = df_all['Adj Close'] if 'Adj Close' in df_all.columns.levels[0] else df_all['Close']
                b_c = df_adj["0050.TW"].dropna()
                
                idx_now, idx_3m, idx_6m, idx_9m, idx_1y = b_c.index[-1], b_c.index[-63], b_c.index[-126], b_c.index[-189], b_c.index[-252]
                b_now, b_3m, b_6m, b_9m, b_1y = b_c.loc[idx_now], b_c.loc[idx_3m], b_c.loc[idx_6m], b_c.loc[idx_9m], b_c.loc[idx_1y]
                benchmark_ibd_score = ((b_now/b_3m*2) + (b_now/b_6m) + (b_now/b_9m) + (b_now/b_1y)) / 5 * 100
                
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
                    
                    s_series = df_adj[ticker].reindex(b_c.index)
                    
                    if s_series.dropna().empty:
                        skipped_stocks.append(stock["name"])
                        continue
                    
                    def get_v(s, idx): 
                        valid = s.dropna()
                        return valid.loc[valid.index[np.argmin(np.abs(valid.index - idx))]]
                    
                    s_n, s_3, s_6, s_9, s_1 = get_v(s_series, idx_now), get_v(s_series, idx_3m), get_v(s_series, idx_6m), get_v(s_series, idx_9m), get_v(s_series, idx_1y)
                    ibd = ((s_n/s_3*2) + (s_n/s_6) + (s_n/s_9) + (s_n/s_1)) / 5 * 100
                    
                    s_ret = s_series.pct_change() * 100
                    outperform = np.sum(s_ret.reindex(panic_dates_list) > b_short_df.loc[panic_dates_list, 'Market_Return'])
                    resilience = (outperform / total_panic_days * 100) if total_panic_days > 0 else 100
                    
                    valid_s = s_series.dropna()
                    if len(valid_s) >= 50:
                        ma50_val = valid_s.rolling(window=50).mean().iloc[-1]
                        price_now = valid_s.iloc[-1]
                        bias_50 = ((price_now - ma50_val) / ma50_val) * 100
                    else:
                        bias_50 = 0.0
                    
                    if len(valid_s) >= 200:
                        sma50_s = valid_s.rolling(50).mean()
                        sma150_s = valid_s.rolling(150).mean()
                        sma200_s = valid_s.rolling(200).mean()
                        
                        p_now = valid_s.iloc[-1]
                        m50 = sma50_s.iloc[-1]
                        m150 = sma150_s.iloc[-1]
                        m200 = sma200_s.iloc[-1]
                        m200_22 = sma200_s.shift(22).iloc[-1] if len(sma200_s) > 22 else np.nan
                        
                        h252 = valid_s.rolling(252, min_periods=1).max().iloc[-1]
                        l252 = valid_s.rolling(252, min_periods=1).min().iloc[-1]
                        
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
                        p_now = valid_s.iloc[-1] if not valid_s.empty else np.nan

                    is_price_new_high = False
                    is_alpha_new_high = False
                    is_alpha_lagging = False
                    is_vcp_80 = False
                    is_vcp_90 = False
                    is_rs_recovering = False
                    
                    if len(valid_s) >= 30:
                        same_idx_b = b_c.reindex(valid_s.index).ffill()
                        rel_close = valid_s / same_idx_b
                        
                        is_price_new_high = p_now >= valid_s.iloc[-31:-1].max()
                        is_alpha_new_high = rel_close.iloc[-1] >= rel_close.iloc[-31:-1].max()
                        is_alpha_lagging = rel_close.iloc[-1] < rel_close.iloc[-31:-1].max()
                        
                        if len(rel_close) >= 3:
                            is_rs_recovering = rel_close.iloc[-1] > rel_close.iloc[-2] and rel_close.iloc[-2] > rel_close.iloc[-3]
                        
                        roll_std5 = valid_s.rolling(5).std()
                        roll_mean5 = valid_s.rolling(5).mean()
                        cv_5 = roll_std5 / roll_mean5
                        if len(cv_5) >= 20:
                            cv_5_ma20 = cv_5.rolling(20).mean()
                            cv_5_now = cv_5.iloc[-1]
                            cv_5_ma20_now = cv_5_ma20.iloc[-1]
                            is_vcp_80 = cv_5_now < cv_5_ma20_now * 0.80
                            is_vcp_90 = cv_5_now < cv_5_ma20_now * 0.90
                    
                    is_rs_leading = (not is_price_new_high) and is_alpha_new_high
                    is_div_warning = is_price_new_high and is_alpha_lagging
                    
                    if is_vcp_80:
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
                    
                    display_name = f"✅ {stock['name']} 【{vcp_status_final}】" if is_trend_template else f"❌ {stock['name']} 【{vcp_status_final}】"
                    
                    integrated_results.append({
                        "股票代號": ticker.split(".")[0], "股票名稱": display_name,
                        "50MA乖離率(%)": bias_50,
                        "IBD式 絕對分數": ibd, "對比 0050 超額強度": ibd - benchmark_ibd_score,
                        "短線抗跌韌性分數": resilience, "逆風勝率": f"{outperform} / {total_panic_days} 天",
                        "逆風上漲天數": f"{np.sum(s_ret.reindex(panic_dates_list) > 0)} 天",
                        # 【新增 B-1】存入原始股票名稱（不含 emoji），供歷史追蹤用
                        "_name_raw": stock['name'],
                        "_is_q1": False,  # 先給預設值，四象限分完後再回填
                    })
                
                df_final = pd.DataFrame(integrated_results).sort_values("對比 0050 超額強度", ascending=False)
                
                cols = df_final.columns.tolist()
                if "50MA乖離率(%)" in cols:
                    cols.remove("50MA乖離率(%)")
                    cols.append("50MA乖離率(%)")
                df_final = df_final[cols]
                
                st.subheader(f"📊 雙軌數據交叉比對表 (大盤恐慌日：{total_panic_days} 天)")
                st.info(f"💡 照妖鏡判定：{level_desc}。抗跌合格線：`{dynamic_threshold}%`")
                
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
                
                # 顯示欄位順序：把 _name_raw / _is_q1 這兩個內部欄位排除在顯示之外
                display_cols = [c for c in df_final.columns if not c.startswith("_")]
                st.dataframe(df_final[display_cols], use_container_width=True, hide_index=True, column_config={
                    "50MA乖離率(%)": st.column_config.NumberColumn("50MA乖離率", format="%.2f%%"),
                    "IBD式 絕對分數": st.column_config.NumberColumn("IBD式 絕對強度", format="%.1f"),
                    "短線抗跌韌性分數": st.column_config.ProgressColumn("抗跌得分", min_value=0, max_value=100, format="%.0f分")
                })
                
                # 四象限戰略部署
                st.divider()
                st.subheader("🏁 Mark Minervini 流派：雙軌交叉戰略部署")
                st.caption("💡 註：括號內為 50MA 乖離率(%)。馬克心法：『不追高乖離，控好風險報酬比，專注基底與樞紐點突破。』")
                true_leaders = df_final[(df_final["對比 0050 超額強度"] > 0) & (df_final["短線抗跌韌性分數"] >= dynamic_threshold)]
                momentum_only = df_final[(df_final["對比 0050 超額強度"] > 0) & (df_final["短線抗跌韌性分數"] < dynamic_threshold)]
                defensive_only = df_final[(df_final["對比 0050 超額強度"] <= 0) & (df_final["短線抗跌韌性分數"] >= dynamic_threshold)]
                laggards = df_final[(df_final["對比 0050 超額強度"] <= 0) & (df_final["短線抗跌韌性分數"] < dynamic_threshold)]
                
                def format_stocks(df):
                    if df.empty:
                        return "無"
                    return "\n".join([f"* {row['股票名稱']} `({row['50MA乖離率(%)']:.1f}%)`" for _, row in df.iterrows()])

                c1, c2 = st.columns(2)
                c1.success(f"### 👑 第一象限：逆風真龍頭 ({len(true_leaders)} 檔)"); c1.write(format_stocks(true_leaders)); c1.caption("👉 戰略部署：長線動能擊敗大盤，且短線抗跌表現達到當前動態合格線以上。隨時注意 VCP 出量突破。")
                c1.info(f"### 🚀 第二象限：高 Beta 攻擊兵 ({len(momentum_only)} 檔)"); c1.write(format_stocks(momentum_only)); c1.caption("👉 戰略部署：長線極強，但修正波動高於大盤. 一旦大盤止穩，這群股票往往是右側出量追擊的首選。")
                c2.warning(f"### 🛡️ 第三象限：資金避風港 ({len(defensive_only)} 檔)"); c2.write(format_stocks(defensive_only)); c2.caption("👉 戰略部署：短線極度抗跌，長線動能尚未完全追上。若有打底完成標的，高抗跌意味主力在低檔死守，值得關注！")
                c2.error(f"### 🚨 第四象限：無情剔除名單 ({len(laggards)} 檔)"); c2.write(format_stocks(laggards)); c2.caption("👉 戰略部署：長短線皆跑輸大盤，在馬克系統中屬於弱勢標的，建議審慎評估資金配置與汰弱留強。")

                # ══════════════════════════════════════════════
                # 【新增 B】歷史追蹤：存入本次掃描快照
                # ══════════════════════════════════════════════
                snapshot = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "params": {
                        "lookback": lookback_days,
                        "threshold": market_threshold,
                        "panic_days": total_panic_days,
                        "dynamic_threshold": dynamic_threshold,
                    },
                    # 各象限：只存乾淨的股票名稱（不含 emoji），方便後續比對
                    "q1": set(true_leaders["_name_raw"].tolist()),
                    "q2": set(momentum_only["_name_raw"].tolist()),
                    "q3": set(defensive_only["_name_raw"].tolist()),
                    "q4": set(laggards["_name_raw"].tolist()),
                    # 精簡版數據表，供歷史對比用
                    "df": df_final[["股票代號", "_name_raw", "對比 0050 超額強度", "短線抗跌韌性分數", "50MA乖離率(%)"]].copy().rename(columns={"_name_raw": "股票名稱"}),
                }
                st.session_state.scan_history.append(snapshot)

                # 只保留最近 10 次，防止記憶體過大
                if len(st.session_state.scan_history) > 10:
                    st.session_state.scan_history.pop(0)

                # ══════════════════════════════════════════════
                # 【新增 C】歷史追蹤：對比 UI（在四象限下方展開）
                # ══════════════════════════════════════════════
                st.divider()
                st.subheader("🕰️ 歷史掃描紀錄對比")

                if len(st.session_state.scan_history) <= 1:
                    st.caption("✅ 本次掃描已儲存。再次執行掃描後，即可在此對比不同時間點的四象限變化（最多保留 10 次）。")
                else:
                    history_labels = [h["timestamp"] for h in st.session_state.scan_history]

                    hcol1, hcol2 = st.columns(2)
                    # 預設：最舊 vs 最新，讓使用者一眼看到變化
                    sel_a = hcol1.selectbox("🔵 基準時間點（較早）", history_labels, index=0, key="hist_a")
                    sel_b = hcol2.selectbox("🟠 比較時間點（較晚）", history_labels, index=len(history_labels) - 1, key="hist_b")

                    snap_a = next(h for h in st.session_state.scan_history if h["timestamp"] == sel_a)
                    snap_b = next(h for h in st.session_state.scan_history if h["timestamp"] == sel_b)

                    # ── 第一象限變動分析 ──
                    still_king  = snap_a["q1"] & snap_b["q1"]                          # 兩次都在 Q1
                    promoted    = snap_b["q1"] - snap_a["q1"]                           # 新晉 Q1
                    demoted     = snap_a["q1"] - snap_b["q1"]                           # 跌出 Q1
                    risen_to_q1 = snap_b["q1"] & (snap_a["q2"] | snap_a["q3"] | snap_a["q4"])  # 從其他象限升至 Q1

                    st.markdown(f"##### 👑 第一象限（逆風真龍頭）變動分析：`{sel_a}` → `{sel_b}`")
                    kc1, kc2, kc3 = st.columns(3)

                    def _fmt(names):
                        return "\n".join(f"· {n}" for n in sorted(names)) if names else "（無）"

                    kc1.success(f"**持續領頭 ({len(still_king)})**\n\n{_fmt(still_king)}")
                    kc2.info(f"**🚀 新晉真龍頭 ({len(promoted)})**\n\n{_fmt(promoted)}")
                    kc3.error(f"**📉 跌出真龍頭 ({len(demoted)})**\n\n{_fmt(demoted)}")

                    # ── 全象限流向總覽（可展開）──
                    with st.expander("🔄 查看全象限流向總覽", expanded=False):
                        # Q2、Q3、Q4 升至 Q1
                        st.markdown("**從其他象限晉升到第一象限的標的：**")
                        st.write(_fmt(risen_to_q1) if risen_to_q1 else "無")

                        st.markdown("---")
                        # 各象限自身的新增與離開
                        for qkey, qname in [("q2","🚀 第二象限"), ("q3","🛡️ 第三象限"), ("q4","🚨 第四象限")]:
                            added   = snap_b[qkey] - snap_a[qkey]
                            removed = snap_a[qkey] - snap_b[qkey]
                            st.markdown(f"**{qname}** ── 新增：{_fmt(added) if added else '無'} ／ 離開：{_fmt(removed) if removed else '無'}")

                    # ── 完整數值對比表（可展開）──
                    with st.expander("📊 完整數值前後對比表", expanded=False):
                        df_a = snap_a["df"].rename(columns={
                            "對比 0050 超額強度": f"超額強度【{sel_a}】",
                            "短線抗跌韌性分數":   f"抗跌分數【{sel_a}】",
                            "50MA乖離率(%)":      f"50MA乖離【{sel_a}】",
                        })
                        df_b = snap_b["df"].rename(columns={
                            "對比 0050 超額強度": f"超額強度【{sel_b}】",
                            "短線抗跌韌性分數":   f"抗跌分數【{sel_b}】",
                            "50MA乖離率(%)":      f"50MA乖離【{sel_b}】",
                        })
                        df_compare = df_a.merge(df_b, on=["股票代號", "股票名稱"], how="outer")

                        # 計算超額強度變化量，方便一眼看趨勢
                        col_a_rs = f"超額強度【{sel_a}】"
                        col_b_rs = f"超額強度【{sel_b}】"
                        if col_a_rs in df_compare.columns and col_b_rs in df_compare.columns:
                            df_compare["超額強度變化 ▲▼"] = (df_compare[col_b_rs] - df_compare[col_a_rs]).round(2)

                        st.dataframe(df_compare, use_container_width=True, hide_index=True)

                    # ── 掃描參數摘要 ──
                    with st.expander("⚙️ 兩次掃描參數對照", expanded=False):
                        param_df = pd.DataFrame([
                            {"項目": "觀察天數",     sel_a: snap_a["params"]["lookback"],          sel_b: snap_b["params"]["lookback"]},
                            {"項目": "恐慌日門檻(%)", sel_a: snap_a["params"]["threshold"],         sel_b: snap_b["params"]["threshold"]},
                            {"項目": "大盤恐慌日數",  sel_a: snap_a["params"]["panic_days"],        sel_b: snap_b["params"]["panic_days"]},
                            {"項目": "抗跌合格線(%)", sel_a: snap_a["params"]["dynamic_threshold"], sel_b: snap_b["params"]["dynamic_threshold"]},
                        ])
                        st.dataframe(param_df, use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"數據錯誤: {e}")
