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

# --- 🎯 網頁標題與馬克心法區塊 ---
st.title("🏆 SEPA 核心持股 - 雙軌相對強度 (RS) 決策終端機")

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
本系統完美融合 正宗 IBD 長線動能指標 與 短線逆風防守照妖鏡：
* 📈 長線動能：採用經典 Pine Script 權重公式 (`3M*2 + 6M + 9M + 12M`)，並以 元大台灣50 (0050) 為比較基準。
* 🔍 短線抗跌：系統將根據大盤回檔天數，動態計算抗跌合格門檻，完美避開極短線的分母效應。
""")

# --- ⚙️ 側邊欄控制面板 ---
with st.sidebar.form("sepa_integrated_form"):
    st.header("⚙️ 雙軌指標參數設定")
    
    default_pool = (
        "2337.TW,旺宏\n3406.TW,玉晶光\n3550.TW,聯穎\n6187.TWO,萬潤\n3037.TW,欣興\n3017.TW,奇鋐\n"
        "8086.TWO,宏捷科\n4749.TWO,新應材\n3680.TWO,家登\n8021.TW,尖點\n3481.TW,群創\n"
        "8438.TW,昶昕\n3691.TWO,碩禾\n6234.TWO,高僑\n8147.TWO,正淩\n5284.TW,JPP-KY\n"
        "2493.TW,揚博\n3023.TW,信邦\n6672.TW,騰輝電子\n6640.TWO,均華\n6134.TWO,萬旭\n3305.TW,昇貿"
    )
    stock_input = st.text_area("股票清單 (支援複製貼上！系統會自動過濾國籍、財報等非代號雜訊)", value=default_pool, height=300)
    
    st.subheader("【短線逆風照妖鏡參數】")
    lookback_days = st.number_input("自訂照妖鏡觀察天數", min_value=5, max_value=365, value=60, step=1)
    market_threshold = st.slider("大盤恐慌日定義 (單日跌幅 %)", min_value=0.5, max_value=2.5, value=1.0, step=0.1)
    
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
    
    end_date = datetime.today()
    start_date_long = end_date - timedelta(days=550) 
    start_date_short = end_date - timedelta(days=int(lookback_days))
    
    with st.spinner("量化引擎計算中... 正在進行一鍵式批次下載與時間軸同步校正..."):
        try:
            if not STOCKS_POOL:
                st.error("❌ 過濾雜訊後，未偵測到任何有效的股票代號，請重新輸入。")
            else:
                all_tickers = ["0050.TW"] + [stock["id"] for stock in STOCKS_POOL]
                df_all = yf.download(all_tickers, start=start_date_long, end=end_date, progress=False, auto_adjust=False)
                
                df_adj = df_all['Adj Close'] if 'Adj Close' in df_all.columns.levels[0] else df_all['Close']
                b_c = df_adj["0050.TW"].dropna()
                
                # 大盤基準線
                idx_now, idx_3m, idx_6m, idx_9m, idx_1y = b_c.index[-1], b_c.index[-63], b_c.index[-126], b_c.index[-189], b_c.index[-252]
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
                    
                    # --- 新增：計算 50MA 與 乖離率 ---
                    valid_s = s_series.dropna()
                    if len(valid_s) >= 50:
                        ma50_val = valid_s.rolling(window=50).mean().iloc[-1]
                        price_now = valid_s.iloc[-1]
                        bias_50 = ((price_now - ma50_val) / ma50_val) * 100
                    else:
                        bias_50 = 0.0 # 避免新股資料不足報錯
                    
                    integrated_results.append({
                        "股票代號": ticker.split(".")[0], "股票名稱": stock["name"],
                        "50MA乖離率(%)": bias_50,
                        "正宗 IBD 絕對分數": ibd, "對比 0050 超額強度": ibd - benchmark_ibd_score,
                        "短線抗跌韌性分數": resilience, "逆風勝率": f"{outperform} / {total_panic_days} 天",
                        "逆風上漲天數": f"{np.sum(s_ret.reindex(panic_dates_list) > 0)} 天"
                    })
                
                # --- 修改：以「50MA乖離率」由低到高排序 ---
                df_final = pd.DataFrame(integrated_results).sort_values("50MA乖離率(%)", ascending=True)
                
                # 🛠️ 核心改動：調整欄位順序，把「50MA乖離率(%)」放到最後面
                cols = df_final.columns.tolist()
                if "50MA乖離率(%)" in cols:
                    cols.remove("50MA乖離率(%)")
                    cols.append("50MA乖離率(%)")
                df_final = df_final[cols]
                
                st.subheader(f"📊 雙軌數據交叉比對表 (大盤恐慌日：{total_panic_days} 天)")
                st.info(f"💡 照妖鏡判定：{level_desc}。抗跌合格線：`{dynamic_threshold}%`")
                
                if skipped_stocks:
                    st.warning(f"⚠️ 以下輸入內容格式正確，但 yfinance 查無交易歷史數據（可能剛上市或打錯）：{', '.join(skipped_stocks)}")
                
                # --- 新增：將 50MA乖離率 顯示在主表格中 ---
                st.dataframe(df_final, use_container_width=True, hide_index=True, column_config={
                    "50MA乖離率(%)": st.column_config.NumberColumn("50MA乖離率", format="%.2f%%"),
                    "正宗 IBD 絕對分數": st.column_config.NumberColumn("IBD 絕對強度", format="%.1f"),
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
                
                # --- 新增：自訂輸出格式函式，將股票名稱與 50MA乖離率 綁定在一起 ---
                def format_stocks(df):
                    if df.empty:
                        return "無"
                    return ', '.join([f"{row['股票名稱']} ({row['50MA乖離率(%)']:.1f}%)" for _, row in df.iterrows()])

                c1, c2 = st.columns(2)
                c1.success(f"### 👑 第一象限：逆風真龍頭 ({len(true_leaders)} 檔)"); c1.write(format_stocks(true_leaders)); c1.caption("👉 戰略部署：長線動能擊敗大盤，且短線抗跌表現達到當前動態合格線以上。隨時注意 VCP 出量突破。")
                c1.info(f"### 🚀 第二象限：高 Beta 攻擊兵 ({len(momentum_only)} 檔)"); c1.write(format_stocks(momentum_only)); c1.caption("👉 戰略部署：長線極強，但修正波動高於大盤。一旦大盤止穩，這群股票往往是右側出量追擊的首選。")
                c2.warning(f"### 🛡️ 第三象限：資金避風港 ({len(defensive_only)} 檔)"); c2.write(format_stocks(defensive_only)); c2.caption("👉 戰略部署：短線極度抗跌，長線動能尚未完全追上。若有打底完成標的，高抗跌意味主力在低檔死守，值得關注！")
                c2.error(f"### 🚨 第四象限：無情剔除名單 ({len(laggards)} 檔)"); c2.write(format_stocks(laggards)); c2.caption("👉 戰略部署：長短線皆跑輸大盤，在馬克系統中完全沒有留戀價值，應盡快抽回資金。")
                
        except Exception as e:
            st.error(f"數據錯誤: {e}")
