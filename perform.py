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

from bs4 import BeautifulSoup




# 1. 網頁初始設定
st.set_page_config(page_title="🏆 SEPA 雙軌強勢股終端機", layout="wide")


# 2. 自動載入與動態初始化後台字典 (相容 UTF-8-sig)
@st.cache_data
def load_stock_dict():
    import time
    stock_dict = {}
    dir_path = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(dir_path, "stocks_list.txt")

    # 檢查檔案是否已過期 (超過 30 天)
    file_exists = os.path.exists(file_path)
    is_outdated = False
    if file_exists:
        try:
            file_mtime = os.path.getmtime(file_path)
            # 30 天為 30 * 86400 秒
            if time.time() - file_mtime > 30 * 86400:
                is_outdated = True
        except Exception:
            pass

    # 若檔案不存在、為空或已過期，自動自官方 API 抓取並覆蓋
    if not file_exists or os.path.getsize(file_path) == 0 or is_outdated:
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
            if stock_dict:
                with open(file_path, "w", encoding="utf-8-sig") as f:
                    for code, name in sorted(stock_dict.items()):
                        f.write(f"{code},{name}\n")
        except Exception as e:
            st.sidebar.error(f"自動初始化股票資料庫失敗: {e}")

    # 從檔案讀取
    stock_dict = {}
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
@st.cache_data(ttl=3600)  # 快取1小時，避免重複下載單一股票
def fetch_single_ticker_data(ticker, start_date, end_date):
    """下載單一股票歷史資料並快取"""
    import time
    import random
    # 隨機微秒延遲防範高併發被 Yahoo Block
    time.sleep(random.uniform(0.02, 0.1))
    df = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)
    if df.empty:
        raise RuntimeError(f"No data fetched for {ticker}")
    return df

def fetch_and_sync_data(tickers, start_date, end_date):
    """併發下載股票歷史資料，並以單股級別快取"""
    results = {}
    # 使用多線程併發下載
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_single_ticker_data, t, start_date, end_date): t for t in tickers}
        for future in futures:
            t = futures[future]
            try:
                df = future.result()
                if not df.empty:
                    results[t] = df
            except Exception:
                pass

    if not results:
        return pd.DataFrame()

    # 重組為與原 yf.download 一致的 MultiIndex (Metric, Ticker) 格式
    combined_dfs = []
    for t, df in results.items():
        if isinstance(df.columns, pd.MultiIndex):
            df_temp = df.copy()
        else:
            df_temp = df.copy()
            df_temp.columns = pd.MultiIndex.from_product([df_temp.columns, [t]])
        combined_dfs.append(df_temp)

    df_all = pd.concat(combined_dfs, axis=1)
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
                year_val = int(y)
                if year_val < 1911:
                    year_val += 1911
                formatted.append(f"{year_val}/{int(m):02d}/{int(d):02d}")
        if formatted:
            return " ~ ".join(formatted)
        return cleaned
    except Exception:
        return str(period_str)

def fetch_disposition_data_raw():
    """
    自動抓取『目前處於處置中』的個股清單 (含處置起迄時間)，啟用 SSL 憑證安全驗證。
    """
    disposition_map = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # --- 上市 (TWSE) ---
    try: # 1. 優先嘗試官方 OpenAPI
        resp = requests.get("https://openapi.twse.com.tw/v1/announcement/punish", headers=headers, timeout=8)
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
        resp2 = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_punish", headers=headers, timeout=8)
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

@st.cache_data(ttl=1800)
def fetch_disposition_data_cached():
    """使用 st.cache_data 安全載入處置股資料，快取時間 30 分鐘，跨 Session 共用"""
    return fetch_disposition_data_raw()

DISPOSITION_MAP = fetch_disposition_data_cached()
if DISPOSITION_MAP:
    st.sidebar.caption(f"🚨 處置股監控：目前偵測到 {len(DISPOSITION_MAP):,} 檔全市場處置中證券")

# --- 🚀 基本面 API 數據獲取（快取存入 session_state 以跨 rerun 持久化） ---

def get_finmind_token():
    """從 session_state 或 st.secrets 取得選填的 FinMind Token"""
    if "finmind_token" in st.session_state and st.session_state.finmind_token:
        return st.session_state.finmind_token.strip()
    try:
        return st.secrets.get("FINMIND_TOKEN", "").strip()
    except Exception:
        return ""

@st.cache_data(ttl=86400)
def fetch_finmind_financials(stock_id, token):
    """獲取季度損益表數據 (首選 FinMind，失敗則自動以 yfinance 作為免費備援，支援重試與避退)"""
    import time
    import random
    # 1. 嘗試 FinMind API (最多重試 2 次)
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockFinancialStatements",
        "data_id": stock_id,
        "start_date": "2024-01-01"
    }
    if token:
        params["token"] = token
    for attempt in range(2):
        try:
            r = requests.get(url, params=params, timeout=8)
            if r.status_code == 200:
                data = r.json().get("data", [])
                if data:
                    return data
            elif r.status_code in [402, 429]:
                time.sleep(1.0 + random.uniform(0.1, 0.5))
                continue
        except (requests.exceptions.RequestException, Exception):
            if attempt < 1:
                time.sleep(0.5 + random.uniform(0.05, 0.2))
                continue

    # 2. 備援機制：使用 yfinance 獲取季度財報數據 (免費且免 Token)
    for suffix in [".TW", ".TWO"]:
        try:
            ticker = f"{stock_id}{suffix}"
            tick = yf.Ticker(ticker)
            qf = tick.quarterly_financials
            if qf is not None and not qf.empty:
                # 建立符合 process_code33 格式的財務字典清單
                records = []
                # 智能對齊會計科目名稱
                rev_row = "Total Revenue" if "Total Revenue" in qf.index else ("Operating Revenue" if "Operating Revenue" in qf.index else None)
                net_row = "Net Income" if "Net Income" in qf.index else ("Net Income Including Noncontrolling Interests" if "Net Income Including Noncontrolling Interests" in qf.index else None)
                eps_row = "Basic EPS" if "Basic EPS" in qf.index else ("Diluted EPS" if "Diluted EPS" in qf.index else None)

                for col_date in qf.columns:
                    date_str = col_date.strftime('%Y-%m-%d')
                    if rev_row:
                        val = qf.loc[rev_row, col_date]
                        if pd.notna(val):
                            records.append({'date': date_str, 'stock_id': stock_id, 'type': 'Revenue', 'value': float(val)})
                    if net_row:
                        val = qf.loc[net_row, col_date]
                        if pd.notna(val):
                            records.append({'date': date_str, 'stock_id': stock_id, 'type': 'IncomeAfterTaxes', 'value': float(val)})
                    if eps_row:
                        val = qf.loc[eps_row, col_date]
                        if pd.notna(val):
                            records.append({'date': date_str, 'stock_id': stock_id, 'type': 'EPS', 'value': float(val)})

                if records:
                    return records
        except Exception:
            pass

    # 拋出異常以阻止 Streamlit 記錄失敗快取，防範 Failure Cache Poisoning
    raise RuntimeError(f"Failed to fetch financials for {stock_id}")

@st.cache_data(ttl=86400)
def fetch_finmind_monthly_revenue(stock_id, token):
    """獲取月營收數據 (首選 FinMind，失敗則自動以 yfinance 季度營收近似，支援重試與避退)"""
    import time
    import random
    # 1. 嘗試 FinMind API (最多重試 2 次)
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockMonthRevenue",
        "data_id": stock_id,
        "start_date": "2024-01-01"
    }
    if token:
        params["token"] = token
    for attempt in range(2):
        try:
            r = requests.get(url, params=params, timeout=8)
            if r.status_code == 200:
                data = r.json().get("data", [])
                if data:
                    return data
            elif r.status_code in [402, 429]:
                time.sleep(1.0 + random.uniform(0.1, 0.5))
                continue
        except (requests.exceptions.RequestException, Exception):
            if attempt < 1:
                time.sleep(0.5 + random.uniform(0.05, 0.2))
                continue

    # 2. 備援：yfinance 季度營收轉月營收近似值
    for suffix in [".TW", ".TWO"]:
        try:
            tick = yf.Ticker(f"{stock_id}{suffix}")
            qf = tick.quarterly_financials
            if qf is None or qf.empty:
                continue
            rev_row = "Total Revenue" if "Total Revenue" in qf.index else ("Operating Revenue" if "Operating Revenue" in qf.index else None)
            if not rev_row:
                continue
            records = []
            for col_date in sorted(qf.columns):
                val = qf.loc[rev_row, col_date]
                if pd.isna(val) or float(val) <= 0:
                    continue
                quarterly_rev = float(val)
                # 將季度營收均分為 3 個月（以季末月為主月份，往前推 2 個月）
                end_month = col_date.month
                end_year = col_date.year
                for offset in range(3):
                    m = end_month - offset
                    y = end_year
                    if m <= 0:
                        m += 12
                        y -= 1
                    records.append({
                        "date": f"{y}-{m:02d}-01",
                        "revenue_year": y,
                        "revenue_month": m,
                        "revenue": quarterly_rev / 3.0,
                        "stock_id": stock_id
                    })
            if records:
                # 去重：同年月只保留最後一筆
                seen = {}
                for rec in records:
                    key = (rec["revenue_year"], rec["revenue_month"])
                    seen[key] = rec
                deduped = list(seen.values())
                return deduped
        except Exception:
            pass
    # 拋出異常以阻止 Streamlit 記錄失敗快取，防範 Failure Cache Poisoning
    raise RuntimeError(f"Failed to fetch monthly revenue for {stock_id}")


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

    # 智慧插補：若 EPS 缺失但淨利存在，以常規股本比例換算 EPS，確保軌跡計算不中斷
    if "EPS" in df_pivot.columns and "IncomeAfterTaxes" in df_pivot.columns:
        both = df_pivot.dropna(subset=["EPS", "IncomeAfterTaxes"])
        if not both.empty:
            factor = both["EPS"].iloc[0] / both["IncomeAfterTaxes"].iloc[0]
            df_pivot["EPS"] = df_pivot["EPS"].fillna(df_pivot["IncomeAfterTaxes"] * factor)
        else:
            df_pivot["EPS"] = df_pivot["EPS"].fillna(df_pivot["IncomeAfterTaxes"])
    elif "IncomeAfterTaxes" in df_pivot.columns:
        df_pivot["EPS"] = df_pivot["IncomeAfterTaxes"]

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

    # 彈性多級降級判定：當歷史資料不足3季時，自動採用2季或1季 YoY 作為參考
    if len(valid_df) < 3:
        if len(valid_df) == 2:
            eps_acc = valid_df["EPS_YoY"].iloc[-1] > valid_df["EPS_YoY"].iloc[-2]
            rev_acc = valid_df["Revenue_YoY"].iloc[-1] > valid_df["Revenue_YoY"].iloc[-2]
            margin_acc = valid_df["NetMargin"].iloc[-1] > valid_df["NetMargin"].iloc[-2]
            active = eps_acc and rev_acc and margin_acc
            eps_t2 = valid_df["EPS_YoY"].iloc[-2:].tolist()
            rev_t2 = valid_df["Revenue_YoY"].iloc[-2:].tolist()
            margin_t2 = valid_df["NetMargin"].iloc[-2:].tolist()

            trajectory = (
                f"[降級比對] EPS YoY: {eps_t2[0]:.1f}% → {eps_t2[1]:.1f}%\\n"
                f"營收 YoY: {rev_t2[0]:.1f}% → {rev_t2[1]:.1f}%\\n"
                f"淨利率: {margin_t2[0]:.1f}% → {margin_t2[1]:.1f}%"
            )
            display_text = f"✅ (EPS: {eps_t2[1]:.1f}%)" if active else f"❌ (EPS: {eps_t2[1]:.1f}%)"
            return {"active": active, "trajectory": trajectory, "display": display_text}

        elif len(valid_df) == 1:
            eps_val = valid_df["EPS_YoY"].iloc[-1]
            rev_val = valid_df["Revenue_YoY"].iloc[-1]
            margin_val = valid_df["NetMargin"].iloc[-1]
            # 單季 YoY 皆為正，且淨利率大於 30% 視為基本面優秀
            active = eps_val > 0 and rev_val > 0 and margin_val > 30
            trajectory = (
                f"[降級單季] EPS YoY: {eps_val:.1f}%\\n"
                f"營收 YoY: {rev_val:.1f}%\\n"
                f"淨利率: {margin_val:.1f}%"
            )
            display_text = f"✅ (EPS: {eps_val:.1f}%)" if active else f"❌ (EPS: {eps_val:.1f}%)"
            return {"active": active, "trajectory": trajectory, "display": display_text}

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

# --- 🚀 多線程併發加載基本面數據 ---

def get_single_stock_fundamentals(args):
    ticker, backtest_date, token = args
    stock_id = ticker.split('.')[0]
    backtest_date_str = backtest_date.strftime('%Y-%m-%d')

    # 1. 抓取數據 (使用 Cache / Fallback，若拋出異常則優雅降級為空清單，避免錯誤快取)
    try:
        financials = fetch_finmind_financials(stock_id, token)
    except Exception:
        financials = []

    try:
        monthly_rev = fetch_finmind_monthly_revenue(stock_id, token)
    except Exception:
        monthly_rev = []

    # 2. 計算基本面指標
    c33 = process_code33(financials, backtest_date_str)
    mrev = process_monthly_momentum(monthly_rev, backtest_date_str)

    return ticker, c33, mrev

def fetch_all_fundamentals(tickers, backtest_date):
    """併發加載所有股票的基本面資料"""
    results = {}
    token = get_finmind_token()
    args_list = [(ticker, backtest_date, token) for ticker in tickers]
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures_results = list(executor.map(get_single_stock_fundamentals, args_list))
    for ticker, c33, mrev in futures_results:
        results[ticker] = {
            "c33": c33,
            "mrev": mrev
        }
    return results


# --- 🧠 核心量化與動能運算輔助模組 ---

def clean_and_normalize(text):
    """
    清洗與標準化輸入字串，移除零寬度空白等隱形字元，並將全形字元轉換為半形。
    """
    # 移除零寬度空白等隱形字元
    text = re.sub(r'[\u200b-\u200d\ufeff]', '', text)
    # 將全角英數與空格轉換為半角
    res = []
    for char in text:
        code = ord(char)
        if code == 0x3000:
            res.append(' ')
        elif 0xFF01 <= code <= 0xFF5E:
            res.append(chr(code - 0xfee0))
        else:
            res.append(char)
    return "".join(res)

def calculate_market_panic_days(b_c, start_date_short, market_threshold):
    """
    計算大盤恐慌日、恐慌日期清單、動態門檻以及大盤狀態描述。
    """
    b_short_df = pd.DataFrame(b_c.loc[start_date_short.strftime('%Y-%m-%d'):])
    b_short_df.columns = ['Close_Price']
    b_short_df['Market_Return'] = b_short_df['Close_Price'].pct_change() * 100
    panic_days = b_short_df[b_short_df['Market_Return'] <= -market_threshold]
    total_panic_days = len(panic_days)
    panic_dates_list = panic_days.index.tolist()

    dynamic_threshold = 55.0 if total_panic_days <= 5 else (70.0 if total_panic_days <= 15 else 80.0)
    level_desc = "⚡ 極短線回檔（採取寬鬆防守標準，勝率過半即合格）" if total_panic_days <= 5 else ("⚖️ 標準波段修正（採取黃金 70% 機構防守標準）" if total_panic_days <= 15 else "🚨 空頭大屠殺 / 系統性風險（採取極嚴苛 80% 沙裡淘金標準）")
    return b_short_df, panic_dates_list, total_panic_days, dynamic_threshold, level_desc

def check_minervini_trend_template(s_series_raw):
    """
    檢測米奈爾維尼 (Mark Minervini) 的 7 大趨勢模板核心準則。
    回傳: (is_trend_template, bias_50, cond5)
    """
    p_now = s_series_raw.iloc[-1]
    if len(s_series_raw) >= 50:
        ma50_val = s_series_raw.rolling(window=50).mean().iloc[-1]
        bias_50 = ((p_now - ma50_val) / ma50_val) * 100
    else:
        bias_50 = 0.0

    cond5 = False
    is_trend_template = False

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

    return is_trend_template, bias_50, cond5

def calculate_relative_strength(s_series_raw, b_c_all):
    """
    計算個股相對強度 (RS) 指標與 IBD 絕對/相對強度分數。
    回傳: (ibd, rel_strength_0050, is_rs_recovering, rel_alpha_rs_series, abs_rs_series)
    """
    if len(s_series_raw) >= 253:
        s_3m = s_series_raw.shift(63)
        s_6m = s_series_raw.shift(126)
        s_9m = s_series_raw.shift(189)
        s_1y = s_series_raw.shift(252)
        abs_rs_series = ((s_series_raw/s_3m*2) + (s_series_raw/s_6m) + (s_series_raw/s_9m) + (s_series_raw/s_1y)) / 5 * 100
        ibd = abs_rs_series.iloc[-1]

        # 對 0050 相對 RS 動能
        b_c_aligned_to_stock = b_c_all.reindex(s_series_raw.index).ffill()
        rel_val = s_series_raw / b_c_aligned_to_stock
        rel_3m = rel_val.shift(63)
        rel_6m = rel_val.shift(126)
        rel_9m = rel_val.shift(189)
        rel_1y = rel_val.shift(252)
        rel_alpha_rs_series = ((rel_val/rel_3m*2) + (rel_val/rel_6m) + (rel_val/rel_9m) + (rel_val/rel_1y)) / 5 * 100

        rel_alpha_rs_now = rel_alpha_rs_series.iloc[-1]
        alpha_sma5_now = rel_alpha_rs_series.rolling(5).mean().iloc[-1]
        is_rs_recovering = rel_alpha_rs_series.iloc[-1] > rel_alpha_rs_series.iloc[-2] and rel_alpha_rs_series.iloc[-1] > alpha_sma5_now

        rel_strength_0050 = rel_alpha_rs_now - 100
    else:
        ibd = 0.0
        rel_strength_0050 = 0.0
        is_rs_recovering = False
        rel_alpha_rs_series = pd.Series(index=s_series_raw.index, dtype=float)
        abs_rs_series = pd.Series(index=s_series_raw.index, dtype=float)

    return ibd, rel_strength_0050, is_rs_recovering, rel_alpha_rs_series, abs_rs_series

def calculate_resilience(s_series_raw, panic_dates_list, b_short_df, total_panic_days):
    """
    計算個股在市場恐慌日的抗跌韌性得分。
    修正新股分母偏差：動態計算個股實際有交易資料的恐慌天數作為分母。
    """
    s_ret = s_series_raw.pct_change() * 100
    if total_panic_days > 0:
        # 僅在個股有交易日期的恐慌日中進行比對
        valid_panic_dates = [d for d in panic_dates_list if d in s_ret.index and d in b_short_df.index]
        if valid_panic_dates:
            outperform = np.sum(s_ret.loc[valid_panic_dates] > b_short_df.loc[valid_panic_dates, 'Market_Return'])
            resilience = (outperform / len(valid_panic_dates) * 100)
        else:
            outperform = 0
            resilience = 100.0  # 若無有效交易數據，預設為 100.0
    else:
        outperform = 0
        resilience = 100.0
    return resilience, outperform, s_ret

def detect_vcp_signals(s_series_raw, df_all, df_vol, ticker, cond5, rel_alpha_rs_series, abs_rs_series, is_rs_recovering):
    """
    計算 VCP 動態波幅與成交量收縮信號。
    回傳: vcp_status_final (含雙軌領先/背離前綴與最終 VCP 狀態)
    """
    is_price_new_high = False
    is_alpha_new_high = False
    is_abs_rs_new_high = False
    is_alpha_lagging = False
    is_abs_rs_lagging = False

    is_vcp_80 = False
    is_vcp_90 = False
    is_quiet_platform = False

    p_now = s_series_raw.iloc[-1]

    if len(s_series_raw) >= 253:
        is_price_new_high = p_now >= s_series_raw.iloc[-31:-1].max()
        is_alpha_new_high = rel_alpha_rs_series.iloc[-1] >= rel_alpha_rs_series.iloc[-31:-1].max()
        is_abs_rs_new_high = abs_rs_series.iloc[-1] >= abs_rs_series.iloc[-31:-1].max()

        is_alpha_lagging = rel_alpha_rs_series.iloc[-1] < rel_alpha_rs_series.iloc[-31:-1].max()
        is_abs_rs_lagging = abs_rs_series.iloc[-1] < abs_rs_series.iloc[-31:-1].max()

        # 1. ATR 與價格壓縮比例 (a_ratio)
        high_s = df_all['High'][ticker].reindex(s_series_raw.index).ffill()
        low_s = df_all['Low'][ticker].reindex(s_series_raw.index).ffill()
        close_prev = s_series_raw.shift(1)
        tr = pd.concat([
            high_s - low_s,
            (high_s - close_prev).abs(),
            (low_s - close_prev).abs()
        ], axis=1).max(axis=1)

        atr_5 = tr.rolling(5).mean().iloc[-1]
        atr_10_ma = tr.rolling(10).mean().rolling(10).mean().iloc[-1]
        atr_20_ma = tr.rolling(20).mean().rolling(20).mean().iloc[-1]

        a_ratio_10 = atr_5 / atr_10_ma if atr_10_ma > 0 else 1.0
        a_ratio_20 = atr_5 / atr_20_ma if atr_20_ma > 0 else 1.0

        # 2. Volume 縮小比例 (v_ratio)
        s_vol = df_vol[ticker].dropna().reindex(s_series_raw.index).ffill()
        vol_5 = s_vol.rolling(5).mean().iloc[-1]
        vol_10 = s_vol.rolling(10).mean().iloc[-1]
        vol_20 = s_vol.rolling(20).mean().iloc[-1]

        v_ratio_10 = vol_5 / vol_10 if vol_10 > 0 else 1.0
        v_ratio_20 = vol_5 / vol_20 if vol_20 > 0 else 1.0

        # 3. 波動率緊縮
        roll_std5 = s_series_raw.rolling(5).std(ddof=0)
        roll_mean5 = s_series_raw.rolling(5).mean()
        cv_5 = roll_std5 / roll_mean5
        cv_5_ma20 = cv_5.rolling(20).mean().iloc[-1]
        cv_5_now = cv_5.iloc[-1]
        is_tight_cv = cv_5_now < cv_5_ma20

        # VCP 狀態判斷 (對齊 TradingView 邏輯)
        is_vcp_80 = (a_ratio_20 < 0.8 or a_ratio_10 < 0.8) and (v_ratio_20 < 0.85 or v_ratio_10 < 0.85) and cond5 and is_tight_cv
        is_vcp_90 = (a_ratio_20 < 0.9 or a_ratio_10 < 0.9) and (v_ratio_20 < 0.95 or v_ratio_10 < 0.95) and cond5 and is_tight_cv
        is_quiet_platform = s_vol.rolling(3).mean().iloc[-1] < vol_20 * 0.7 and is_tight_cv

    is_div_warning = is_price_new_high and (is_alpha_lagging or is_abs_rs_lagging)
    is_abs_leading = (not is_price_new_high) and is_abs_rs_new_high
    is_alpha_leading = (not is_price_new_high) and is_alpha_new_high

    if is_vcp_80:
        struct_status = "💎 極致壓縮(80%+CV)"
    elif is_quiet_platform:
        struct_status = "💤 Dead Quiet"
    elif is_vcp_90:
        struct_status = "🔥 相對壓縮(90%+CV)"
    elif is_rs_recovering:
        struct_status = "📈 動能回復中"
    else:
        struct_status = "⏳ 區間整理"

    lead_prefix = ""
    if is_alpha_leading and is_abs_leading:
        lead_prefix = "🌟 雙軌領先 | "
    elif is_alpha_leading:
        lead_prefix = "🌟 Alpha領先 | "
    elif is_abs_leading:
        lead_prefix = "🌟 RS領先 | "
    elif is_div_warning:
        lead_prefix = "⚠️ 雙軌背離 | "

    return lead_prefix + struct_status

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

# --- ⚙️ 側邊欄控制面板 ---
with st.sidebar.form("sepa_integrated_form"):
    st.header("⚙️ 雙軌指標參數設定")

    default_pool = (
        "2337.TW,旺宏\n3028.TW,增你強\n3550.TW,聯穎\n6187.TWO,萬潤\n3037.TW,欣興\n3017.TW,奇鋐\n"
        "2478.TW,大毅\n4749.TWO,新應材\n3680.TWO,家登\n8021.TW,尖點\n3481.TW,群創\n"
        "8438.TW,昶昕\n3691.TWO,碩禾\n2423.TW,固緯\n8147.TWO,正淩\n8028.TW,昇陽半導體\n6716.TWO,應廣\n2428.TW,興勤\n5284.TW,JPP-KY\n"
        "2493.TW,揚博\n3023.TW,信邦\n6672.TW,騰輝電子\n3044.TW,健鼎\n3022.TW,威強電\n3577.TWO,泓格\n3305.TW,昇貿"
    )
    stock_input = st.text_area("股票清單 (支援複製貼上！系統會自動過濾國籍、財報等非代號雜訊)", value=default_pool, height=300)

    st.subheader("【短線逆風照妖鏡參數】")
    lookback_days = st.number_input("自訂照妖鏡觀察天數", min_value=5, max_value=365, value=45, step=1)
    market_threshold = st.slider("大盤恐慌日定義 (單日跌幅 %)", min_value=0.5, max_value=2.5, value=1.0, step=0.1)

    show_fundamental = st.checkbox("🔬 顯示基本面分析標籤", value=False, help="開啟後，下方象限列表個股名稱下方將顯示 Code 33 與 月營收之詳細徽章")

    st.subheader("【🕒 歷史回溯與績效回測】")
    backtest_date = st.date_input("選擇回溯基準日 (以此日視為當時的今天)", value=datetime.today())
    holding_days = st.number_input("回溯後預計持有天數 (交易日)", min_value=1, max_value=120, value=20, step=1)

    is_backtesting = backtest_date < datetime.today().date()
    submit_btn = st.form_submit_button("🚀 執行雙軌交叉選股分析")

# --- 🔌 API 連線與資料時間診斷 ---
st.sidebar.markdown("---")
with st.sidebar.expander("🔌 數據引擎與資料時間診斷", expanded=True):
    # 初始化 session state 中的 token
    if "finmind_token" not in st.session_state:
        try:
            st.session_state.finmind_token = st.secrets.get("FINMIND_TOKEN", "")
        except Exception:
            st.session_state.finmind_token = ""

    # 使用 key="finmind_token" 讓 Streamlit 自動同步並更新 session state
    token_input = st.text_input(
        "🔑 FinMind Token (選填)",
        type="password",
        key="finmind_token",
        help="輸入您的 FinMind 個人 Token 可大幅提升每日 API 讀取額度，避免營收資料退回 yfinance 備援狀態。"
    )

    if token_input:
        st.success("🟢 Token 已載入！已啟用個人 API 額度")
    else:
        st.info("💡 目前使用匿名限制模式")

    # 檢測 token 是否變更，若變更則清空快取
    if "last_finmind_token" not in st.session_state:
        st.session_state.last_finmind_token = st.session_state.finmind_token
    elif st.session_state.last_finmind_token != st.session_state.finmind_token:
        st.session_state.last_finmind_token = st.session_state.finmind_token
        st.cache_data.clear()

    st.caption("系統會自動測試 API 連線並回報最新數據更新時間：")

    @st.cache_data(ttl=1800) # 每30分鐘重新診斷一次，全域快取節省 Token
    def run_fast_diagnose(token):
        diag_info = {}
        # 1. FinMind (使用聯邦觀測：併發查詢八大龍頭，取其最新月份以防單一公司延遲)
        try:
            url = "https://api.finmindtrade.com/api/v4/data"
            test_tickers = ["2330", "2303", "2317", "2454", "2382", "2301", "3711", "2409"]
            latest_year = 0
            latest_month = 0
            
            def fetch_single(data_id):
                params = {
                    "dataset": "TaiwanStockMonthRevenue",
                    "data_id": data_id,
                    "start_date": (datetime.today() - timedelta(days=90)).strftime('%Y-%m-%d')
                }
                if token:
                    params["token"] = token
                try:
                    r = requests.get(url, params=params, timeout=3)
                    if r.status_code == 200:
                        data = r.json().get("data", [])
                        if data:
                            return int(data[-1]['revenue_year']), int(data[-1]['revenue_month'])
                    elif r.status_code in [402, 429]:
                        return r.status_code, None
                except Exception:
                    pass
                return None, None

            # 併發查詢 8 檔以提升診斷速度
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(fetch_single, test_tickers))
            
            has_limit_error = False
            limit_code = None
            for y, m in results:
                if y in [402, 429]:
                    has_limit_error = True
                    limit_code = y
                    break
                if y is not None and m is not None:
                    if (y > latest_year) or (y == latest_year and m > latest_month):
                        latest_year = y
                        latest_month = m
            
            if has_limit_error:
                if limit_code == 402:
                    diag_info["FinMind (月營收)"] = "🔴 額度超限/付費限制 (HTTP 402)"
                else:
                    diag_info["FinMind (月營收)"] = "🔴 速率限制 (HTTP 429)"
            elif latest_year > 0:
                diag_info["FinMind (月營收)"] = f"🟢 正常 (最新: {latest_year}/{latest_month})"
            else:
                diag_info["FinMind (月營收)"] = "🟡 無回傳資料"
        except Exception as e:
            diag_info["FinMind (月營收)"] = f"🔴 系統異常: {type(e).__name__}"

        # 2. yfinance (改用歷史價格測試，避開有依賴問題的 get_earnings_dates)
        try:
            tick = yf.Ticker("2330.TW")
            h = tick.history(period="1d")
            if not h.empty:
                diag_info["yfinance (價格與財報)"] = f"🟢 正常 (最新交易日: {h.index[-1].strftime('%Y-%m-%d')})"
            else:
                diag_info["yfinance (價格與財報)"] = "🟡 無交易數據"
        except Exception as e:
            diag_info["yfinance (價格與財報)"] = f"🔴 連線失敗: {type(e).__name__}"

        return diag_info

    diag_results = run_fast_diagnose(st.session_state.finmind_token)
    for name, status in diag_results.items():
        st.write(f"**{name}**")
        st.write(status)


# --- clean_and_normalize 已合併回主程式 ---


def get_stocks_pool(text):
    """智能掃描器：自動分割並比對輸入文字與 STOCK_DICT 名稱，支援多種分隔符號並防範模糊比對誤判"""
    pool = []

    # 先清理與標準化輸入字串 (如去除手機輸入可能產生的全角字元或零寬度空白)
    cleaned_text = clean_and_normalize(text)

    # 支援新行、半角逗號、全角逗號、空格、分號等分隔符
    tokens = re.split(r'[\n\r,，;；\s\t]+', cleaned_text)

    for token in tokens:
        token = token.strip()
        if not token:
            continue

        # 1. 第一優先：精確匹配股票代號 (四至六位數字)
        if token.isdigit() and 4 <= len(token) <= 6:
            found = False
            for suffix in ["", ".TW", ".TWO"]:
                target = f"{token}{suffix}" if suffix else token
                if target in STOCK_DICT:
                    pool.append({"id": target, "name": STOCK_DICT[target]})
                    found = True
                    break
            if found:
                continue

        # 2. 第二優先：名稱比對
        found_name = False
        clean_token = token.upper()

        exact_matches = []
        substring_matches = []

        for code, official_name in STOCK_DICT.items():
            off_name_upper = official_name.upper()
            if clean_token == off_name_upper:
                exact_matches.append({"id": code, "name": official_name})
            elif clean_token in off_name_upper:
                substring_matches.append({"id": code, "name": official_name})

        if exact_matches:
            pool.append(exact_matches[0])
            found_name = True
        elif substring_matches:
            substring_matches.sort(key=lambda x: len(x["name"]))
            pool.append(substring_matches[0])
            found_name = True

        if not found_name:
            # 備援：若 token 含有非純數字（例如 "2330.TW" 或 "2330台積電"），嘗試用 Regex 提取代號
            code_match = re.search(r'\d{4,6}', token)
            if code_match:
                code = code_match.group()
                found = False
                for suffix in ["", ".TW", ".TWO"]:
                    target = f"{code}{suffix}" if suffix else code
                    if target in STOCK_DICT:
                        pool.append({"id": target, "name": STOCK_DICT[target]})
                        found = True
                        break
                if found:
                    continue

            st.sidebar.warning(f"⚠️ 找不到此標的: {token}")

    # 去除重複
    seen = set()
    unique_pool = []
    for item in pool:
        if item['id'] not in seen:
            seen.add(item['id'])
            unique_pool.append(item)

    return unique_pool

@st.cache_data(ttl=600)
def fetch_official_latest_prices(latest_date):
    """
    從證交所(MI_INDEX)與櫃買中心官方 OpenAPI 下載指定日期的最精確收盤價與成交量，
    用來修補 yfinance 最新一天的 NaN 或延遲數據，啟用 SSL 憑證安全驗證。
    """
    date_str = latest_date.strftime('%Y%m%d')
    headers = {"User-Agent": "Mozilla/5.0"}
    prices = {}

    # 1. 抓取 TWSE (上市)
    try:
        url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={date_str}&type=ALL"
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            data = r.json()
            if "tables" in data:
                for tbl in data["tables"]:
                    data_rows = tbl.get("data", [])
                    if len(data_rows) > 500:
                        for row in data_rows:
                            if len(row) > 8:
                                code = str(row[0]).strip()
                                if code.isdigit() and len(code) == 4:
                                    close_str = str(row[8]).replace(',', '').strip()
                                    vol_str = str(row[2]).replace(',', '').strip()
                                    try:
                                        prices[f"{code}.TW"] = {
                                            "Close": float(close_str) if close_str and close_str != '--' else None,
                                            "Volume": float(vol_str) if vol_str else None
                                        }
                                    except ValueError:
                                        pass
    except Exception:
        pass

    # 若 MI_INDEX 抓取失敗，再嘗試 TWSE OpenAPI
    if not any(k.endswith(".TW") for k in prices):
        try:
            url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
            r = requests.get(url, headers=headers, timeout=8)
            if r.status_code == 200:
                for item in r.json():
                    code = item.get("Code", "").strip()
                    close_str = item.get("ClosingPrice", "").strip()
                    vol_str = item.get("TradeVolume", "").strip()
                    if code and len(code) == 4:
                        try:
                            prices[f"{code}.TW"] = {
                                "Close": float(close_str) if close_str else None,
                                "Volume": float(vol_str) if vol_str else None
                            }
                        except ValueError:
                            pass
        except Exception:
            pass

    # 2. 抓取 TPEx (上櫃)
    try:
        url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            for item in r.json():
                code = item.get("SecuritiesCompanyCode", "").strip()
                close_str = item.get("Close", "").strip()
                vol_str = item.get("TradingShares", "").strip()
                if code and len(code) == 4:
                    try:
                        prices[f"{code}.TWO"] = {
                            "Close": float(close_str) if close_str else None,
                            "Volume": float(vol_str) if vol_str else None
                        }
                    except ValueError:
                        pass
    except Exception:
        pass

    return prices

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

                # 優先使用還原收盤價 (Adj Close)，若不存在（如啟用 auto_adjust=True 時）則使用 Close
                df_adj = df_all['Adj Close'] if 'Adj Close' in df_all.columns.levels[0] else df_all['Close']
                df_vol = df_all['Volume']

                # 只有最新一天才需要嘗試從官方 API 修補（若是回溯歷史，yfinance 的歷史資料已完全正常，無需修補）
                if not is_backtesting and not df_adj.empty:
                    latest_date = df_adj.index[-1]
                    # 只有當最新一天的 Close 中有任何 NaN 時，才去抓取官方 API
                    if df_adj.loc[latest_date].isna().any():
                        with st.spinner("🚨 正在向證交所與櫃買中心獲取最新官方收盤行情修補..."):
                            official_quotes = fetch_official_latest_prices(latest_date)
                            if official_quotes:
                                for ticker in df_adj.columns:
                                    if ticker in official_quotes:
                                        p_info = official_quotes[ticker]
                                        if p_info.get("Close") is not None:
                                            df_adj.loc[latest_date, ticker] = p_info["Close"]
                                        if p_info.get("Volume") is not None:
                                            df_vol.loc[latest_date, ticker] = p_info["Volume"]

                # 智慧補值與 ffill 備援，防範個別無交易量或官方沒回傳的股票
                if 'Open' in df_all.columns.levels[0]:
                    df_adj = df_adj.fillna(df_all['Open'])
                if 'High' in df_all.columns.levels[0]:
                    df_adj = df_adj.fillna(df_all['High'])
                df_adj = df_adj.ffill()

                b_c_all = df_adj["0050.TW"].dropna()
                if is_backtesting:
                    b_c = b_c_all.loc[:end_date.strftime('%Y-%m-%d')]
                else:
                    b_c = b_c_all

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

                    # 1. 計算大盤恐慌日與動態門檻
                    b_short_df, panic_dates_list, total_panic_days, dynamic_threshold, level_desc = calculate_market_panic_days(
                        b_c, start_date_short, market_threshold
                    )

                    # 🚀 多線程併發加載基本面數據 (僅當使用者開啟基本面分析標籤時執行，未開啟時跳過以發揮百檔極速)
                    if show_fundamental:
                        tickers_for_fundamentals = [stock["id"] for stock in STOCKS_POOL]
                        FUNDAMENTAL_RESULTS = fetch_all_fundamentals(tickers_for_fundamentals, backtest_date)
                    else:
                        FUNDAMENTAL_RESULTS = {}

                    integrated_results = []
                    skipped_stocks = []

                    for stock in STOCKS_POOL:
                        ticker = stock["id"]

                        if ticker not in df_adj.columns:
                            skipped_stocks.append(stock["name"])
                            continue

                        s_series_raw_all = df_adj[ticker].dropna()
                        s_series_raw = s_series_raw_all.loc[:end_date.strftime('%Y-%m-%d')] if is_backtesting else s_series_raw_all

                        if s_series_raw.empty:
                            skipped_stocks.append(stock["name"])
                            continue

                        p_now = s_series_raw.iloc[-1]

                        # 2. 檢測 Minervini 趨勢模板
                        is_trend_template, bias_50, cond5 = check_minervini_trend_template(s_series_raw)

                        # 3. 計算相對強度與 IBD 指標
                        ibd, rel_strength_0050, is_rs_recovering, rel_alpha_rs_series, abs_rs_series = calculate_relative_strength(
                            s_series_raw, b_c_all
                        )

                        # 4. 計算抗跌韌性得分
                        resilience, outperform, s_ret = calculate_resilience(
                            s_series_raw, panic_dates_list, b_short_df, total_panic_days
                        )

                        # 5. 偵測 VCP 信號與動能狀態標籤
                        vcp_status_final = detect_vcp_signals(
                            s_series_raw, df_all, df_vol, ticker, cond5, rel_alpha_rs_series, abs_rs_series, is_rs_recovering
                        )

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

                        integrated_results.append({
                            "ticker": ticker,
                            "股票代號": ticker.split(".")[0],
                            "股票名稱": display_name,
                            "原始名稱": stock['name'],
                            "趨勢模板": "✅" if is_trend_template else "❌",
                            "動能狀態判定": vcp_status_final,
                            "🧪 Code 33": c33_display,
                            "🚀 月營收爆發": mrev_display,
                            "50MA乖離率(%)": bias_50,
                            "IBD式 絕對分數": ibd, "對比 0050 超額強度": rel_strength_0050,
                            "短線抗跌韌性分數": resilience, "逆風勝率": f"{outperform} / {total_panic_days} 天",
                            "逆風上漲天數": f"{np.sum(s_ret.reindex(panic_dates_list) > 0)} 天",
                            perf_col_key: future_return
                        })

                    df_final = pd.DataFrame(integrated_results).sort_values("對比 0050 超額強度", ascending=False)

                    cols = df_final.columns.tolist()
                    perf_col_name = f"後續{holding_days}日實際報酬(%)"

                    fundamental_cols = ["🧪 Code 33", "🚀 月營收爆發"]

                    for f_col in fundamental_cols:
                        if f_col in cols:
                            cols.remove(f_col)
                    idx_to_insert = cols.index("股票名稱") + 1
                    for f_col in reversed(fundamental_cols):
                        cols.insert(idx_to_insert, f_col)

                    if "50MA乖離率(%)" in cols:
                        cols.remove("50MA乖離率(%)")
                        cols.append("50MA乖離率(%)")
                    if perf_col_name in cols:
                        cols.remove(perf_col_name)
                        if is_backtesting:
                            # 插入在基本面欄位後面
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
                        "🧪 Code 33": st.column_config.TextColumn("🧪 Code 33", width=150, help="連續三季的 EPS YoY、營收 YoY、淨利率是否同步呈現遞增趨勢。✅=三加速確認"),
                        "🚀 月營收爆發": st.column_config.TextColumn("🚀 月營收爆發", width=150, help="月營收創12M新高 或 YoY連2月加速")
                    }
                    if is_backtesting:
                        column_config_dict[perf_col_name] = st.column_config.NumberColumn(f"🎯 後續{holding_days}日報酬", format="%.2f%%")
                    else:
                        column_config_dict[perf_col_name] = st.column_config.NumberColumn("今日至今持平率", format="%.2f%%")

                    display_df = df_final.drop(columns=["ticker", "原始名稱", "趨勢模板", "動能狀態判定"], errors="ignore")
                    st.dataframe(display_df, use_container_width=True, hide_index=True, column_config=column_config_dict)

                    st.divider()
                    st.subheader("🏁 Mark Minervini 流派：雙軌交叉戰略部署")

                    # 說明文字：依開關狀態而異
                    desc_lines = []
                    if show_fundamental:
                        desc_lines.append("🧪 <b>Code 33</b> = 連3季 EPS/營收/淨利率三加速&nbsp;｜&nbsp;🚀 <b>月營收</b> = 創12M新高 或 YoY連2月加速")
                        desc_lines.append(
                            "🔬 <b>馬克的 SEPA 基本面心法備註</b>：<br>"
                            "&nbsp;&nbsp;• <b>「技術面決定進場時機，基本面決定漲幅高度」</b>：馬克指出，90% 的超級飆股在發動主升段前，其盈餘與營收均呈現『加速增長』的特徵。<br>"
                            "&nbsp;&nbsp;• <b>Code 33 三加速</b>：代表連續 3 季 EPS YoY、營收 YoY、淨利率同步攀升，是機構資金（Institutional Money）鎖定吃貨的最強護城河。<br>"
                            "&nbsp;&nbsp;• <b>月營收爆發</b>：在季報公佈前，單月營收創 12 個月新高或 YoY 連續加速，是領先確認終端銷售動能爆發的即時信號。"
                        )

                    if desc_lines:
                        st.markdown(
                            "<div style='background-color:#f6ffed; border:1px solid #b7eb8f; padding:12px; border-radius:8px; margin-bottom:15px;'>"
                            "<span style='color:#389e0d; font-size:0.86em; line-height:1.6;'>"
                            "💡 <b>指標徽章說明與馬克心法備註</b>（懸停可檢視詳細數據軌跡）：<br><br>" + "<br><br>".join(desc_lines) +
                            "</span></div>",
                            unsafe_allow_html=True
                        )
                    else:
                        st.caption(f"💡 括號內為 50MA 乖離率(%)。右側標註為【後續 {holding_days} 日回測實際報酬率】。可在左側開啟「🔬 顯示基本面分析標籤」查看更多維度資訊。")

                    true_leaders = df_final[(df_final["對比 0050 超額強度"] > 0) & (df_final["短線抗跌韌性分數"] >= dynamic_threshold)]
                    momentum_only = df_final[(df_final["對比 0050 超額強度"] > 0) & (df_final["短線抗跌韌性分數"] < dynamic_threshold)]
                    defensive_only = df_final[(df_final["對比 0050 超額強度"] <= 0) & (df_final["短線抗跌韌性分數"] >= dynamic_threshold)]
                    laggards = df_final[(df_final["對比 0050 超額強度"] <= 0) & (df_final["短線抗跌韌性分數"] < dynamic_threshold)]

                    def format_stocks(df, show_perf=False):
                        if df.empty:
                            return "無"
                        lines = []
                        for _, row in df.iterrows():
                            # 50MA 乖離率：括號格式，高乖離染紅
                            bias_val = row['50MA乖離率(%)']
                            if bias_val >= 30.0:
                                bias_str = f"(<span style='color:#cf1322;font-weight:bold;'>{bias_val:.1f}%</span>)"
                            else:
                                bias_str = f"({bias_val:.1f}%)"

                            # 處置股：直接 inline 顯示起迄日期（手機無懸停，不用 title）
                            disp_info = DISPOSITION_MAP.get(row['股票代號'])
                            if disp_info:
                                period_text = disp_info['period'] if disp_info.get('period') else ""
                                disp_str = (
                                    f" <span style='color:#e74c3c;font-weight:600;'>"
                                    f"🚨 處置中({period_text})</span>"
                                )
                            else:
                                disp_str = ""

                            # 回測績效：inline 彩色箭頭
                            if show_perf:
                                ret_val = row[perf_col_name]
                                if ret_val > 0:
                                    perf_str = f" <span style='color:#389e0d;font-weight:bold;'>▲ {ret_val:.1f}%</span>"
                                elif ret_val < 0:
                                    perf_str = f" <span style='color:#cf1322;font-weight:bold;'>▼ {ret_val:.1f}%</span>"
                                else:
                                    perf_str = f" <span style='color:#888;'>— 0.0%</span>"
                            else:
                                perf_str = ""

                            # 主行：經典格式 ✅/❌ 股名 【動能狀態】 (50MA%) 🚨處置中 ▲報酬
                            status_str = row['動能狀態判定']
                            main_line = (
                                f"{row['趨勢模板']} <b>{row['原始名稱']}</b> "
                                f"【{status_str}】 {bias_str}{disp_str}{perf_str}"
                            )

                            # 子行（依開關狀態輸出基本面徽章 + 折疊詳細軌跡）
                            sub_badges_list = []
                            details_lines = []
                            ticker = row["ticker"]
                            fund = FUNDAMENTAL_RESULTS.get(ticker, {})

                            if show_fundamental:
                                # 🧪 Code 33
                                c33 = fund.get("c33", {})
                                if c33.get("active", False):
                                    sub_badges_list.append(
                                        f'<span style="background:#e6f7ff;color:#0050b3;border:1px solid #91d5ff;'
                                        f'padding:1px 8px;border-radius:10px;font-size:0.82em;font-weight:bold;'
                                        f'margin-right:5px;">🧪 Code 33</span>'
                                    )
                                    details_lines.append(f"🧪 <b>Code 33 加速數據：</b><br>" + c33.get("trajectory", "").replace("\\n", "<br>"))

                                # 🚀 月營收
                                mrev = fund.get("mrev", {})
                                mrev_12h = mrev.get("is_12m_high", False)
                                mrev_acc = mrev.get("is_accelerating", False)
                                if mrev_12h and mrev_acc:
                                    sub_badges_list.append(
                                        f'<span style="background:#f6ffed;color:#389e0d;border:1px solid #b7eb8f;'
                                        f'padding:1px 8px;border-radius:10px;font-size:0.82em;font-weight:bold;'
                                        f'margin-right:5px;">🚀 月營收爆發</span>'
                                    )
                                elif mrev_12h:
                                    sub_badges_list.append(
                                        f'<span style="background:#f6ffed;color:#389e0d;border:1px solid #b7eb8f;'
                                        f'padding:1px 8px;border-radius:10px;font-size:0.82em;font-weight:bold;'
                                        f'margin-right:5px;">🚀 營收新高</span>'
                                    )
                                elif mrev_acc:
                                    sub_badges_list.append(
                                        f'<span style="background:#f6ffed;color:#389e0d;border:1px solid #b7eb8f;'
                                        f'padding:1px 8px;border-radius:10px;font-size:0.82em;font-weight:bold;'
                                        f'margin-right:5px;">🚀 營收YoY加速</span>'
                                    )
                                if mrev_12h or mrev_acc:
                                    details_lines.append(f"🚀 <b>月營收動能軌跡：</b><br>" + mrev.get("trajectory", "").replace("\\n", "<br>"))


                            # 用 div 包裹主行，避免 markdown * 與 HTML 混排錯位
                            item_html = f"<div style='margin-bottom:10px;line-height:1.6;font-size:0.95em;'>"
                            item_html += f"<div>• {main_line}</div>"

                            # 徽章子行
                            if sub_badges_list:
                                badge_html = "".join(sub_badges_list)
                                item_html += (
                                    f"<div style='margin:2px 0 0 20px;line-height:2;opacity:0.95;'>"
                                    f"<span style='color:#bbb;font-size:0.8em;margin-right:4px;'>└</span>"
                                    f"{badge_html}</div>"
                                )

                            # 折疊面板：點擊展開詳細軌跡（取代 title 懸停，手機友善）
                            if show_fundamental and details_lines:
                                details_content = "<br>".join(details_lines)
                                item_html += (
                                    f"<details style='margin:4px 0 2px 20px;font-size:0.82em;'>"
                                    f"<summary style='cursor:pointer;outline:none;color:#8c8c8c;font-size:0.9em;'>🔬 點擊展開詳細軌跡</summary>"
                                    f"<div style='padding:6px 10px;margin-top:4px;border-left:2px solid rgba(128,128,128,0.3);line-height:1.4;color:inherit;background:rgba(128,128,128,0.05);border-radius:4px;'>{details_content}</div>"
                                    f"</details>"
                                )

                            item_html += "</div>"
                            lines.append(item_html)

                        return "\n".join(lines)

                    c1, c2 = st.columns(2)
                    c1.success(f"### 👑 第一象限：逆風真龍頭 ({len(true_leaders)} 檔)"); c1.markdown(format_stocks(true_leaders, is_backtesting), unsafe_allow_html=True); c1.caption("👉 戰略部署：長線動能擊敗大盤，且短線抗跌表現達到當前動態合格線以上。隨時注意 VCP 出量突破。")
                    c1.info(f"### 🚀 第二象限：高 Beta 攻擊兵 ({len(momentum_only)} 檔)"); c1.markdown(format_stocks(momentum_only, is_backtesting), unsafe_allow_html=True); c1.caption("👉 戰略部署：長線極強，但修正波動高於大盤. 一旦大盤止穩，這群股票往往是右側出量追擊的首選。")
                    c2.warning(f"### 🛡️ 第三象限：資金避風港 ({len(defensive_only)} 檔)"); c2.markdown(format_stocks(defensive_only, is_backtesting), unsafe_allow_html=True); c2.caption("👉 戰略部署：短線極度抗跌，長線動能尚未完全追上。若有打打底完成標的，高抗跌意味主力在低檔死守，值得關注！")
                    c2.error(f"### 🚨 第四象限：無情剔除名單 ({len(laggards)} 檔)"); c2.markdown(format_stocks(laggards, is_backtesting), unsafe_allow_html=True); c2.caption("👉 戰略部署：長短線皆跑輸大盤，在馬克系統中屬於弱勢標的，建議審慎評估資金配置與汰弱留強。")

        except Exception as e:
            st.error(f"數據錯誤: {e}")
