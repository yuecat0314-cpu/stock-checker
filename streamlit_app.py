import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import json, os, unicodedata
from datetime import datetime
import pytz

st.set_page_config(page_title="高配当株 監視＆3軸診断", layout="wide", page_icon="📈")
WATCHLIST_FILE = "watchlist.json"
JPX_MASTER_FILE = "jpx_master.csv"
JST = pytz.timezone('Asia/Tokyo')

STATUS_OPTS = ["監視", "保有", "趣味"]

def norm_c(c):
    return unicodedata.normalize("NFKC", str(c)).strip().upper()

@st.cache_data
def load_jpx_master():
    if os.path.exists(JPX_MASTER_FILE):
        try:
            df = pd.read_csv(JPX_MASTER_FILE, dtype={"銘柄コード": str})
            df["銘柄コード"] = df["銘柄コード"].str.strip()
            return df
        except Exception:
            pass
    return pd.DataFrame(columns=["銘柄コード", "銘柄名称", "商品分類", "市場区分", "業種"])

jpx_df = load_jpx_master()

jpx_options = []
if not jpx_df.empty:
    for _, row in jpx_df.iterrows():
        c_raw = str(row["銘柄コード"]).strip()
        n_val = str(row["銘柄名称"]).strip()
        jpx_options.append(f"{c_raw} - {n_val}")

def get_sym(code):
    clean_c = norm_c(code)
    base_c = clean_c[:4]
    return f"{base_c}.T"

name_map = {}
if not jpx_df.empty:
    for _, row in jpx_df.iterrows():
        c_raw = str(row["銘柄コード"]).strip()
        c_4 = c_raw[:4]
        n_val = str(row["銘柄名称"]).strip()
        name_map[c_raw] = n_val
        name_map[c_4] = n_val

def get_company_name(code):
    c_clean = norm_c(code)
    if c_clean in name_map:
        return name_map[c_clean]
    if c_clean[:4] in name_map:
        return name_map[c_clean[:4]]
    return code

def get_dividend_data(code, info_dict, cur_price, ticker_obj=None):
    if not cur_price or pd.isna(cur_price) or cur_price <= 0:
        return 0.0, 0.0, 0.0, "N/A", None

    div_y = 0.0
    annual_d = 0.0

    raw_y = info_dict.get("dividendYield")
    if raw_y is not None and not pd.isna(raw_y) and float(raw_y) > 0:
        raw_val = float(raw_y)
        div_y = raw_val * 100 if raw_val < 0.20 else raw_val
        annual_d = (div_y / 100.0) * float(cur_price)
    
    if div_y == 0.0:
        d_rate = info_dict.get("dividendRate") or info_dict.get("trailingAnnualDividendRate")
        if d_rate and not pd.isna(d_rate) and float(d_rate) > 0:
            annual_d = float(d_rate)
            div_y = (annual_d / float(cur_price)) * 100

    if div_y == 0.0 and ticker_obj is not None:
        try:
            div_hist = ticker_obj.dividends
            if not div_hist.empty:
                last_year_sum = float(div_hist.last("365D").sum())
                if last_year_sum > 0:
                    annual_d = last_year_sum
                    div_y = (annual_d / float(cur_price)) * 100
        except Exception:
            pass

    hist_div_actual = 0.0
    if ticker_obj is not None:
        try:
            div_hist = ticker_obj.dividends
            if not div_hist.empty:
                yearly_divs = div_hist.resample("YE").sum().dropna()
                current_year = datetime.now().year
                completed = yearly_divs[yearly_divs.index.year < current_year]
                if not completed.empty:
                    hist_div_actual = float(completed.iloc[-1])
        except Exception:
            pass

    warn_msg = None
    if div_y >= 10.0:
        warn_msg = f"🚨 利回りが{div_y:.1f}%と高水準です。念のため公式開示情報をご確認ください。"

    return div_y, annual_d, hist_div_actual, "自動取得", warn_msg

def load_watchlist_data():
    tickers, tags, details = [], {}, {}
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict):
                    for k, v in d.items():
                        c_norm = norm_c(k)
                        tickers.append(c_norm)
                        if isinstance(v, dict):
                            val = v.get("status", "監視")
                            if val in ["💼 保有中", "保有"]: val = "保有"
                            elif val in ["👀 監視中", "🎯 買いたい", "監視"]: val = "監視"
                            else: val = "趣味"
                            tags[c_norm] = val
                            details[c_norm] = {
                                "buy_price": float(v.get("buy_price", 0.0)),
                                "shares": int(v.get("shares", 0)),
                                "target_price": float(v.get("target_price", 0.0)),
                                "annual_div": float(v.get("annual_div", 0.0))
                            }
                        else:
                            val = v if v in STATUS_OPTS else "監視"
                            if val in ["💼 保有中", "保有"]: val = "保有"
                            elif val in ["👀 監視中", "🎯 買いたい", "監視"]: val = "監視"
                            else: val = "趣味"
                            tags[c_norm] = val
                            details[c_norm] = {"buy_price": 0.0, "shares": 0, "target_price": 0.0, "annual_div": 0.0}
                elif isinstance(d, list):
                    for c in d:
                        c_norm = norm_c(c)
                        tickers.append(c_norm)
                        tags[c_norm] = "監視"
                        details[c_norm] = {"buy_price": 0.0, "shares": 0, "target_price": 0.0, "annual_div": 0.0}
        except Exception:
            pass
    cln = list(dict.fromkeys(tickers))
    for c in cln:
        if c not in tags: tags[c] = "監視"
        if c not in details: details[c] = {"buy_price": 0.0, "shares": 0, "target_price": 0.0, "annual_div": 0.0}
    return cln, tags, details

def save_watchlist_data(tickers, tags, details):
    cln = list(dict.fromkeys([norm_c(c) for c in tickers]))
    st.session_state.watchlist = cln
    st.session_state.company_tags = tags
    st.session_state.portfolio_details = details
    try:
        data_to_save = {}
        for c in cln:
            det = details.get(c, {"buy_price": 0.0, "shares": 0, "target_price": 0.0, "annual_div": 0.0})
            data_to_save[c] = {
                "status": tags.get(c, "監視"),
                "buy_price": det.get("buy_price", 0.0),
                "shares": det.get("shares", 0),
                "target_price": det.get("target_price", 0.0),
                "annual_div": det.get("annual_div", 0.0)
            }
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

if "watchlist" not in st.session_state:
    w, t, d = load_watchlist_data()
    st.session_state.watchlist = w
    st.session_state.company_tags = t
    st.session_state.portfolio_details = d

@st.dialog("📊 銘柄総合診断（健全性 ✕ 買い時 ✕ 配当維持力）", width="large")
def show_detail_dialog(code, name, status, cur_p=None, ma25_dev=None):
    sym = get_sym(code)
    st.caption(f"対象銘柄: **{name}** ({sym}) ｜ 分類: **{status}**")
    with st.spinner("財務データおよびテクニカル指標を多角解析中..."):
        try:
            t = yf.Ticker(sym)
            info = t.info
            inc = t.financials
            bal = t.balance_sheet
            cf = t.cashflow
            hist = t.history(period="1y", auto_adjust=False)
            sector = info.get("sector", "") or ""
            is_financial = any(k in sector for k in ["Financial", "Bank", "Insurance"])

            h_scores, h_descs = {}, {}

            if not inc.empty and "Total Revenue" in inc.index:
                rev = inc.loc["Total Revenue"].dropna()[::-1]
                if len(rev) >= 2:
                    yoy = ((rev.iloc[-1] / rev.iloc[0]) ** (1 / (len(rev)-1)) - 1) * 100
                    h_scores['売上成長'] = 100 if yoy >= 3.0 else (80 if yoy > 0 else 30)
                    h_descs['売上成長'] = f"年平均{yoy:+.1f}%"

            raw_m = info.get("operatingMargins")
            if is_financial:
                h_scores['営業利益率'] = 85
                h_descs['営業利益率'] = "金融セクター基準"
            elif raw_m is not None and not pd.isna(raw_m):
                op_m = float(raw_m) * 100 if float(raw_m) < 1 else float(raw_m)
                h_scores['営業利益率'] = 100 if op_m >= 15 else (85 if op_m >= 10 else (65 if op_m >= 5 else 30))
                h_descs['営業利益率'] = f"{op_m:.1f}%"

            if not inc.empty and "Net Income" in inc.index:
                ni = inc.loc["Net Income"].dropna()[::-1]
                if len(ni) >= 2:
                    h_scores['純利益成長'] = 100 if (ni.iloc[-1] > ni.iloc[0] and (ni > 0).all()) else (75 if (ni > 0).all() else 35)
                    h_descs['純利益成長'] = "増益基調" if ni.iloc[-1] > ni.iloc[0] else "横ばい/減益"
                net_incomes = inc.loc["Net Income"].dropna()
                if len(net_incomes) >= 2:
                    h_scores['純利益安定'] = 100 if (net_incomes > 0).all() else 25
                    h_descs['純利益安定'] = "連続黒字" if (net_incomes > 0).all() else "赤字期あり"

            div_series = t.dividends
            if not div_series.empty:
                yearly_divs = div_series.resample("YE").sum().dropna()
                current_year = datetime.now().year
                completed_divs = yearly_divs[yearly_divs.index.year < current_year]
                if len(completed_divs) >= 2:
                    diffs = completed_divs.diff().dropna()
                    if (diffs > 0).all():
                        h_scores['配当継続力'] = 100
                        h_descs['配当継続力'] = "◎ 連続増配継続"
                    elif (diffs >= 0).all():
                        h_scores['配当継続力'] = 85
                        h_descs['配当継続力'] = "○ 非減配維持"
                    elif completed_divs.iloc[-1] >= completed_divs.iloc[0]:
                        h_scores['配当継続力'] = 65
                        h_descs['配当継続力'] = "△ 配当横ばい/波あり"
                    else:
                        h_scores['配当継続力'] = 35
                        h_descs['配当継続力'] = "✕ 過去に減配歴あり"
                elif len(yearly_divs) >= 1:
                    h_scores['配当継続力'] = 70
                    h_descs['配当継続力'] = "配当実績あり"

            raw_p = info.get("payoutRatio")
            if raw_p is not None and not pd.isna(raw_p) and float(raw_p) > 0:
                po_r = float(raw_p) * 100 if float(raw_p) < 1 else float(raw_p)
                h_scores['配当性向'] = 100 if 30 <= po_r <= 50 else (80 if (50 < po_r <= 65 or 20 <= po_r < 30) else (55 if po_r <= 80 else 25))
                h_descs['配当性向'] = f"{po_r:.1f}%"

            if not bal.empty and "Stockholders Equity" in bal.index and "Total Assets" in bal.index:
                ta = bal.loc["Total Assets"].dropna().iloc[0]
                if ta > 0:
                    eq_r = (bal.loc["Stockholders Equity"].dropna().iloc[0] / ta) * 100
                    if is_financial:
                        h_scores['自己資本比率'] = 100 if eq_r >= 10 else (80 if eq_r >= 6 else 60)
                    else:
                        h_scores['自己資本比率'] = 100 if eq_r >= 50 else (80 if eq_r >= 35 else (60 if eq_r >= 20 else 30))
                    h_descs['自己資本比率'] = f"{eq_r:.1f}%"

            if not bal.empty and "Retained Earnings" in bal.index:
                re_v = bal.loc["Retained Earnings"].dropna()[::-1]
                if len(re_v) >= 2:
                    h_scores['利益剰余金'] = 100 if re_v.iloc[-1] > re_v.iloc[0] else 40
                    h_descs['利益剰余金'] = "蓄積中" if re_v.iloc[-1] > re_v.iloc[0] else "横ばい/減少"

            h_weights = {'売上成長': 0.10, '営業利益率': 0.15, '純利益成長': 0.10, '純利益安定': 0.15, '配当継続力': 0.15, '配当性向': 0.10, '自己資本比率': 0.15, '利益剰余金': 0.10}
            avail_h = [k for k in h_weights if k in h_scores]
            h_fullness = f"{len(avail_h)}/8"
            h_score = int(sum(h_scores[k] * (h_weights[k] / sum(h_weights[k] for k in avail_h)) for k in avail_h)) if avail_h else 50
            h_rank = "S" if h_score >= 85 else ("A" if h_score >= 70 else ("B" if h_score >= 55 else "C"))

            cur_p = float(cur_p) if cur_p and not pd.isna(cur_p) else (float(hist["Close"].iloc[-1]) if not hist.empty else 0)
            div_y, annual_d, hist_actual_d, source_type, warn_div = get_dividend_data(code, info, cur_p, ticker_obj=t)

            b_scores, b_descs = {}, {}
            if not hist.empty and len(hist) >= 25:
                ma25 = hist["Close"].rolling(25).mean().iloc[-1]
                ma25_dev_val = ((cur_p - ma25) / ma25) * 100
                b_scores['25日乖離'] = 100 if ma25_dev_val <= -5 else (85 if ma25_dev_val <= -2 else (65 if ma25_dev <= 2 else (45 if ma25_dev <= 6 else 20)))
                b_descs['25日乖離'] = f"{ma25_dev_val:+.1f}%"
            elif ma25_dev is not None and not pd.isna(ma25_dev):
                b_scores['25日乖離'] = 100 if ma25_dev <= -5 else (85 if ma25_dev <= -2 else (65 if ma25_dev <= 2 else (45 if ma25_dev <= 6 else 20)))
                b_descs['25日乖離'] = f"{ma25_dev:+.1f}%"

            if not hist.empty and "High" in hist.columns:
                high_52w = float(hist["High"].max())
                drop_52w = ((cur_p - high_52w) / high_52w) * 100 if high_52w > 0 else 0
                b_scores['52週高値比'] = 100 if -25 <= drop_52w <= -10 else (75 if (-35 <= drop_52w < -25 or -10 < drop_52w <= -5) else (45 if drop_52w > -5 else 30))
                b_descs['52週高値比'] = f"{drop_52w:+.1f}% ({high_52w:,.1f}円)"

            if div_y is not None and not pd.isna(div_y) and div_y > 0:
                b_scores['利回り水準'] = 100 if div_y >= 4.5 else (85 if div_y >= 4.0 else (65 if div_y >= 3.5 else (45 if div_y >= 3.0 else 25)))
                b_descs['利回り水準'] = f"{div_y:.2f}%"

            raw_pbr = info.get("priceToBook")
            if raw_pbr is not None and not pd.isna(raw_pbr) and float(raw_pbr) > 0:
                pbr_val = float(raw_pbr)
                b_scores['PBR水準'] = 100 if pbr_val <= 0.8 else (85 if pbr_val <= 1.0 else (60 if pbr_val <= 1.5 else 35))
                b_descs['PBR水準'] = f"{pbr_val:.2f}倍"
            else:
                pbr_val = None

            b_weights = {'25日乖離': 0.25, '52週高値比': 0.25, '利回り水準': 0.30, 'PBR水準': 0.20}
            avail_b = [k for k in b_weights if k in b_scores]
            b_fullness = f"{len(avail_b)}/4"
            b_score = int(sum(b_scores[k] * (b_weights[k] / sum(b_weights[k] for k in avail_b)) for k in avail_b)) if avail_b else 50
            b_rank = "S" if b_score >= 80 else ("A" if b_score >= 65 else ("B" if b_score >= 50 else "C"))

            m_scores = {}
            if '配当継続力' in h_scores: m_scores['配当継続力'] = h_scores['配当継続力']
            if '配当性向' in h_scores: m_scores['配当性向'] = h_scores['配当性向']
            if '自己資本比率' in h_scores: m_scores['自己資本比率'] = h_scores['自己資本比率']
            if '純利益安定' in h_scores: m_scores['純利益安定'] = h_scores['純利益安定']

            if not cf.empty and "Operating Cash Flow" in cf.index:
                ocf = cf.loc["Operating Cash Flow"].dropna()
                if not ocf.empty:
                    capex = cf.loc["Capital Expenditure"].dropna() if "Capital Expenditure" in cf.index else pd.Series([0])
                    fcf = ocf.iloc[0] + capex.iloc[0] if not capex.empty else ocf.iloc[0]
                    m_scores['CF余力'] = 100 if (ocf.iloc[0] > 0 and fcf > 0) else (75 if ocf.iloc[0] > 0 else 30)

            m_weights = {'配当継続力': 0.25, '配当性向': 0.25, '自己資本比率': 0.15, '純利益安定': 0.15, 'CF余力': 0.20}
            avail_m = [k for k in m_weights if k in m_scores]
            m_fullness = f"{len(avail_m)}/5"
            d_safety_score = int(sum(m_scores[k] * (m_weights[k] / sum(m_weights[k] for k in avail_m)) for k in avail_m)) if avail_m else 60
            d_safety_rank = "S" if d_safety_score >= 85 else ("A" if d_safety_score >= 70 else ("B" if d_safety_score >= 55 else "C"))

            total_available = len(avail_h) + len(avail_b) + len(avail_m)
            star_count = 5 if total_available >= 15 else (4 if total_available >= 12 else (3 if total_available >= 9 else 2))
            reliability_stars = "★" * star_count + "☆" * (5 - star_count)

            c1, c2, c3 = st.columns(3)
            c1.metric("🏋️ 企業の健全性", f"{h_score}点", f"RANK {h_rank} ({h_fullness})")
            c2.metric("🎯 買い時スコア", f"{b_score}点", f"RANK {b_rank} ({b_fullness})")
            c3.metric("🛡️ 配当維持力", f"{d_safety_score}点", f"RANK {d_safety_rank} ({m_fullness})")

            if h_score >= 70 and b_score >= 65 and d_safety_score >= 70:
                st.success("🟢【絶好の買い場】企業体力・株価位置・配当維持力の3拍子が揃った優良候補です。")
            elif h_score >= 70 and b_score < 50:
                st.info("🟡【押し目待ち】企業力が高く配当も安心ですが、現在は株価が高値圏です。急落待ちを推奨。")
            elif d_safety_score < 55 and b_score >= 65:
                st.warning("⚠️【罠警戒・要調査】利回りや割安度は高いですが、配当維持力（CF・業績）に不安があり減配リスクに注意。")
            elif h_score < 55 and b_score < 50:
                st.error("🔴【見送り推奨】業績・財務基盤が弱く、現在の株価水準でも買い場とは言えません。")
            else:
                st.info("👀【通常監視】標準的な水準です。決算発表や急落シグナルを継続監視してください。")

            if warn_div:
                st.warning(warn_div)

            pbr_disp = f"`{pbr_val:.2f}倍`" if pbr_val is not None else "`欠損`"
            st.caption(f"診断信頼度: **{reliability_stars}** ｜ 現在値: `{cur_p:,.1f}円` ｜ 想定年間配当: `{annual_d:.1f}円` (自動取得) ｜ 実績配当: `{hist_actual_d:.1f}円` ｜ 利回り: `{div_y:.2f}%` ｜ PBR: {pbr_disp}")

            cats = ['売上成長', '営業利益率', '純利益成長', '純利益安定', '配当継続力', '配当性向', '自己資本比率', '利益剰余金']
            chart_scores = [h_scores.get(c, 0) for c in cats]
            fig = go.Figure(go.Scatterpolar(r=chart_scores + [chart_scores[0]], theta=cats + [cats[0]], fill='toself', fillcolor='rgba(14,165,233,0.25)', line=dict(color='#0284c7', width=2)))
            fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=False, height=190, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

            table_rows = [{"健全性指標": c, "スコア": f"{h_scores.get(c, '欠損')}点" if c in h_scores else "データなし", "判定・実績値": h_descs.get(c, "-")} for c in cats]
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"詳細診断エラー: {e}")

if "cached_price_df" not in st.session_state:
    st.session_state.cached_price_df = pd.DataFrame()

def fetch_watchlist_data_memory(tickers_tuple):
    if not tickers_tuple: return pd.DataFrame()
    cln = list(dict.fromkeys([norm_c(t) for t in tickers_tuple]))
    syms = [get_sym(t) for t in cln]
    try:
        data = yf.download(syms, period="3mo", interval="1d", group_by="ticker", auto_adjust=False, progress=False)
    except Exception:
        data = pd.DataFrame()
    
    rows = []
    for c in cln:
        sym = get_sym(c)
        cur_p, diff, diff_pct, week_pct, ma25_dev, div_y = np.nan, np.nan, np.nan, np.nan, 0.0, np.nan
        try:
            df = data[sym] if (not data.empty and len(cln) > 1 and sym in data) else (data if not data.empty and len(cln) == 1 else pd.DataFrame())
            t_obj = yf.Ticker(sym)
            if df.empty or len(df.dropna(how="all")) < 2:
                single = t_obj.history(period="1mo", auto_adjust=False)
                if not single.empty and len(single) >= 2: df = single
            if not df.empty and "Close" in df.columns:
                cl = df["Close"].dropna()
                if len(cl) >= 2:
                    cur_p, prev_p = float(cl.iloc[-1]), float(cl.iloc[-2])
                    diff = cur_p - prev_p
                    diff_pct = (diff / prev_p) * 100
                    w_p = float(cl.iloc[-6]) if len(cl) >= 6 else float(cl.iloc[0])
                    week_pct = ((cur_p - w_p) / w_p) * 100
                    ma25 = float(cl.rolling(25).mean().iloc[-1]) if len(cl) >= 25 else float(cl.mean())
                    ma25_dev = ((cur_p - ma25) / ma25) * 100

            div_y, _, _, _, _ = get_dividend_data(c, t_obj.info, cur_p, ticker_obj=t_obj)
        except Exception:
            pass
        rows.append({
            "コード": c, 
            "現在値": cur_p, 
            "前日差": diff, 
            "前日比": diff_pct, 
            "1週": week_pct, 
            "25日乖離": ma25_dev, 
            "利回り": div_y
        })
    return pd.DataFrame(rows)
    
c_t, c_r = st.columns([3, 1])
c_t.title("📈 高配当株 監視ダッシュボード")
if c_r.button("🔄 最新データ更新", use_container_width=True):
    with st.spinner("株価データ更新中..."):
        st.session_state.cached_price_df = fetch_watchlist_data_memory(tuple(st.session_state.watchlist))
    st.rerun()

if st.session_state.cached_price_df.empty and st.session_state.watchlist:
    with st.spinner("初期株価データ読込中..."):
        st.session_state.cached_price_df = fetch_watchlist_data_memory(tuple(st.session_state.watchlist))

df_prices = st.session_state.cached_price_df

rows = []
for c in st.session_state.watchlist:
    tag = st.session_state.company_tags.get(c, "監視")
    name = get_company_name(c)
    p_row = df_prices[df_prices["コード"] == c] if not df_prices.empty and "コード" in df_prices.columns else pd.DataFrame()
    
    row_data = {"状態": tag, "コード": c, "銘柄名": name}
    if not p_row.empty:
        row_data.update({
            "現在値": p_row.iloc[0]["現在値"],
            "前日差": p_row.iloc[0]["前日差"],
            "前日比": p_row.iloc[0]["前日比"],
            "1週": p_row.iloc[0]["1週"],
            "25日乖離": p_row.iloc[0]["25日乖離"],
            "利回り": p_row.iloc[0]["利回り"]
        })
    else:
        row_data.update({"現在値": np.nan, "前日差": np.nan, "前日比": np.nan, "1週": np.nan, "25日乖離": np.nan, "利回り": np.nan})
    rows.append(row_data)

df_all = pd.DataFrame(rows)
update_time = datetime.now(JST).strftime("%H:%M:%S")

st.caption(f"登録数: **{len(st.session_state.watchlist)} 銘柄** ｜ 時刻: **{update_time}** (約20分ディレイ)")

if not df_all.empty:
    valid_df = df_all.dropna(subset=["現在値"])
    
    with st.container(border=True):
        st.markdown("##### 🚨 本日の注目シグナル ＆ 参考高利回り")
        has_signal = False
        
        dip_df = valid_df[(valid_df["25日乖離"] <= -1.0) & (valid_df["前日比"] < 0)].sort_values(by="25日乖離", ascending=True)
        for _, r in dip_df.head(3).iterrows():
            has_signal = True
            yld_val = r['利回り']
            yld_str = f"{yld_val:.2f}%" if pd.notna(yld_val) and yld_val > 0 else "-"
            st.markdown(f"- 🟢 **【押し目候補】** {r['銘柄名']} ({r['コード']}): 25日乖離 `{r['25日乖離']:+.1f}%`, 本日 `{r['前日比']:+.2f}%`, 利回り `{yld_str}`")
        
        heat_df = valid_df[(valid_df["1週"] >= 8.0) | (valid_df["25日乖離"] >= 8.0)].sort_values(by="1週", ascending=False)
        heat_items = []
        for _, r in heat_df.head(3).iterrows():
            heat_items.append(f"**{r['銘柄名']} ({r['コード']})**: 1W `{r['1週']:+.1f}%`, 25d `{r['25日乖離']:+.1f}%`")
        if heat_items:
            has_signal = True
            st.markdown(f"- 🔴 **【過熱中】** " + " ｜ ".join(heat_items))
        
        high_yield_df = valid_df[valid_df["利回り"] >= 5.0].sort_values(by="利回り", ascending=False)
        hy_items = []
        for _, r in high_yield_df.head(3).iterrows():
            yld_val = r['利回り']
            yld_str = f"{yld_val:.2f}%" if pd.notna(yld_val) and yld_val > 0 else "-"
            hy_items.append(f"**{r['銘柄名']} ({r['コード']})**: `{yld_str}`")
        if hy_items:
            has_signal = True
            st.markdown(f"- 💰 **【高利回り】** " + " ｜ ".join(hy_items))

        if not has_signal:
            st.success("✅ 現在、該当するシグナルはありません。")
        
    st.divider()

    tab_all, tab_watch, tab_hold, tab_hobby, tab_profit = st.tabs(["すべて", "監視", "保有", "趣味", "🎯 利確ライン"])

    def style_dataframe(df_target):
        disp_df = df_target[["状態", "コード", "銘柄名", "現在値", "前日比", "1週", "25日乖離", "利回り"]].copy()
        disp_df['利回り表示'] = disp_df['利回り'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) and x > 0 else "-")
        disp_df = disp_df[["状態", "コード", "銘柄名", "現在値", "前日比", "1週", "25日乖離", "利回り表示"]]
        disp_df.rename(columns={"利回り表示": "利回り"}, inplace=True)

        def color_cells(v):
            if pd.isna(v): return ''
            if isinstance(v, (int, float)):
                if v > 0: return 'color: #f87171; font-weight: 600;'
                elif v < 0: return 'color: #60a5fa; font-weight: 600;'
            return ''

        styler = disp_df.style
        map_fn = styler.map if hasattr(styler, 'map') else styler.applymap
        styled = map_fn(color_cells, subset=['前日比', '1週', '25日乖離']).format({
            '現在値': '{:,.1f} 円',
            '前日比': '{:+.2f}%',
            '1週': '{:+.2f}%',
            '25日乖離': '{:+.1f}%'
        }, na_rep='-')
        
        st.dataframe(
            styled,
            use_container_width=True,
            hide_index=True,
            column_config={
                "状態": st.column_config.TextColumn("所属", width="small"),
                "コード": st.column_config.TextColumn("コード", width="small"),
                "銘柄名": st.column_config.TextColumn("銘柄名", width="medium"),
                "現在値": st.column_config.NumberColumn("現在値"),
                "前日比": st.column_config.NumberColumn("前日比"),
                "1週": st.column_config.NumberColumn("1週騰落"),
                "25日乖離": st.column_config.NumberColumn("25日乖離"),
                "利回り": st.column_config.TextColumn("利回り"),
            }
        )

    with tab_all:
        st.caption("📋 すべての登録銘柄の一覧です（閲覧専用）")
        style_dataframe(df_all)

    def render_action_tab(tag_name):
        with st.container(border=True):
            st.markdown(f"##### ⚡ 【{tag_name}】一括追加 ＆ 銘柄管理")
            
            sel_adds = st.multiselect(
                "銘柄を検索して追加 (複数選択可)",
                options=jpx_options,
                key=f"multiselect_add_{tag_name}",
                placeholder="コードや社名の一部を入力して検索（例: 8058, トヨタ）"
            )
            if st.button("➕ 選択した銘柄を追加する", key=f"btn_add_exec_{tag_name}", type="primary"):
                if sel_adds:
                    cur_w, cur_t, cur_d = list(st.session_state.watchlist), dict(st.session_state.company_tags), dict(st.session_state.portfolio_details)
                    added_count = 0
                    for item in sel_adds:
                        c_code = norm_c(item.split(" - ")[0])
                        cur_t[c_code] = tag_name
                        if c_code not in cur_w:
                            cur_w.append(c_code)
                            cur_d[c_code] = {"buy_price": 0.0, "shares": 0, "target_price": 0.0, "annual_div": 0.0}
                            added_count += 1
                    save_watchlist_data(cur_w, cur_t, cur_d)
                    with st.spinner("追加銘柄の株価取得中..."):
                        st.session_state.cached_price_df = fetch_watchlist_data_memory(tuple(cur_w))
                    st.success(f"{added_count} 銘柄を追加しました！")
                    st.rerun()

            st.markdown("---")

            tab_codes = df_all[df_all["状態"] == tag_name]["コード"].tolist()
            if not tab_codes:
                st.info(f"「{tag_name}」タブに該当する銘柄はありません。")
            else:
                tab_options = [f"{c} - {get_company_name(c)}" for c in tab_codes]
                sel_manages = st.multiselect(
                    f"管理する銘柄を選択 ({tag_name}タブ内)",
                    options=tab_options,
                    key=f"multiselect_manage_{tag_name}",
                    placeholder="銘柄を選択または検索（複数選択可）"
                )

                if sel_manages:
                    sel_codes = [norm_c(item.split(" - ")[0]) for item in sel_manages]
                    col_act1, col_act2, col_act3 = st.columns(3)
                    
                    if len(sel_codes) == 1:
                        s_c = sel_codes[0]
                        s_name = get_company_name(s_c)
                        r_match = df_all[df_all["コード"] == s_c]
                        cur_p = r_match.iloc[0]["現在値"] if not r_match.empty else None
                        ma_dev = r_match.iloc[0]["25日乖離"] if not r_match.empty else None
                        if col_act1.button("🔍 選択銘柄の診断", key=f"diag_btn_{tag_name}", use_container_width=True):
                            show_detail_dialog(s_c, s_name, tag_name, cur_p=cur_p, ma25_dev=ma_dev)
                    else:
                        col_act1.caption("※診断は1件のみ選択時有効")

                    other_tags = [t for t in STATUS_OPTS if t != tag_name]
                    for idx, ot in enumerate(other_tags):
                        if col_act2.button(f"👉 選択分を「{ot}」へ移動", key=f"move_btn_{tag_name}_{ot}", use_container_width=True):
                            cur_t = dict(st.session_state.company_tags)
                            for s_c in sel_codes:
                                cur_t[s_c] = ot
                            save_watchlist_data(list(st.session_state.watchlist), cur_t, st.session_state.portfolio_details)
                            st.success(f"{len(sel_codes)} 銘柄を「{ot}」に移動しました！")
                            st.rerun()

                    if col_act3.button("🗑️ 選択分を一括削除", key=f"del_btn_{tag_name}", use_container_width=True, type="secondary"):
                        new_w = [w for w in st.session_state.watchlist if w not in sel_codes]
                        cur_t = dict(st.session_state.company_tags)
                        cur_d = dict(st.session_state.portfolio_details)
                        for s_c in sel_codes:
                            cur_t.pop(s_c, None)
                            cur_d.pop(s_c, None)
                        save_watchlist_data(new_w, cur_t, cur_d)
                        if not st.session_state.cached_price_df.empty:
                            st.session_state.cached_price_df = st.session_state.cached_price_df[~st.session_state.cached_price_df["コード"].isin(sel_codes)]
                        st.success(f"{len(sel_codes)} 銘柄を削除しました！")
                        st.rerun()

        st.markdown("---")
        subset_df = df_all[df_all["状態"] == tag_name].copy()
        style_dataframe(subset_df)

    with tab_watch:
        render_action_tab("監視")
    with tab_hold:
        render_action_tab("保有")
    with tab_hobby:
        render_action_tab("趣味")

    with tab_profit:
        st.markdown("##### 🎯 保有銘柄の利回りと利確ライン管理")
        st.caption("保有タブに登録されている銘柄の「取得単価」「保有株数」「利確ライン」「年間配当金」を手入力で設定し、YOC（取得ベース利回り）や売り時を冷静に判断するチェッカーです。")
        
        hold_codes = df_all[df_all["State"] if "State" in df_all.columns else df_all["状態"] == "保有"]["コード"].tolist()
        
        if not hold_codes:
            st.info("現在、「保有」タブに登録されている銘柄はありません。まずは「保有」タブで銘柄を追加してください。")
        else:
            if "portfolio_details" not in st.session_state:
                st.session_state.portfolio_details = {}

            with st.form("portfolio_form"):
                updated_details = {}
                for hc in hold_codes:
                    h_name = get_company_name(hc)
                    p_match = df_all[df_all["コード"] == hc]
                    cur_p = p_match.iloc[0]["現在値"] if not p_match.empty and not pd.isna(p_match.iloc[0]["現在値"]) else 0.0

                    saved_info = st.session_state.portfolio_details.get(hc, {"buy_price": 0.0, "shares": 0, "target_price": 0.0, "annual_div": 0.0})
                    
                    st.markdown(f"**📌 {h_name} ({hc})** ｜ 現在値: `{cur_p:,.1f} 円`")
                    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
                    b_price = col_p1.number_input(f"取得単価 (円) [{hc}]", min_value=0.0, value=float(saved_info.get("buy_price", 0.0)), step=1.0, format="%.1f")
                    n_shares = col_p2.number_input(f"保持株数 [{hc}]", min_value=0, value=int(saved_info.get("shares", 0)), step=100)
                    t_price = col_p3.number_input(f"利確ライン (円) [{hc}]", min_value=0.0, value=float(saved_info.get("target_price", 0.0)), step=1.0, format="%.1f")
                    a_div = col_p4.number_input(f"年間配当金(1株) [{hc}]", min_value=0.0, value=float(saved_info.get("annual_div", 0.0)), step=0.5, format="%.2f")
                    
                    updated_details[hc] = {"buy_price": b_price, "shares": n_shares, "target_price": t_price, "annual_div": a_div}
                    st.divider()

                if st.form_submit_button("💾 入力内容を保存する", type="primary"):
                    st.session_state.portfolio_details = updated_details
                    save_watchlist_data(st.session_state.watchlist, st.session_state.company_tags, updated_details)
                    st.success("利確ライン・保有データを保存しました！")
                    st.rerun()

            profit_rows = []
            for hc in hold_codes:
                h_name = get_company_name(hc)
                p_match = df_all[df_all["コード"] == hc]
                cur_p = p_match.iloc[0]["現在値"] if not p_match.empty and not pd.isna(p_match.iloc[0]["現在値"]) else 0.0
                week_p = p_match.iloc[0]["1週"] if not p_match.empty and not pd.isna(p_match.iloc[0]["1週"]) else 0.0
                ma_dev = p_match.iloc[0]["25日乖離"] if not p_match.empty and not pd.isna(p_match.iloc[0]["25日乖離"]) else 0.0

                det = st.session_state.portfolio_details.get(hc, {"buy_price": 0.0, "shares": 0, "target_price": 0.0, "annual_div": 0.0})
                bp = det.get("buy_price", 0.0)
                sh = det.get("shares", 0)
                tp = det.get("target_price", 0.0)
                ad = det.get("annual_div", 0.0)

                # 計算ロジック
                p_loss_yen = (cur_p - bp) * sh if bp > 0 and sh > 0 else np.nan
                p_loss_pct = ((cur_p - bp) / bp) * 100 if bp > 0 else np.nan
                target_progress = (cur_p / tp) * 100 if tp > 0 else np.nan
                yoc = (ad / bp) * 100 if bp > 0 and ad > 0 else np.nan
                target_div_yield = (ad / tp) * 100 if tp > 0 and ad > 0 else np.nan
                div_multiple = (cur_p - bp) / ad if bp > 0 and ad > 0 else np.nan

                # 警告アイコン判定ロジック
                status_icon = "🟢 通常"
                if tp > 0 and cur_p >= tp:
                    status_icon = "🔴 要確認(利確到達)"
                elif tp > 0 and cur_p >= tp * 0.95:
                    status_icon = "🟡 上昇警戒(利確接近)"
                elif week_p >= 6.0 or ma_dev >= 7.0:
                    status_icon = "🟡 上昇警戒(急騰・過熱)"
                elif week_p <= -5.0 or ma_dev <= -5.0:
                    status_icon = "🔵 下落警戒(急落・乖離)"

                profit_rows.append({
                    "状態": status_icon,
                    "コード": hc,
                    "銘柄名": h_name,
                    "現在値": cur_p,
                    "取得単価": bp if bp > 0 else np.nan,
                    "利確ライン": tp if tp > 0 else np.nan,
                    "達成率": target_progress,
                    "評価損益": p_loss_yen,
                    "損益率": p_loss_pct,
                    "YOC(取得利回り)": yoc,
                    "到達時利回り": target_div_yield,
                    "配当倍率": div_multiple
                })

            if profit_rows:
                pdf = pd.DataFrame(profit_rows)
                st.markdown("##### 📊 利確判断・保有ステータス一覧")
                
                def color_profit_cells(v):
                    if pd.isna(v): return ''
                    if isinstance(v, (int, float)):
                        if v > 0: return 'color: #f87171; font-weight: 600;'
                        elif v < 0: return 'color: #60a5fa; font-weight: 600;'
                    return ''

                p_styler = pdf.style
                p_map_fn = p_styler.map if hasattr(p_styler, 'map') else p_styler.applymap
                p_styled = p_map_fn(color_profit_cells, subset=['損益率', '評価損益']).format({
                    '現在値': '{:,.1f} 円',
                    '取得単価': '{:,.1f} 円',
                    '利確ライン': '{:,.1f} 円',
                    '達成率': '{:.1f}%',
                    '評価損益': '{:+,.0f} 円',
                    '損益率': '{:+.2f}%',
                    'YOC(取得利回り)': '{:.2f}%',
                    '到達時利回り': '{:.2f}%',
                    '配当倍率': '{:.1f}年分'
                }, na_rep='-')

                st.dataframe(
                    p_styled,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "状態": st.column_config.TextColumn("判定", width="small"),
                        "コード": st.column_config.TextColumn("コード", width="small"),
                        "銘柄名": st.column_config.TextColumn("銘柄名", width="medium"),
                        "現在値": st.column_config.NumberColumn("現在値"),
                        "取得単価": st.column_config.NumberColumn("取得単価"),
                        "利確ライン": st.column_config.NumberColumn("利確ライン"),
                        "達成率": st.column_config.NumberColumn("目標達成率"),
                        "評価損益": st.column_config.NumberColumn("評価損益"),
                        "損益率": st.column_config.NumberColumn("損益率"),
                        "YOC(取得利回り)": st.column_config.NumberColumn("取得利回り"),
                        "到達時利回り": st.column_config.NumberColumn("到達時利回り"),
                        "配当倍率": st.column_config.NumberColumn("含み益配当倍率"),
                    }
    )
