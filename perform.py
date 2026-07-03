import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import os
import re
import requests
from io import StringIO
from concurrent.futures import ThreadPoolExecutor

# 1. 網頁初始設定
st.set_page_config(page_title="🏆 SEPA 雙軌強勢股終端機", layout="wide")

# 2. 自動載入與動態初始化後台字典 (相容 UTF-8-sig)
@st.cache_data
def load_stock_dict():
    stock_dict = {}
    file_path = "stocks_list.txt"
    
    # 若檔案不存在或為空，自動自官方 API 抓取所有上市與上櫃股票代號
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        try:
            # 1. 獲取上市公司 (TWSE)
            url_twse = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
            r_twse = requests.get(url_twse, timeout=10)
            if r_twse.status_code == 200:
                for item in r_twse.json():
                    code = item.get("Code", "").strip()
                    name = item.get("Name", "").strip()
                    if code and name and code.isdigit() and len(code) == 4:
                        stock_dict[f"{code}.TW"] = name
            
            # 2. 獲取上櫃公司 (TPEx)
            url_tpex = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
            r_tpex = requests.get(url_tpex, timeout=10)
            if r_tpex.status_code == 200:
                for item in r_tpex.json():
                    code = item.get("SecuritiesCompanyCode", "").strip()
                    name = item.get("CompanyName", "").strip()
                    if code and name and code.isdigit() and len(code) == 4:
                        stock_dict[f"{code}.TWO"] = name
            
            # 寫入 stocks_list.txt
            with open(file_path, "w", encoding="utf-8-sig") as f:
                for code, name in sorted(stock_dict.items()):
                    f.write(f"{code},{name}\n")
        except Exception as e:
            st.sidebar.error(f"自動初始化股票資料庫失敗: {e}")
            
    # 從檔案讀取
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

# --- 🆕 優化版：處置股查詢引擎 (上市 TWSE + 上櫃 TPEx) ---
def _format_disposition_period(period_str):
    """將民國年『處置起迄時間』轉換為西元年字串，並利用正則表達式過濾雜訊"""
    if not period_str: return ""
    try:
        # 去除 HTML tag 干擾 (若有)
        cleaned = re.sub(r'<[^>]+>', '', str(period_str))
        cleaned = cleaned.replace('～', '~').replace('－', '~').replace('-', '~').strip()
        parts = [p.strip() for p in cleaned.split('~') if p.strip()]
        formatted = []
        for p in parts:
            # 智能提取日期數字，支援 113/06/15, 113.06.15, 113年06月15日 等多元格式
            match = re.search(r'(\d{3,4})[/\.年]\s*(\d{1,2})[/\.月]\s*(\d{1,2})', p)
            if match:
                y, m, d = match.groups()
                formatted.append(f"{int(y) + 1911}/{int(m):02d}/{int(d):02d}")
        if formatted:
            return " ~ ".join(formatted)
        return cleaned
    except Exception:
        return str(period_str)

@st.cache_data(ttl=1800)  # 處置公告每日更新，快取30分鐘
def fetch_disposition_data():
    """
    自動抓取『目前處於處置中』的個股清單 (含處置起迄時間)。
    🔄 升級：優先採用官方 OpenAPI JSON，若失敗再啟用備援爬蟲，並加入動態 Key 掃描確保 100% 抓到期間。
    """
    disposition_map = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # --- 上市 (TWSE) ---
    try: # 1. 優先嘗試官方 OpenAPI
        resp = requests.get("https://openapi.twse.com.tw/v1/announcement/punish", headers=headers, timeout=5)
        if resp.status_code == 200:
            for item in resp.json():
                code = str(item.get('Code', '')).strip()
                if not code: # 動態找尋代號 Key
                    for k, v in item.items():
                        if 'Code' in k or '代號' in k:
                            code = str(v).strip()
                            break
                if code and code.isalnum():
                    period_val = ""
                    for k, v in item.items():
                        if 'Period' in k or '期間' in k or '起迄' in k:
                            period_val = str(v)
                            break
                    if not period_val:
                        for v in item.values():
                            if isinstance(v, str) and ('~' in v or '～' in v) and re.search(r'\d', v):
                                period_val = v
                                break
                    disposition_map[code] = {
                        "period": _format_disposition_period(period_val),
                        "market": "上市"
                    }
    except Exception:
        pass

    try: # 1b. 若 OpenAPI 失敗或漏掉期間則啟動 JSON 備援爬蟲
        if not any(v['market'] == '上市' for v in disposition_map.values()) or any(v['period'] == '' for v in disposition_map.values() if v['market'] == '上市'):
            url_twse = "https://www.twse.com.tw/announcement/punish?response=json"
            resp = requests.get(url_twse, headers=headers, timeout=10)
            data = resp.json()
            if 'data' in data:
                for row in data['data']:
                    if len(row) >= 5:
                        code = str(row[1]).split('.')[0].strip()
                        code = ''.join(e for e in code if e.isalnum())
                        period = str(row[4]).strip()
                        if code and code not in disposition_map or (code in disposition_map and not disposition_map[code]['period']):
                            disposition_map[code] = {
                                "period": _format_disposition_period(period),
                                "market": "上市",
                            }
    except Exception:
        pass

    # --- 上櫃 (TPEx) ---
    try: # 2. 優先嘗試櫃買 OpenAPI
        resp2 = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_punish", headers=headers, timeout=5)
        if resp2.status_code == 200:
            for item in resp2.json():
                code = str(item.get('SecuritiesCompanyCode', item.get('Code', ''))).strip()
                if not code:
                    for k, v in item.items():
                        if 'Code' in k or '代號' in k:
                            code = str(v).strip()
                            break
                if code and code.isalnum():
                    period_val = ""
                    for k, v in item.items():
                        if 'Period' in k or '期間' in k or '起迄' in k:
                            period_val = str(v)
                            break
                    if not period_val:
                        for v in item.values():
                            if isinstance(v, str) and ('~' in v or '～' in v) and re.search(r'\d', v):
                                period_val = v
                                break
                    disposition_map[code] = {
                        "period": _format_disposition_period(period_val),
                        "market": "上櫃"
                    }
    except Exception:
        pass

    try: # 2b. 備援爬蟲：直搗 TPEx 的 JSON API
        if not any(v['market'] == '上櫃' for v in disposition_map.values()) or any(v['period'] == '' for v in disposition_map.values() if v['market'] == '上櫃'):
            url_tpex = "https://www.tpex.org.tw/web/bulletin/disposal_information/disposal_information_result.php?l=zh-tw"
            resp2 = requests.get(url_tpex, headers=headers, timeout=10)
            data = resp2.json()
            if 'aaData' in data:
                for row in data['aaData']:
                    if len(row) >= 4:
                        code = str(row[2]).strip()
                        code = ''.join(e for e in code if e.isalnum())
                        period = str(row[1]).strip()
                        if code and code not in disposition_map or (code in disposition_map and not disposition_map[code]['period']):
                            disposition_map[code] = {
                                "period": _format_disposition_period(period),
                                "market": "上櫃"
                            }
    except Exception:
        pass

    return disposition_map

# --- 🚀 基本面 API 數據獲取與快取 ---

@st.cache_data(ttl=86400) # 財報每季發布，快取1天
def fetch_finmind_financials(stock_id):
    """獲取 FinMind 季度損益表數據"""
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockFinancialStatements",
        "data_id": stock_id,
        "start_date": "2024-01-01"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            return r.json().get("data", [])
    except Exception:
        pass
    return []

@st.cache_data(ttl=3600) # 月營收每月發布，快取1小時
def fetch_finmind_monthly_revenue(stock_id):
    """獲取 FinMind 月營收數據"""
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockMonthRevenue",
        "data_id": stock_id,
        "start_date": "2024-01-01"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            return r.json().get("data", [])
    except Exception:
        pass
    return []

@st.cache_data(ttl=1800) # 盈餘意外預估，快取30分鐘
def fetch_yfinance_surprise(ticker):
    """獲取 yfinance 盈餘意外與分析師預估數據"""
    try:
        tick = yf.Ticker(ticker)
        ed = tick.get_earnings_dates(limit=5)
        if ed is not None and not ed.empty:
            return ed.to_json(date_format='iso')
    except Exception:
        pass
    return None

# --- 🧪 基本面運算核心邏輯 (支持歷史回溯時間軸過濾) ---

def process_code33(financials, backtest_date_str):
    """
    計算 Code 33 狀態及軌跡。
    條件：連續三季的 EPS YoY、營收 YoY、淨利率 同步呈現遞增趨勢。
    """
    if not financials:
        return {"active": False, "trajectory": "無財務報表數據", "display": "N/A"}
        
    # 歷史回溯過濾：僅保留基準日之前的資料
    filtered_data = [x for x in financials if x["date"] <= backtest_date_str]
    if not filtered_data:
        return {"active": False, "trajectory": "無回溯基準日前的財務數據", "display": "N/A"}
        
    df = pd.DataFrame(filtered_data)
    needed_types = ["Revenue", "IncomeAfterTaxes", "EPS"]
    df = df[df["type"].isin(needed_types)]
    if df.empty:
        return {"active": False, "trajectory": "無有效會計項目數據", "display": "N/A"}
        
    df_pivot = df.pivot(index="date", columns="type", values="value")
    df_pivot = df_pivot.sort_index()
    
    eps_yoy = []
    rev_yoy = []
    net_margin = []
    
    dates = df_pivot.index.tolist()
    for date_str in dates:
        current_date = pd.to_datetime(date_str)
        target_date = current_date - pd.DateOffset(years=1)
        target_date_str = target_date.strftime('%Y-%m-%d')
        
        # 1. 淨利率 Margin
        rev = df_pivot.loc[date_str, "Revenue"] if "Revenue" in df_pivot.columns else None
        net_inc = df_pivot.loc[date_str, "IncomeAfterTaxes"] if "IncomeAfterTaxes" in df_pivot.columns else None
        margin = (net_inc / rev * 100) if rev and rev > 0 and net_inc is not None else None
        net_margin.append(margin)
        
        # 2. EPS & Revenue YoY (比對去年同季)
        if target_date_str in df_pivot.index:
            eps_now = df_pivot.loc[date_str, "EPS"] if "EPS" in df_pivot.columns else None
            eps_last = df_pivot.loc[target_date_str, "EPS"] if "EPS" in df_pivot.columns else None
            yoy_eps = (eps_now / eps_last - 1) * 100 if eps_last and eps_last != 0 and eps_now is not None else None
            
            rev_now = df_pivot.loc[date_str, "Revenue"] if "Revenue" in df_pivot.columns else None
            rev_last = df_pivot.loc[target_date_str, "Revenue"] if "Revenue" in df_pivot.columns else None
            yoy_rev = (rev_now / rev_last - 1) * 100 if rev_last and rev_last != 0 and rev_now is not None else None
        else:
            yoy_eps = None
            yoy_rev = None
            
        eps_yoy.append(yoy_eps)
        rev_yoy.append(yoy_rev)
        
    df_pivot["EPS_YoY"] = eps_yoy
    df_pivot["Revenue_YoY"] = rev_yoy
    df_pivot["NetMargin"] = net_margin
    
    valid_df = df_pivot.dropna(subset=["EPS_YoY", "Revenue_YoY", "NetMargin"])
    if len(valid_df) < 3:
        return {"active": False, "trajectory": "歷史季數不足 (計算 YoY 需比對去年)", "display": "不足3季數據"}
        
    # 連續三季加速檢測
    eps_acc = valid_df["EPS_YoY"].iloc[-1] > valid_df["EPS_YoY"].iloc[-2] > valid_df["EPS_YoY"].iloc[-3]
    rev_acc = valid_df["Revenue_YoY"].iloc[-1] > valid_df["Revenue_YoY"].iloc[-2] > valid_df["Revenue_YoY"].iloc[-3]
    margin_acc = valid_df["NetMargin"].iloc[-1] > valid_df["NetMargin"].iloc[-2] > valid_df["NetMargin"].iloc[-3]
    
    active = eps_acc and rev_acc and margin_acc
    
    eps_t3 = valid_df["EPS_YoY"].iloc[-3:].tolist()
    rev_t3 = valid_df["Revenue_YoY"].iloc[-3:].tolist()
    margin_t3 = valid_df["NetMargin"].iloc[-3:].tolist()
    
    trajectory = (
        f"EPS YoY: {eps_t3[0]:.1f}% → {eps_t3[1]:.1f}% → {eps_t3[2]:.1f}%\\n"
        f"營收 YoY: {rev_t3[0]:.1f}% → {rev_t3[1]:.1f}% → {rev_t3[2]:.1f}%\\n"
        f"淨利率: {margin_t3[0]:.1f}% → {margin_t3[1]:.1f}% → {margin_t3[2]:.1f}%"
    )
    
    display_text = f"✅ (EPS: {eps_t3[2]:.1f}%)" if active else f"❌ (EPS: {eps_t3[2]:.1f}%)"
    return {"active": active, "trajectory": trajectory, "display": display_text}

def process_monthly_momentum(monthly_rev, backtest_date_str):
    """
    計算月營收動能狀態及軌跡。
    條件：月營收創 12 個月新高，或 YoY 連續兩月加速。
    """
    if not monthly_rev:
        return {"is_12m_high": False, "is_accelerating": False, "trajectory": "無營收數據", "display": "N/A"}
        
    filtered_data = [x for x in monthly_rev if x["date"] <= backtest_date_str]
    if not filtered_data:
        return {"is_12m_high": False, "is_accelerating": False, "trajectory": "無回溯基準日前的營收數據", "display": "N/A"}
        
    df = pd.DataFrame(filtered_data)
    df = df.sort_values(["revenue_year", "revenue_month"]).reset_index(drop=True)
    
    # 建立映射以精準對齊去年同月
    rev_map = {}
    for _, row in df.iterrows():
        y = int(row["revenue_year"])
        m = int(row["revenue_month"])
        rev_map[(y, m)] = float(row["revenue"])
        
    yoy_list = []
    for _, row in df.iterrows():
        y = int(row["revenue_year"])
        m = int(row["revenue_month"])
        rev_now = float(row["revenue"])
        rev_last = rev_map.get((y - 1, m))
        yoy = (rev_now / rev_last - 1) * 100 if rev_last and rev_last > 0 else None
        yoy_list.append(yoy)
        
    df["YoY"] = yoy_list
    
    if len(df) < 1:
        return {"is_12m_high": False, "is_accelerating": False, "trajectory": "無營收數據", "display": "N/A"}
        
    latest_idx = len(df) - 1
    row_latest = df.iloc[latest_idx]
    rev_latest = float(row_latest["revenue"])
    yoy_latest = row_latest["YoY"]
    y_lat, m_lat = int(row_latest["revenue_year"]), int(row_latest["revenue_month"])
    
    # 1. 12個月新高
    is_12m_high = False
    max_prev = 0
    if latest_idx >= 11:
        prev_11 = df.iloc[latest_idx-11:latest_idx]["revenue"].astype(float)
        max_prev = prev_11.max()
        is_12m_high = rev_latest > max_prev
        
    # 2. YoY 連續兩月加速 (YoY_t > YoY_{t-1} > YoY_{t-2})
    is_accelerating = False
    yoy_t0 = df.iloc[latest_idx]["YoY"]
    yoy_t1 = df.iloc[latest_idx-1]["YoY"] if latest_idx >= 1 else None
    yoy_t2 = df.iloc[latest_idx-2]["YoY"] if latest_idx >= 2 else None
    if yoy_t0 is not None and yoy_t1 is not None and yoy_t2 is not None:
        is_accelerating = yoy_t0 > yoy_t1 > yoy_t2
        
    yoy_str = "YoY: N/A"
    if yoy_t0 is not None and yoy_t1 is not None and yoy_t2 is not None:
        yoy_str = f"YoY: {yoy_t2:.1f}% → {yoy_t1:.1f}% → {yoy_t0:.1f}%"
        
    trajectory = (
        f"統計期間: {y_lat}年{m_lat}月\\n"
        f"最新單月營收: {rev_latest/1e8:.1f}億元 vs 12M最高: {max_prev/1e8:.1f}億元\\n"
        f"{yoy_str} ({'YoY加速' if is_accelerating else 'YoY未加速'})"
    )
    
    # 表格顯示格式
    if is_12m_high and is_accelerating:
        disp = "✅ 雙重爆發"
    elif is_12m_high:
        disp = "✅ 創12M新高"
    elif is_accelerating:
        disp = "✅ YoY連2月加速"
    else:
        disp = "❌"
        
    return {
        "is_12m_high": is_12m_high,
        "is_accelerating": is_accelerating,
        "trajectory": trajectory,
        "display": disp,
        "latest_rev": rev_latest,
        "latest_yoy": yoy_latest
    }

def process_earnings_surprise(surprise_json, backtest_date):
    """
    從 yfinance 導出 JSON 中提取最近的盈餘意外數據。
    """
    if not surprise_json:
        return None
    try:
        ed = pd.read_json(StringIO(surprise_json))
        if ed.empty:
            return None
        
        # 轉換回 timezone-aware cutoff 來做歷史回溯過濾
        cutoff = pd.to_datetime(backtest_date).tz_localize(ed.index.tz)
        df_reported = ed[ed.index <= cutoff].dropna(subset=['Reported EPS', 'EPS Estimate', 'Surprise(%)'])
        
        if not df_reported.empty:
            latest = df_reported.iloc[0] # yfinance 由新到舊排列
            return {
                "estimate": float(latest['EPS Estimate']),
                "actual": float(latest['Reported EPS']),
                "surprise": float(latest['Surprise(%)']),
                "date": df_reported.index[0].strftime('%Y-%m-%d')
            }
    except Exception:
        pass
    return None

# --- 🚀 多線程併發加載基本面數據 ---

def get_single_stock_fundamentals(args):
    ticker, backtest_date = args
    stock_id = ticker.split('.')[0]
    backtest_date_str = backtest_date.strftime('%Y-%m-%d')
    
    # 1. 抓取數據 (使用 Cache)
    financials = fetch_finmind_financials(stock_id)
    monthly_rev = fetch_finmind_monthly_revenue(stock_id)
    surprise_json = fetch_yfinance_surprise(ticker)
    
    # 2. 計算基本面指標
    c33 = process_code33(financials, backtest_date_str)
    mrev = process_monthly_momentum(monthly_rev, backtest_date_str)
    surprise = process_earnings_surprise(surprise_json, backtest_date)
    
    return ticker, c33, mrev, surprise

def fetch_all_fundamentals(tickers, backtest_date):
    """併發加載所有股票的基本面資料"""
    results = {}
    args_list = [(ticker, backtest_date) for ticker in tickers]
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures_results = list(executor.map(get_single_stock_fundamentals, args_list))
    for ticker, c33, mrev, surprise in futures_results:
        results[ticker] = {
            "c33": c33,
            "mrev": mrev,
            "surprise": surprise
        }
    return results

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
        "8438.TW,昶昕\n3691.TWO,碩禾\n2423.TW,固緯\n8147.TWO,正淩\n8028.TW,昇陽半導體\n6716.TWO,應廣\n2428.TW,興勤\n5284.TW,JPP-KY\n"
        "2493.TW,揚博\n3023.TW,信邦\n6672.TW,騰輝電子\n3044.TW,健鼎\n6134.TWO,萬旭\n2413.TW,環科\n3577.TWO,泓格\n3305.TW,昇貿"
    )
    stock_input = st.text_area("股票清單 (支援複製貼上！系統會自動過濾國籍、財報等非代號雜訊)", value=default_pool, height=300)
    
    st.subheader("【短線逆風照妖鏡參數】")
    lookback_days = st.number_input("自訂照妖鏡觀察天數", min_value=5, max_value=365, value=60, step=1)
    market_threshold = st.slider("大盤恐慌日定義 (單日跌幅 %)", min_value=0.5, max_value=2.5, value=1.0, step=0.1)
    
    st.subheader("【🕒 歷史回溯與績效回測】")
    backtest_date = st.date_input("選擇回溯基準日 (以此日視為當時的今天)", value=datetime.today())
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
    
    end_date = datetime.combine(backtest_date, datetime.min.time())
    real_today = datetime.today()
    
    start_date_long = end_date - timedelta(days=730) 
    start_date_short = end_date - timedelta(days=int(lookback_days))
    
    with st.spinner("量化引擎計算中... 正在進行一鍵式批次下載與時間軸同步校正..."):
        try:
            if not STOCKS_POOL:
                st.error("❌ 過濾雜訊後，未偵測到任何有效的股票代號，請重新輸入。")
            else:
                all_tickers = ["0050.TW"] + [stock["id"] for stock in STOCKS_POOL]
                
                download_end_date = real_today + timedelta(days=1)
                df_all = fetch_and_sync_data(tuple(all_tickers), start_date_long.strftime('%Y-%m-%d'), download_end_date.strftime('%Y-%m-%d'))
                
                df_adj = df_all['Close'] if 'Close' in df_all.columns.levels[0] else df_all['Adj Close']
                df_vol = df_all['Volume']
                
                b_c_all = df_adj["0050.TW"].dropna()
                b_c = b_c_all.loc[:end_date.strftime('%Y-%m-%d')]
                
                if b_c.empty:
                    st.error("❌ 回溯基準日無交易數據或超出歷史範圍，請重新選擇。")
                else:
                    idx_now = b_c.index[-1]
                    loc_now = b_c_all.index.get_loc(idx_now)
                    
                    if loc_now + holding_days < len(b_c_all):
                        idx_future = b_c_all.index[loc_now + holding_days]
                        actual_holding_text = f"後續 {holding_days} 個交易日 (至 {idx_future.strftime('%Y-%m-%d')})"
                    else:
                        idx_future = b_c_all.index[-1]
                        actual_holding_text = f"後續 {len(b_c_all) - 1 - loc_now} 個交易日 (資料庫極限至今日 {idx_future.strftime('%Y-%m-%d')})"

                    if len(b_c) >= 253:
                        b_now_val = b_c.iloc[-1]
                        b_3m_val = b_c.iloc[-64]
                        b_6m_val = b_c.iloc[-127]
                        b_9m_val = b_c.iloc[-190]
                        b_1y_val = b_c.iloc[-253]
                        benchmark_ibd_score = ((b_now_val/b_3m_val*2) + (b_now_val/b_6m_val) + (b_now_val/b_9m_val) + (b_now_val/b_1y_val)) / 5 * 100
                    else:
                        benchmark_ibd_score = 0.0
                    
                    b_short_df = pd.DataFrame(b_c.loc[start_date_short.strftime('%Y-%m-%d'):])
                    b_short_df.columns = ['Close_Price']
                    b_short_df['Market_Return'] = b_short_df['Close_Price'].pct_change() * 100
                    panic_days = b_short_df[b_short_df['Market_Return'] <= -market_threshold]
                    total_panic_days = len(panic_days)
                    panic_dates_list = panic_days.index.tolist()
                    
                    dynamic_threshold = 55.0 if total_panic_days <= 5 else (70.0 if total_panic_days <= 15 else 80.0)
                    level_desc = "⚡ 極短線回檔（採取寬鬆防守標準，勝率過半即合格）" if total_panic_days <= 5 else ("⚖️ 標準波段修正（採取黃金 70% 機構防守標準）" if total_panic_days <= 15 else "🚨 空頭大屠殺 / 系統性風險（採取極嚴苛 80% 沙裡淘金標準）")
                    
                    # 🚀 多線程併發加載基本面數據
                    tickers_for_fundamentals = [stock["id"] for stock in STOCKS_POOL]
                    FUNDAMENTAL_RESULTS = fetch_all_fundamentals(tickers_for_fundamentals, backtest_date)
                    
                    integrated_results = []
                    skipped_stocks = []
                    
                    for stock in STOCKS_POOL:
                        ticker = stock["id"]
                        
                        if ticker not in df_adj.columns:
                            skipped_stocks.append(stock["name"])
                            continue
                        
                        s_series_raw_all = df_adj[ticker].dropna()
                        s_series_raw = s_series_raw_all.loc[:end_date.strftime('%Y-%m-%d')]
                        
                        if s_series_raw.empty:
                            skipped_stocks.append(stock["name"])
                            continue
                            
                        p_now = s_series_raw.iloc[-1]
                        
                        if len(s_series_raw) >= 50:
                            ma50_val = s_series_raw.rolling(window=50).mean().iloc[-1]
                            bias_50 = ((p_now - ma50_val) / ma50_val) * 100
                        else:
                            bias_50 = 0.0
                            
                        if len(s_series_raw) >= 200:
                            sma50_s = s_series_raw.rolling(50).mean()
                            sma150_s = s_series_raw.rolling(150).mean()
                            sma200_s = s_series_raw.rolling(200).mean()
                            
                            m50 = sma50_s.iloc[-1]
                            m150 = sma150_s.iloc[-1]
                            m200 = sma200_s.iloc[-1]
                            
                            m200_22 = sma200_s.iloc[-23] if len(sma200_s) >= 23 else np.nan
                            
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

                        if len(s_series_raw) >= 253:
                            s_now_val = s_series_raw.iloc[-1]
                            s_3m_val = s_series_raw.iloc[-64]
                            s_6m_val = s_series_raw.iloc[-127]
                            s_9m_val = s_series_raw.iloc[-190]
                            s_1y_val = s_series_raw.iloc[-253]
                            ibd = ((s_now_val/s_3m_val*2) + (s_now_val/s_6m_val) + (s_now_val/s_9m_val) + (s_now_val/s_1y_val)) / 5 * 100
                        else:
                            ibd = 0.0
                        
                        s_ret = s_series_raw.pct_change() * 100
                        outperform = np.sum(s_ret.reindex(panic_dates_list) > b_short_df.loc[panic_dates_list, 'Market_Return'])
                        resilience = (outperform / total_panic_days * 100) if total_panic_days > 0 else 100
                        
                        is_price_new_high = False
                        is_alpha_new_high = False
                        is_alpha_lagging = False
                        is_vcp_80 = False
                        is_vcp_90 = False
                        is_vcp_dead_quiet = False
                        is_rs_recovering = False
                        
                        if len(s_series_raw) >= 30:
                            b_c_aligned_to_stock = b_c_all.reindex(s_series_raw.index).ffill()
                            rel_close = s_series_raw / b_c_aligned_to_stock
                            
                            is_price_new_high = p_now >= s_series_raw.iloc[-31:-1].max()
                            is_alpha_new_high = rel_close.iloc[-1] >= rel_close.iloc[-31:-1].max()
                            is_alpha_lagging = rel_close.iloc[-1] < rel_close.iloc[-31:-1].max()
                            
                            if len(rel_close) >= 3:
                                is_rs_recovering = rel_close.iloc[-1] > rel_close.iloc[-2] and rel_close.iloc[-2] > rel_close.iloc[-3]
                            
                            roll_std5 = s_series_raw.rolling(5).std(ddof=0)
                            roll_mean5 = s_series_raw.rolling(5).mean()
                            cv_5 = roll_std5 / roll_mean5
                            
                            if len(cv_5) >= 20:
                                cv_5_ma20 = cv_5.rolling(20).mean()
                                cv_5_now = cv_5.iloc[-1]
                                cv_5_ma20_now = cv_5_ma20.iloc[-1]
                                
                                is_vcp_dead_quiet = cv_5_now < cv_5_ma20_now * 0.50
                                is_vcp_80 = cv_5_now < cv_5_ma20_now * 0.80
                                is_vcp_90 = cv_5_now < cv_5_ma20_now * 0.90
                        
                        is_rs_leading = (not is_price_new_high) and is_alpha_new_high
                        is_div_warning = is_price_new_high and is_alpha_lagging
                        
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
                        display_name = f"✅ {stock['name']} 【{vcp_status_final}】" if is_trend_template else f"❌ {stock['name']} 【{vcp_status_final}】"
                        
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
                        
                        # 讀取基本面計算數據
                        fund_data = FUNDAMENTAL_RESULTS.get(ticker, {})
                        c33_display = fund_data.get("c33", {}).get("display", "N/A")
                        mrev_display = fund_data.get("mrev", {}).get("display", "N/A")
                        surprise_data = fund_data.get("surprise")
                        if surprise_data:
                            surp_val = surprise_data["surprise"]
                            surprise_display = f"+{surp_val:.1f}%" if surp_val > 0 else f"{surp_val:.1f}%"
                        else:
                            surprise_display = "N/A"

                        integrated_results.append({
                            "ticker": ticker, # 隱藏欄位
                            "股票代號": ticker.split(".")[0], 
                            "股票名稱": display_name,
                            "原始名稱": stock['name'],
                            "趨勢模板": "✅" if is_trend_template else "❌",
                            "動能狀態判定": vcp_status_final,
                            "🧪 Code 33": c33_display,
                            "🚀 月營收爆發": mrev_display,
                            "💥 盈餘意外": surprise_display,
                            "50MA乖離率(%)": bias_50,
                            "IBD式 絕對分數": ibd, "對比 0050 超額強度": ibd - benchmark_ibd_score,
                            "短線抗跌韌性分數": resilience, "逆風勝率": f"{outperform} / {total_panic_days} 天",
                            "逆風上漲天數": f"{np.sum(s_ret.reindex(panic_dates_list) > 0)} 天",
                            perf_col_key: future_return
                        })
                    
                    df_final = pd.DataFrame(integrated_results).sort_values("對比 0050 超額強度", ascending=False)
                    
                    cols = df_final.columns.tolist()
                    perf_col_name = f"後續{holding_days}日實際報酬(%)"
                    
                    # 重新安排基本面欄位順序至顯眼處
                    fundamental_cols = ["🧪 Code 33", "🚀 月營收爆發", "💥 盈餘意外"]
                    for f_col in fundamental_cols:
                        if f_col in cols:
                            cols.remove(f_col)
                    
                    # 插入至股票名稱後面
                    idx_to_insert = cols.index("股票名稱") + 1
                    for f_col in reversed(fundamental_cols):
                        cols.insert(idx_to_insert, f_col)
                    
                    if "50MA乖離率(%)" in cols:
                        cols.remove("50MA乖離率(%)")
                        cols.append("50MA乖離率(%)")
                    if perf_col_name in cols:
                        cols.remove(perf_col_name)
                        if is_backtesting:
                            cols.insert(cols.index("股票名稱") + 1 + len(fundamental_cols), perf_col_name)
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
                        * ❌ 未符標記：代表該股目前未全數滿足 7 項技術面排列準則（可能均線結構仍待修復，或距 52 週高低點比例未達標）。
                        
                        🌀 VCP / 動能狀態動態標籤說明：
                        * 🌟 雙軌領先：個股股價尚未突破30日新高，但相對強度 (Alpha RS 曲線) 已率先刷新30日紀錄，暗示機構暗中強勢吃貨，極具爆發力。
                        * ⚠️ 雙軌背離：股價已創30日新高，但相對強度未同步創高，短線動能呈現隱形落後，需警惕高檔假突破。
                        * 💤 價格波動沉寂(Dead Quiet)：5日價格變異係數收縮至20日均值的 50% 以下，代表波幅極限窄化，即將噴發大行情。
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
                    
                    column_config_dict = {
                        "50MA乖離率(%)": st.column_config.NumberColumn("50MA乖離率", format="%.2f%%"),
                        "IBD式 絕對分數": st.column_config.NumberColumn("IBD式 絕對強度", format="%.1f"),
                        "短線抗跌韌性分數": st.column_config.ProgressColumn("抗跌得分", min_value=0, max_value=100, format="%.0f分"),
                        "🧪 Code 33": st.column_config.TextColumn("🧪 Code 33", help="連續三季的 EPS YoY、營收 YoY、淨利率 是否同步呈現遞增趨勢"),
                        "🚀 月營收爆發": st.column_config.TextColumn("🚀 月營收爆發", help="最新月營收創 12 個月新高，或營收 YoY 連續兩月加速"),
                        "💥 盈餘意外": st.column_config.TextColumn("💥 盈餘意外", help="實際公佈每股盈餘與分析師預估值之意外比例 (%)")
                    }
                    if is_backtesting:
                        column_config_dict[perf_col_name] = st.column_config.NumberColumn(f"🎯 後續{holding_days}日報酬", format="%.2f%%")
                    else:
                        column_config_dict[perf_col_name] = st.column_config.NumberColumn("今日至今持平率", format="%.2f%%")
                        
                    display_df = df_final.drop(columns=["ticker", "原始名稱", "趨勢模板", "動能狀態判定"], errors="ignore")
                    st.dataframe(display_df, use_container_width=True, hide_index=True, column_config=column_config_dict)
                    
                    st.divider()
                    st.subheader("🏁 Mark Minervini 流派：雙軌交叉戰略部署")
                    st.caption(f"💡 註：括號內為 50MA 乖離率(%)。右側標註為【後續 {holding_days} 日回測實際報酬率】。懸停於基本面標籤可檢視詳細數據與軌跡。")
                    
                    with st.spinner("🚨 正在同步證交所/櫃買中心處置股公告..."):
                        DISPOSITION_MAP = fetch_disposition_data()
                    if DISPOSITION_MAP:
                        st.sidebar.caption(f"🚨 處置股監控：目前偵測到 {len(DISPOSITION_MAP):,} 檔全市場處置中證券")

                    true_leaders = df_final[(df_final["對比 0050 超額強度"] > 0) & (df_final["短線抗跌韌性分數"] >= dynamic_threshold)]
                    momentum_only = df_final[(df_final["對比 0050 超額強度"] > 0) & (df_final["短線抗跌韌性分數"] < dynamic_threshold)]
                    defensive_only = df_final[(df_final["對比 0050 超額強度"] <= 0) & (df_final["短線抗跌韌性分數"] >= dynamic_threshold)]
                    laggards = df_final[(df_final["對比 0050 超額強度"] <= 0) & (df_final["短線抗跌韌性分數"] < dynamic_threshold)]
                    
                    def format_stocks(df, show_perf=False):
                        if df.empty:
                            return "無"
                        lines = []
                        for _, row in df.iterrows():
                            perf_str = f" ➡️ 後續報酬: {row[perf_col_name]:.1f}%" if show_perf else ""
                            bias_val = row['50MA乖離率(%)']
                            
                            if bias_val >= 30.0:
                                bias_str = f"<span style='background-color: #ffcccc; color: #990000; padding: 2px 4px; border-radius: 4px; font-weight: bold;'>{bias_val:.1f}%</span>"
                            else:
                                bias_str = f"{bias_val:.1f}%"

                            disp_info = DISPOSITION_MAP.get(row['股票代號'])
                            if disp_info:
                                period_text = f" ({disp_info['period']})" if disp_info.get('period') else ""
                                disp_str = (
                                    f" <span style='background-color: #fff1f0; color: #e74c3c; border: 1px solid #ffbaba; "
                                    f"padding: 2px 6px; border-radius: 6px; font-size: 0.85em; font-weight: 600; "
                                    f"margin-left: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);'>"
                                    f"🚨 處置中{period_text}</span>"
                                )
                            else:
                                disp_str = ""
                                
                            # 基本面 HTML 標籤與懸停提示 (Tooltips)
                            ticker = row["ticker"]
                            fund = FUNDAMENTAL_RESULTS.get(ticker, {})
                            
                            # 1. Code 33 Badge
                            c33 = fund.get("c33", {})
                            c33_active = c33.get("active", False)
                            c33_traj = c33.get("trajectory", "").replace('"', '&quot;')
                            if c33_active:
                                c33_badge = f'<span style="background-color: #e6f7ff; color: #0050b3; border: 1px solid #91d5ff; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; font-weight: bold; margin-left: 4px; cursor: help;" title="{c33_traj}">🧪 Code 33 ✅</span>'
                            else:
                                c33_badge = f'<span style="background-color: #f5f5f5; color: #595959; border: 1px solid #d9d9d9; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; margin-left: 4px; cursor: help;" title="{c33_traj}">🧪 Code 33 ❌</span>'
                                
                            # 2. Monthly Revenue Badge
                            mrev = fund.get("mrev", {})
                            mrev_12h = mrev.get("is_12m_high", False)
                            mrev_acc = mrev.get("is_accelerating", False)
                            mrev_traj = mrev.get("trajectory", "").replace('"', '&quot;')
                            if mrev_12h and mrev_acc:
                                mrev_badge = f'<span style="background-color: #f6ffed; color: #389e0d; border: 1px solid #b7eb8f; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; font-weight: bold; margin-left: 4px; cursor: help;" title="{mrev_traj}">🚀 月營收爆發</span>'
                            elif mrev_12h:
                                mrev_badge = f'<span style="background-color: #f6ffed; color: #389e0d; border: 1px solid #b7eb8f; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; font-weight: bold; margin-left: 4px; cursor: help;" title="{mrev_traj}">🚀 營收新高</span>'
                            elif mrev_acc:
                                mrev_badge = f'<span style="background-color: #f6ffed; color: #389e0d; border: 1px solid #b7eb8f; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; font-weight: bold; margin-left: 4px; cursor: help;" title="{mrev_traj}">🚀 營收YoY加速</span>'
                            else:
                                mrev_badge = f'<span style="background-color: #f5f5f5; color: #595959; border: 1px solid #d9d9d9; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; margin-left: 4px; cursor: help;" title="{mrev_traj}">🚀 月營收 ❌</span>'
                                
                            # 3. Earnings Surprise Badge
                            surprise = fund.get("surprise")
                            if surprise:
                                val = surprise["surprise"]
                                est = surprise["estimate"]
                                act = surprise["actual"]
                                dt = surprise["date"]
                                title_str = f"預估 EPS: {est:.2f}\\n實際 EPS: {act:.2f}\\n公佈日期: {dt}".replace('"', '&quot;')
                                if val > 0:
                                    surprise_badge = f'<span style="background-color: #fff7e6; color: #d46b08; border: 1px solid #ffd591; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; font-weight: bold; margin-left: 4px; cursor: help;" title="{title_str}">💥 盈餘意外 +{val:.1f}%</span>'
                                else:
                                    surprise_badge = f'<span style="background-color: #fff0f6; color: #c41d7f; border: 1px solid #ffadd2; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; font-weight: bold; margin-left: 4px; cursor: help;" title="{title_str}">💥 盈餘意外 {val:.1f}%</span>'
                            else:
                                surprise_badge = f'<span style="background-color: #f5f5f5; color: #595959; border: 1px solid #d9d9d9; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; margin-left: 4px; cursor: help;" title="無分析師預估資料">💥 盈餘意外 N/A</span>'
                                
                            fund_badges = f"{c33_badge}{mrev_badge}{surprise_badge}"
                            formatted_name = f"{row['趨勢模板']} {row['原始名稱']} 【{row['動能狀態判定']}】"
                            lines.append(f"* {formatted_name} ({bias_str}){disp_str}{fund_badges}{perf_str}")
                        return "\n".join(lines)

                    c1, c2 = st.columns(2)
                    c1.success(f"### 👑 第一象限：逆風真龍頭 ({len(true_leaders)} 檔)"); c1.markdown(format_stocks(true_leaders, is_backtesting), unsafe_allow_html=True); c1.caption("👉 戰略部署：長線動能擊敗大盤，且短線抗跌表現達到當前動態合格線以上。隨時注意 VCP 出量突破。")
                    c1.info(f"### 🚀 第二象限：高 Beta 攻擊兵 ({len(momentum_only)} 檔)"); c1.markdown(format_stocks(momentum_only, is_backtesting), unsafe_allow_html=True); c1.caption("👉 戰略部署：長線極強，但修正波動高於大盤. 一旦大盤止穩，這群股票往往是右側出量追擊的首選。")
                    c2.warning(f"### 🛡️ 第三象限：資金避風港 ({len(defensive_only)} 檔)"); c2.markdown(format_stocks(defensive_only, is_backtesting), unsafe_allow_html=True); c2.caption("👉 戰略部署：短線極度抗跌，長線動能尚未完全追上。若有打打底完成標的，高抗跌意味主力在低檔死守，值得關注！")
                    c2.error(f"### 🚨 第四象限：無情剔除名單 ({len(laggards)} 檔)"); c2.markdown(format_stocks(laggards, is_backtesting), unsafe_allow_html=True); c2.caption("👉 戰略部署：長短線皆跑輸大盤，在馬克系統中屬於弱勢標的，建議審慎評估資金配置與汰弱留強。")
                    
        except Exception as e:
            st.error(f"數據錯誤: {e}")
