import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import pytz
import json
import os
import re
import plotly.graph_objects as go

JST = pytz.timezone("Asia/Tokyo")

st.set_page_config(
    page_title="高配当株 監視ダッシュボード",
    page_icon="📈",
    layout="wide"
)

# -------------------------------------------------------------------------
# データ永続化・管理関数
# -------------------------------------------------------------------------
DATA_FILE = "watchlist.json"
STATUS_OPTS = ["監視", "保有", "趣味"]

def load_watchlist_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data, {c: "監視" for c in data}, {}
                elif isinstance(data, dict):
                    wl = data.get("watchlist", [])
                    tags = data.get("company_tags", {c: "監視" for c in wl})
                    details = data.get("portfolio_details", {})
                    return wl, tags, details
        except Exception:
            pass
    return ["1414", "5253"], {"1414": "監視", "5253": "監視"}, {}

def save_watchlist_data(watchlist, company_tags, portfolio_details):
    data = {
        "watchlist": watchlist,
        "company_tags": company_tags,
        "portfolio_details": portfolio_details
    }
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"データ保存エラー: {e}")

if "watchlist" not in st.session_state:
    wl, tags, details = load_watchlist_data()
    st.session_state.watchlist = wl
    st.session_state.company_tags = tags
    st.session_state.portfolio_details = details

# -------------------------------------------------------------------------
# マスター読込（列名ゆらぎ自動対応版）
# -------------------------------------------------------------------------
@st.cache_data
def load_jpx_master():
    if not os.path.exists("jpx_master.csv"):
        st.warning("⚠️ 【マスター読込エラー】`jpx_master.csv` ファイルが見つかりません。")
        return pd.DataFrame(columns=["コード", "銘柄名", "オプション表示"])
    
    last_error = None
    for enc in ["utf-8", "cp932", "shift_jis", "utf-8-sig"]:
        try:
            df = pd.read_csv("jpx_master.csv", dtype=str, encoding=enc)
            
            # 列名のゆらぎを吸収（コード/銘柄コード、銘柄名/銘柄名称に対応）
            code_col = next((c for c in ["コード", "銘柄コード"] if c in df.columns), None)
            name_col = next((c for c in ["銘柄名", "銘柄名称"] if c in df.columns), None)
            
            if code_col and name_col:
                # 確実に文字列化し、前後の空白を除外し、先頭4桁を取り出してzfill(4)する
                df["コード"] = df[code_col].astype(str).str.strip().str[:4].str.zfill(4)
                df["銘柄名"] = df[name_col].astype(str).str.strip()
                df["オプション表示"] = df["コード"] + " - " + df["銘柄名"]
                return df
            else:
                last_error = f"必須カラムが見つかりません (encoding={enc}, 検出列: {list(df.columns)})"
        except Exception as e:
            last_error = f"読み込み例外 (encoding={enc}): {e}"
            continue
            
    st.error(f"❌ `jpx_master.csv` の読込に失敗しました。\n詳細な原因: {last_error}")
    return pd.DataFrame(columns=["コード", "銘柄名", "オプション表示"])

jpx_df = load_jpx_master()
jpx_options = jpx_df["オプション表示"].tolist() if not jpx_df.empty else []

def get_company_name(code):
    clean_c = str(code).zfill(4)[:4]
    if not jpx_df.empty:
        match = jpx_df[jpx_df["コード"] == clean_c]
        if not match.empty:
            return match.iloc[0]["銘柄名"]
    return f"銘柄-{clean_c}"

def norm_c(c):
    return str(c).strip().zfill(4)[:4]

def get_sym(code):
    c_str = norm_c(code)
    return f"{c_str}.T"

# -------------------------------------------------------------------------
# 配当データ取得ヘルパー
# -------------------------------------------------------------------------
def get_dividend_data(code, info, cur_p, ticker_obj=None):
    div_y, annual_d, hist_actual_d, source_type, warn_msg = np.nan, 0.0, 0.0, "なし", None
    try:
        raw_y = info.get("dividendYield")
        if raw_y is not None and not pd.isna(raw_y) and float(raw_y) > 0:
            div_y = float(raw_y) * 100 if float(raw_y) < 1 else float(raw_y)
            
        raw_r = info.get("dividendRate")
        if raw_r is not None and not pd.isna(raw_r) and float(raw_r) > 0:
            annual_d = float(raw_r)

        t = ticker_obj if ticker_obj else yf.Ticker(get_sym(code))
        divs = t.dividends
        if not divs.empty:
            yearly_divs = divs.resample("YE").sum().dropna()
            if not yearly_divs.empty:
                hist_actual_d = float(yearly_divs.iloc[-1])
                if annual_d == 0.0 and len(yearly_divs) >= 1:
                    annual_d = float(yearly_divs.iloc[-1])
                    source_type = "直近実績年間配当"

        if (pd.isna(div_y) or div_y == 0) and annual_d > 0 and cur_p > 0:
            div_y = (annual_d / cur_p) * 100

        if div_y > 8.0:
            warn_msg = f"⚠️ 【高利回り要確認】計算上の配当利回りが {div_y:.2f}% と高水準です。一時的な特別配当や株価急落、またはデータの誤りが含まれている可能性があります。"
    except Exception:
        pass
    return div_y, annual_d, hist_actual_d, source_type, warn_msg

# -------------------------------------------------------------------------
# 銘柄総合診断ダイアログ
# -------------------------------------------------------------------------
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
            safe_ma25_dev = float(ma25_dev) if ma25_dev is not None and not pd.isna(ma25_dev) else None

            if not hist.empty and len(hist) >= 25:
                ma25 = hist["Close"].rolling(25).mean().iloc[-1]
                safe_ma25_dev = ((cur_p - ma25) / ma25) * 100

            if safe_ma25_dev is not None:
                b_scores['25日乖離'] = 100 if safe_ma25_dev <= -5 else (85 if safe_ma25_dev <= -2 else (65 if safe_ma25_dev <= 2 else (45 if safe_ma25_dev <= 6 else 20)))
                b_descs['25日乖離'] = f"{safe_ma25_dev:+.1f}%"

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

# -------------------------------------------------------------------------
# データ一括取得関数（1銘柄時のマルチインデックス完全対応版）
# -------------------------------------------------------------------------
def fetch_watchlist_data_memory(tickers_tuple):
    if not tickers_tuple: return pd.DataFrame()
    cln = list(dict.fromkeys([norm_c(t)[:4] for t in tickers_tuple]))
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
            df = pd.DataFrame()
            if not data.empty:
                if len(cln) == 1:
                    df = data
                elif sym in data:
                    df = data[sym]
            
            t_obj = yf.Ticker(sym)
            if df.empty or len(df.dropna(how="all")) < 2:
                single = t_obj.history(period="1mo", auto_adjust=False)
                if not single.empty and len(single) >= 2: df = single
            
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    close_series = None
                    for col in df.columns:
                        if (sym in col or c in str(col)) and ("Close" in col):
                            close_series = df[col].dropna()
                            break
                    if close_series is None or close_series.empty:
                        for col in df.columns:
                            if "Close" in col:
                                close_series = df[col].dropna()
                                break
                    cl = close_series if close_series is not None else pd.Series(dtype=float)
                else:
                    cl = df["Close"].dropna() if "Close" in df.columns else pd.Series(dtype=float)

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

# -------------------------------------------------------------------------
# メイン表示部
# -------------------------------------------------------------------------
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

    tab_all, tab_watch, tab_hold, tab_hobby, tab_profit = st.tabs(["すべて", "監視", "保有", "趣味", "🎯 釣り合い管理"])

    def display_sortable_dataframe(df_target, sort_key_prefix, default_sort="コード"):
        if df_target.empty:
            st.info("該当する銘柄はありません。")
            return

        c_s1, c_s2 = st.columns([2, 1])
        sort_col = c_s1.selectbox("並び替え基準", ["コード", "銘柄名", "現在値", "前日比", "1週", "25日乖離", "利回り"], index=["コード", "銘柄名", "現在値", "前日比", "1週", "25日乖離", "利回り"].index(default_sort) if default_sort in ["コード", "銘柄名", "現在値", "前日比", "1週", "25日乖離", "利回り"] else 0, key=f"s_col_{sort_key_prefix}")
        order_opt = c_s2.selectbox("順序", ["昇順 (▲)", "降順 (▼)"], index=1 if sort_col in ["現在値", "前日比", "1週", "利回り"] else 0, key=f"s_ord_{sort_key_prefix}")
        is_ascending = order_opt.startswith("昇順")

        sorted_df = df_target.sort_values(by=sort_col, ascending=is_ascending, na_position='last')

        disp_df = sorted_df[["状態", "コード", "銘柄名", "現在値", "前日比", "1週", "25日乖離", "利回り"]].copy()
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
            use_container_width=False,
            hide_index=True,
            column_config={
                "状態": st.column_config.TextColumn("所属", width="small"),
                "コード": st.column_config.TextColumn("コード", width="small"),
                "銘柄名": st.column_config.TextColumn("銘柄名", width="medium"),
                "現在値": st.column_config.NumberColumn("現在値", width="small"),
                "前日比": st.column_config.NumberColumn("前日比", width="small"),
                "1週": st.column_config.NumberColumn("1週騰落", width="small"),
                "25日乖離": st.column_config.NumberColumn("25日乖離", width="small"),
                "利回り": st.column_config.TextColumn("利回り", width="small"),
            }
        )

    with tab_all:
        st.markdown("##### 📋 登録銘柄一覧（すべて）")
        display_sortable_dataframe(df_all, "all", "コード")

    with tab_watch:
        st.markdown("##### 👀 監視中銘柄")
        display_sortable_dataframe(df_all[df_all["状態"] == "監視"], "watch", "利回り")

    with tab_hold:
        st.markdown("##### 💼 保有中銘柄")
        display_sortable_dataframe(df_all[df_all["状態"] == "保有"], "hold", "コード")

    with tab_hobby:
        st.markdown("##### 🧪 趣味・研究銘柄")
        display_sortable_dataframe(df_all[df_all["状態"] == "趣味"], "hobby", "コード")

    with tab_profit:
        st.markdown("##### ⚖️ 含み益と配当金の釣り合い管理")
        st.caption("保有銘柄の評価損益が年間配当金の何年分に相当するかを確認できます。")
        
        hold_codes = df_all[df_all["状態"] == "保有"]["コード"].tolist()
        
        if not hold_codes:
            st.info("現在、「保有」タブに登録されている銘柄はありません。")
        else:
            if "portfolio_details" not in st.session_state:
                st.session_state.portfolio_details = {}

            edit_options = [f"{hc} - {get_company_name(hc)}" for hc in hold_codes]
            selected_edit_item = st.selectbox("個別設定・調整する銘柄を選択", edit_options, key="select_profit_edit")
            
            if selected_edit_item:
                target_hc = norm_c(selected_edit_item.split(" - ")[0])[:4]
                target_name = get_company_name(target_hc)
                p_match = df_all[df_all["コード"] == target_hc]
                cur_p = p_match.iloc[0]["現在値"] if not p_match.empty and not pd.isna(p_match.iloc[0]["現在値"]) else 0.0

                saved_info = st.session_state.portfolio_details.get(target_hc, {"buy_price": 0.0, "shares": 0, "gain_pct": 20.0, "annual_div": 0.0})
                
                with st.container(border=True):
                    st.markdown(f"**📌 {target_name} ({target_hc})** ｜ 現在値: `{cur_p:,.1f} 円`")
                    
                    col_p1, col_p2, col_p3 = st.columns(3)
                    b_price = col_p1.number_input("取得単価 (円)", min_value=0.0, value=float(saved_info.get("buy_price", 0.0)), step=1.0, format="%.1f", key=f"bp_{target_hc}")
                    n_shares = col_p2.number_input("保持株数", min_value=0, value=int(saved_info.get("shares", 0)), step=100, key=f"sh_{target_hc}")
                    a_div = col_p3.number_input("年間配当金(1株・円)", min_value=0.0, value=float(saved_info.get("annual_div", 0.0)), step=0.5, format="%.2f", key=f"ad_{target_hc}")
                    
                    if st.button("💾 この銘柄の設定を保存する", type="primary", key=f"save_btn_{target_hc}"):
                        st.session_state.portfolio_details[target_hc] = {
                            "buy_price": b_price,
                            "shares": n_shares,
                            "gain_pct": float(saved_info.get("gain_pct", 20.0)),
                            "annual_div": a_div
                        }
                        save_watchlist_data(st.session_state.watchlist, st.session_state.company_tags, st.session_state.portfolio_details)
                        st.success(f"{target_name} の設定を保存しました！")
                        st.rerun()

            st.divider()

            profit_rows = []
            for hc in hold_codes:
                h_name = get_company_name(hc)
                p_match = df_all[df_all["コード"] == hc]
                cur_p = p_match.iloc[0]["現在値"] if not p_match.empty and not pd.isna(p_match.iloc[0]["現在値"]) else 0.0
                week_p = p_match.iloc[0]["1週"] if not p_match.empty and not pd.isna(p_match.iloc[0]["1週"]) else 0.0
                ma_dev = p_match.iloc[0]["25日乖離"] if not p_match.empty and not pd.isna(p_match.iloc[0]["25日乖離"]) else 0.0

                det = st.session_state.portfolio_details.get(hc, {"buy_price": 0.0, "shares": 0, "gain_pct": 20.0, "annual_div": 0.0})
                bp = det.get("buy_price", 0.0)
                sh = det.get("shares", 0)
                ad = det.get("annual_div", 0.0)

                p_loss_yen = (cur_p - bp) * sh if bp > 0 and sh > 0 else np.nan
                p_loss_pct = ((cur_p - bp) / bp) * 100 if bp > 0 else np.nan
                annual_div_total = ad * sh if ad > 0 and sh > 0 else np.nan
                yoc = (ad / bp) * 100 if bp > 0 and ad > 0 else np.nan
                
                div_multiple = p_loss_yen / annual_div_total if p_loss_yen is not np.nan and annual_div_total is not np.nan and annual_div_total > 0 else np.nan

                is_overheated = (week_p >= 6.0 or ma_dev >= 7.0)
                is_rising = (week_p >= 4.0 or ma_dev >= 4.0)
                is_downturn = (week_p <= -5.0 or ma_dev <= -5.0)

                if is_overheated:
                    status_icon = "🔴 要確認"
                elif is_rising:
                    status_icon = "🟡 上昇警戒"
                elif is_downturn:
                    status_icon = "🔵 下落・原因確認"
                else:
                    status_icon = "🟢 通常"

                profit_rows.append({
                    "状態": status_icon,
                    "コード": hc,
                    "銘柄名": h_name,
                    "現在値": cur_p,
                    "取得単価": bp if bp > 0 else np.nan,
                    "評価損益": p_loss_yen,
                    "損益率": p_loss_pct,
                    "年間配当総額": annual_div_total,
                    "YOC(取得利回り)": yoc,
                    "配当何年分": div_multiple
                })

            if profit_rows:
                pdf = pd.DataFrame(profit_rows)
                
                c_ps1, c_ps2 = st.columns([2, 1])
                p_sort_col = c_ps1.selectbox("釣り合い一覧の並び替え基準", ["状態", "コード", "銘柄名", "現在値", "評価損益", "損益率", "年間配当総額", "YOC(取得利回り)", "配当何年分"], index=8, key="ps_col")
                p_order_opt = c_ps2.selectbox("順序", ["昇順 (▲)", "降順 (▼)"], index=1, key="ps_ord")
                p_ascending = p_order_opt.startswith("昇順")

                sorted_pdf = pdf.sort_values(by=p_sort_col, ascending=p_ascending, na_position='last')

                st.markdown("##### 📊 評価損益 ✕ 配当金の釣り合い一覧")
                
                def color_profit_cells(v):
                    if pd.isna(v): return ''
                    if isinstance(v, (int, float)):
                        if v > 0: return 'color: #f87171; font-weight: 600;'
                        elif v < 0: return 'color: #60a5fa; font-weight: 600;'
                    return ''

                p_styler = sorted_pdf.style
                p_map_fn = p_styler.map if hasattr(p_styler, 'map') else p_styler.applymap
                p_styled = p_map_fn(color_profit_cells, subset=['損益率', '評価損益']).format({
                    '現在値': '{:,.1f} 円',
                    '取得単価': '{:,.1f} 円',
                    '評価損益': '{:+,.0f} 円',
                    '損益率': '{:+.2f}%',
                    '年間配当総額': '{:,.0f} 円',
                    'YOC(取得利回り)': '{:.2f}%',
                    '配当何年分': '{:.1f}年分'
                }, na_rep='-')

                st.dataframe(
                    p_styled,
                    use_container_width=False,
                    hide_index=True,
                    column_config={
                        "状態": st.column_config.TextColumn("状態", width="small"),
                        "コード": st.column_config.TextColumn("コード", width="small"),
                        "銘柄名": st.column_config.TextColumn("銘柄名", width="medium"),
                        "現在値": st.column_config.NumberColumn("現在値", width="small"),
                        "取得単価": st.column_config.NumberColumn("取得単価", width="small"),
                        "評価損益": st.column_config.NumberColumn("評価損益", width="small"),
                        "損益率": st.column_config.NumberColumn("損益率", width="small"),
                        "年間配当総額": st.column_config.NumberColumn("年間配当総額", width="small"),
                        "YOC(取得利回り)": st.column_config.NumberColumn("YOC", width="small"),
                        "配当何年分": st.column_config.NumberColumn("配当何年分", width="small"),
                    }
                )

# -------------------------------------------------------------------------
# サイドバー管理 ＆ 設定のバックアップ・復元
# -------------------------------------------------------------------------
st.sidebar.header("⚙️ 銘柄管理")
with st.sidebar.expander("➕ 銘柄の追加", expanded=False):
    add_mode = st.radio("入力方法", ["マスターから選択", "コード直接入力"], horizontal=True)
    sel_codes = []
    if add_mode == "マスターから選択":
        chosen_opts = st.multiselect("銘柄検索・選択（複数可）", jpx_options if jpx_options else ["マスター未読込"], key="add_multiselect")
        if chosen_opts:
            sel_codes = [opt.split(" - ")[0] for opt in chosen_opts]
    else:
        raw_input_text = st.text_input("4桁コード（カンマ区切り等で複数可）", "").strip()
        if raw_input_text:
            sel_codes = [c.strip() for c in re.split(r'[,,\s]+', raw_input_text) if c.strip()]

    add_status = st.selectbox("登録分類", STATUS_OPTS, key="add_status_box")
    if st.button("追加する", type="primary"):
        if sel_codes:
            added_count = 0
            for sc in sel_codes:
                norm_add = norm_c(sc)[:4]
                if norm_add and norm_add not in st.session_state.watchlist:
                    st.session_state.watchlist.append(norm_add)
                    st.session_state.company_tags[norm_add] = add_status
                    if norm_add not in st.session_state.portfolio_details:
                        st.session_state.portfolio_details[norm_add] = {"buy_price": 0.0, "shares": 0, "gain_pct": 20.0, "annual_div": 0.0}
                    added_count += 1
            if added_count > 0:
                save_watchlist_data(st.session_state.watchlist, st.session_state.company_tags, st.session_state.portfolio_details)
                st.success(f"{added_count}件の銘柄を追加しました！")
                st.rerun()
            else:
                st.warning("追加対象が指定されていないか、すでにすべて登録されています。")
        else:
            st.warning("追加する銘柄を選択または入力してください。")

with st.sidebar.expander("🗑️ 銘柄の削除・変更", expanded=False):
    if st.session_state.watchlist:
        watch_options = [f"{c} - {get_company_name(c)}" for c in st.session_state.watchlist]
        del_chosen = st.multiselect("対象銘柄選択（複数可）", watch_options, key="del_multiselect")
        new_tag = st.selectbox("分類変更（一括）", STATUS_OPTS, key="tag_chg_box")
        
        c_b1, c_b2 = st.columns(2)
        if c_b1.button("分類を更新"):
            if del_chosen:
                up_count = 0
                for item in del_chosen:
                    t_code = norm_c(item.split(" - ")[0])[:4]
                    if t_code in st.session_state.watchlist:
                        st.session_state.company_tags[t_code] = new_tag
                        up_count += 1
                save_watchlist_data(st.session_state.watchlist, st.session_state.company_tags, st.session_state.portfolio_details)
                st.success(f"{up_count}件の分類を更新しました！")
                st.rerun()
            else:
                st.warning("対象の銘柄を選択してください。")
        if c_b2.button("削除する", type="primary"):
            if del_chosen:
                del_count = 0
                for item in del_chosen:
                    t_code = norm_c(item.split(" - ")[0])[:4]
                    if t_code in st.session_state.watchlist:
                        st.session_state.watchlist.remove(t_code)
                        if t_code in st.session_state.company_tags: del st.session_state.company_tags[t_code]
                        if t_code in st.session_state.portfolio_details: del st.session_state.portfolio_details[t_code]
                        del_count += 1
                save_watchlist_data(st.session_state.watchlist, st.session_state.company_tags, st.session_state.portfolio_details)
                st.success(f"{del_count}件の銘柄を削除しました！")
                st.rerun()
            else:
                st.warning("削除する銘柄を選択してください。")
    else:
        st.info("登録銘柄がありません。")

with st.sidebar.expander("🔍 銘柄の個別3軸診断", expanded=True):
    if st.session_state.watchlist:
        diag_options = [f"{c} - {get_company_name(c)}" for c in st.session_state.watchlist]
        diag_target_opt = st.selectbox("診断対象", diag_options, key="diag_sel_box")
        if diag_target_opt:
            diag_target = norm_c(diag_target_opt.split(" - ")[0])[:4]
            diag_name = get_company_name(diag_target)
            diag_status = st.session_state.company_tags.get(diag_target, "監視")
            if st.button("📊 この銘柄を診断する", type="primary", use_container_width=True):
                show_detail_dialog(diag_target, diag_name, diag_status)
    else:
        st.info("登録銘柄がありません。")

with st.sidebar.expander("💾 設定のバックアップ・復元", expanded=False):
    st.caption("クラウド環境の再起動等によるデータ消失に備え、設定をファイルとして保存・復元できます。")
    
    current_data_dict = {
        "watchlist": st.session_state.watchlist,
        "company_tags": st.session_state.company_tags,
        "portfolio_details": st.session_state.portfolio_details
    }
    json_bytes = json.dumps(current_data_dict, ensure_ascii=False, indent=2).encode("utf-8")
    export_filename = f"stock_watchlist_backup_{datetime.now(JST).strftime('%Y%m%d_%H%M%S')}.json"
    
    st.download_button(
        label="📥 設定ファイルをダウンロード",
        data=json_bytes,
        file_name=export_filename,
        mime="application/json",
        use_container_width=True
    )
    
    st.divider()
    
    uploaded_file = st.file_uploader("📤 バックアップファイルから復元", type=["json"])
    if uploaded_file is not None:
        try:
            imported_data = json.load(uploaded_file)
            if isinstance(imported_data, dict) and "watchlist" in imported_data:
                st.session_state.watchlist = imported_data.get("watchlist", [])
                st.session_state.company_tags = imported_data.get("company_tags", {})
                st.session_state.portfolio_details = imported_data.get("portfolio_details", {})
                
                save_watchlist_data(
                    st.session_state.watchlist, 
                    st.session_state.company_tags, 
                    st.session_state.portfolio_details
                )
                st.success("設定データを正常に復元しました！")
                st.rerun()
            else:
                st.error("エラー: 想定外のファイル構造です。正しいバックアップファイルを選択してください。")
        except Exception as e:
            st.error(f"インポートエラー: {e}")