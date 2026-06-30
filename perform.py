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
st.title("🏆 SEPA 技術面篩選模組 - 多軌照妖鏡新標的決策終端機")

# 🌟 馬克·米奈爾維尼 核心格言
st.info("🔥 「逆風不倒的韌性，就是下一波超級飆股的邀請函。」—— 馬克·米奈爾維尼 (Mark Minervini)")

# --- ⚙️ 側邊欄控制面板 ---
with st.sidebar.form("sepa_integrated_form"):
    st.header("⚙️ 雙軌指標參數設定")
    
    default_pool = (
        "2337.TW,旺宏\n3406.TW,玉晶光\n3550.TW,聯穎\n6187.TWO,萬潤\n3037.TW,欣興\n3017.TW,奇鋐\n"
        "8086.TWO,宏捷科\n4749.TWO,新應材\n3680.TWO,家登\n8021.TW,尖點\n3481.TW,群創\n"
        "8438.TW,昶昕\n3691.TWO,碩禾\n2423.TW,固緯\n8147.TWO,正淩\n5284.TW,JPP-KY\n"
        "2493.TW,揚博\n3023.TW,信邦\n6672.TW,騰輝電子\n3044.TW,健鼎\n6134.TWO,萬旭\n2413.TW,環科\n3577.TWO,泓格\n3305.TW,昇貿"
    )
    stock_input = st.text_area("🎯 輸入待篩選池 (支援複製任何來源雜訊，系統會自動清洗)", value=default_pool, height=250)
    
    st.subheader("【多軌照妖鏡參數】")
    # 🌟 升級功能：改為讓使用者在前端自由輸入三個天數（預設為 20, 30, 45）
    track_days_input = st.text_input("自訂三個對比天數 (請用半形逗號隔開)", value="20, 30, 45")
    market_threshold = st.slider("大盤恐慌日定義 (單日跌幅 %)", min_value=0.5, max_value=2.5, value=1.0, step=0.1)
    
    submit_btn = st.form_submit_button("🚀 一鍵平行交叉篩選新標的")

def get_stocks_pool(text):
    """智能掃描器：自動比對輸入文字與 STOCK_DICT 名稱"""
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
    
    with st.spinner("多軌平行量化引擎運算中..."):
        try:
            if not STOCKS_POOL:
                st.error("❌ 未偵測到任何有效的股票代號，請重新輸入。")
            else:
                # 🌟 升級功能：動態解析使用者輸入的天數 (自動防錯與補足機制)
                try:
                    track_days = [int(x.strip()) for x in track_days_input.split(",") if x.strip().isdigit()][:3]
                    if len(track_days) < 3:
                        track_days += [20, 30, 45][len(track_days):]
                except Exception:
                    track_days = [20, 30, 45]
                
                all_tickers = ["0050.TW"] + [stock["id"] for stock in STOCKS_POOL]
                df_all = fetch_and_sync_data(tuple(all_tickers), start_date_long.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                
                df_adj = df_all['Adj Close'] if 'Adj Close' in df_all.columns.levels[0] else df_all['Close']
                b_c = df_adj["0050.TW"].dropna()
                
                # 長線 IBD 基準
                idx_now, idx_3m, idx_6m, idx_9m, idx_1y = b_c.index[-1], b_c.index[-63], b_c.index[-126], b_c.index[-189], b_c.index[-252]
                b_now, b_3m, b_6m, b_9m, b_1y = b_c.loc[idx_now], b_c.loc[idx_3m], b_c.loc[idx_6m], b_c.loc[idx_9m], b_c.loc[idx_1y]
                benchmark_ibd_score = ((b_now/b_3m*2) + (b_now/b_6m) + (b_now/b_9m) + (b_now/b_1y)) / 5 * 100
                
                # 🚀 核心升級：平行計算動態多軌大盤恐慌日與日期清單
                track_panic_info = {}
                
                for days in track_days:
                    start_short = end_date - timedelta(days=days)
                    b_short_df = pd.DataFrame(b_c.loc[start_short.strftime('%Y-%m-%d'):])
                    b_short_df.columns = ['Close_Price']
                    b_short_df['Market_Return'] = b_short_df['Close_Price'].pct_change() * 100
                    panic_days = b_short_df[b_short_df['Market_Return'] <= -market_threshold]
                    track_panic_info[days] = {
                        "total_panic": len(panic_days),
                        "dates": panic_days.index.tolist(),
                        "returns": b_short_df['Market_Return'],
                        "threshold": 55.0 if len(panic_days) <= 5 else (70.0 if len(panic_days) <= 15 else 80.0)
                    }
                
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
                    
                    # 🚀 核心升級：一鍵平行算出使用者自訂三軌之韌性分數
                    resilience_scores = {}
                    for days in track_days:
                        p_dates = track_panic_info[days]["dates"]
                        t_panic = track_panic_info[days]["total_panic"]
                        m_ret = track_panic_info[days]["returns"]
                        
                        if t_panic > 0:
                            outperform = np.sum(s_ret.reindex(p_dates) > m_ret.loc[p_dates])
                            resilience_scores[days] = (outperform / t_panic * 100)
                        else:
                            resilience_scores[days] = 100.0
                    
                    # 50MA 乖離率計算
                    valid_s = s_series.dropna()
                    if len(valid_s) >= 50:
                        ma50_val = valid_s.rolling(window=50).mean().iloc[-1]
                        price_now = valid_s.iloc[-1]
                        bias_50 = ((price_now - ma50_val) / ma50_val) * 100
                    else:
                        bias_50 = 0.0
                    
                    # 馬克 7 大趨勢模板
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

                    # VCP 緊縮指標量化計算
                    is_price_new_high, is_alpha_new_high, is_alpha_lagging = False, False, False
                    is_vcp_80, is_vcp_90, is_rs_recovering = False, False, False
                    
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
                            is_vcp_80 = cv_5.iloc[-1] < cv_5_ma20.iloc[-1] * 0.80
                            is_vcp_90 = cv_5.iloc[-1] < cv_5_ma20.iloc[-1] * 0.90
                    
                    struct_status = "💎 極致壓縮(80%+CV)" if is_vcp_80 else ("🔥 相對壓縮(90%+CV)" if is_vcp_90 else ("📈 動能回復中" if is_rs_recovering else "⏳ 區間整理"))
                    lead_prefix = "🌟 雙軌領先 | " if ((not is_price_new_high) and is_alpha_new_high) else ("⚠️ 雙軌背離 | " if (is_price_new_high and is_alpha_lagging) else "")
                    vcp_status_final = lead_prefix + struct_status
                    
                    display_name = f"✅ {stock['name']} 【{vcp_status_final}】" if is_trend_template else f"❌ {stock['name']} 【{vcp_status_final}】"
                    
                    # 🚀 多軌全紀錄：動態寫入字典
                    stock_res_data = {
                        "股票代號": ticker.split(".")[0], 
                        "股票名稱": display_name,
                        "對比 0050 超額強度": ibd - benchmark_ibd_score,
                        "IBD式 絕對分數": ibd, 
                        "50MA乖離率(%)": bias_50
                    }
                    # 動態拼裝自訂天數的抗跌分 key
                    for d in track_days:
                        stock_res_data[f"{d}日抗跌分"] = resilience_scores[d]
                        
                    integrated_results.append(stock_res_data)
                
                # 資料排序 (依據超額強度)
                df_final = pd.DataFrame(integrated_results).sort_values("對比 0050 超額強度", ascending=False)
                
                # --- 📊 輸出大表與多軌配置說明 ---
                st.subheader("📊 雙軌數據多軌平行交叉比對表")
                st.caption(f"💡 本表已同時平行運算短線三軌抗跌指標（大盤恐慌日：{track_days[0]}日={track_panic_info[track_days[0]]['total_panic']}天 | {track_days[1]}日={track_panic_info[track_days[1]]['total_panic']}天 | {track_days[2]}日={track_panic_info[track_days[2]]['total_panic']}天）")
                
                if skipped_stocks:
                    st.warning(f"⚠️ 以下輸入內容格式正確，但 yfinance 查無交易歷史數據：{', '.join(skipped_stocks)}")
                
                # 🌟 升級功能：主表格渲染設定 (ProgressColumn 採動態欄位指派)
                dynamic_config = {
                    "IBD式 絕對分數": st.column_config.NumberColumn("IBD絕對強度", format="%.1f"),
                    "對比 0050 超額強度": st.column_config.NumberColumn("超額動能", format="%.1f"),
                    "50MA乖離率(%)": st.column_config.NumberColumn("50MA乖離率", format="%.2f%%")
                }
                for d in track_days:
                    dynamic_config[f"{d}日抗跌分"] = st.column_config.ProgressColumn(f"{d}日抗跌分", min_value=0, max_value=100, format="%.0f分")
                
                st.dataframe(df_final, use_container_width=True, hide_index=True, column_config=dynamic_config)
                
                # 🏁 多軌交叉新標的戰略部署
                st.divider()
                st.subheader(f"🏁 篩選新標的專用：三軌全合格【真龍頭獵殺區】")
                st.caption(f"💡 篩選標準：長線動能大於大盤，且不論 {track_days[0]}/{track_days[1]}/{track_days[2]} 天的短線照妖鏡，抗跌分數皆達到動態防守門檻以上。")
                
                # 🌟 升級功能：定義動態三軌同時合格邏輯
                c1_passed = df_final[f"{track_days[0]}日抗跌分"] >= track_panic_info[track_days[0]]["threshold"]
                c2_passed = df_final[f"{track_days[1]}日抗跌分"] >= track_panic_info[track_days[1]]["threshold"]
                c3_passed = df_final[f"{track_days[2]}日抗跌分"] >= track_panic_info[track_days[2]]["threshold"]
                alpha_passed = df_final["對比 0050 超額強度"] > 0
                
                # 新標的分流
                all_pass_leaders = df_final[alpha_passed & c1_passed & c2_passed & c3_passed]
                vcp_incubating = all_pass_leaders[all_pass_leaders["股票名稱"].str.contains("💎|🔥")]
                
                # 🌟 升級功能：文字輸出也完全重構為動態 Key
                def format_stocks(df):
                    if df.empty: return "無"
                    return "\n".join([f"* {row['股票名稱']} `(乖離:{row['50MA乖離率(%)']:.1f}%)` [{track_days[0]}日:{row[f'{track_days[0]}日抗跌分']:.0f}分 | {track_days[1]}日:{row[f'{track_days[1]}日抗跌分']:.0f}分 | {track_days[2]}日:{row[f'{track_days[2]}日抗跌分']:.0f}分]" for _, row in df.iterrows()])

                col_l, col_r = st.columns(2)
                
                with col_l:
                    st.success(f"### 👑 三軌全合格：逆風真龍頭 ({len(all_pass_leaders)} 檔)")
                    st.write(format_stocks(all_pass_leaders))
                    st.caption("👉 部署策略：長線動能極強，且不論大盤短、中、長期回檔，都有機構死守。這是下一波行情發動時的戰略核心。")
                
                with col_r:
                    st.info(f"### 💎 黃金新標的：三軌合格 + VCP 籌碼沉澱組 ({len(vcp_incubating)} 檔)")
                    st.write(format_stocks(vcp_incubating))
                    st.caption("👉 極度重要：這群股票滿足了抗跌條件，且名字帶有 `💎` 或 `🔥`。代表主力正在低檔死守，且股價波動已收窄至極限、尚未噴發！這正是你要找的完美新標的。")

                # 保留其餘四象限大聯盟分流，供快速點檢
                with st.expander("📊 點檢其餘多軌象限分流（高Beta攻擊、資金防守）", expanded=False):
                    any_pass_momentum = df_final[alpha_passed & ~(c1_passed & c2_passed & c3_passed)]
                    any_pass_defensive = df_final[~alpha_passed & (c1_passed | c2_passed | c3_passed)]
                    laggards = df_final[~alpha_passed & ~(c1_passed | c2_passed | c3_passed)]
                    
                    cx1, cx2, cx3 = st.columns(3)
                    cx1.warning(f"#### 🚀 高 Beta 攻擊兵 ({len(any_pass_momentum)} 檔)")
                    cx1.write(format_stocks(any_pass_momentum))
                    cx2.info(f"#### 🛡️ 潛在補漲防守組 ({len(any_pass_defensive)} 檔)")
                    cx2.write(format_stocks(any_pass_defensive))
                    cx3.error(f"#### 🚨 汰弱留強剔除名單 ({len(laggards)} 檔)")
                    cx3.write(format_stocks(laggards))

        except Exception as e:
            st.error(f"數據錯誤: {e}")
