import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import json, os, unicodedata
from datetime import datetime
import pytz

# --- ページ設定 ＆ 初期データ ---
st.set_page_config(page_title="高配当株 監視＆8指標3軸診断", layout="wide", page_icon="📈")
WATCHLIST_FILE, NAMES_FILE = "watchlist.json", "company_names.json"
JST = pytz.timezone('Asia/Tokyo')
STATUS_OPTS = ["👀 監視中", "💼 保有中", "🎯 買いたい"]

INIT_DATA = {
    "8058": ("三菱商事", "👀 監視中"), "3355": ("クリヤマHD", "👀 監視中"), "9433": ("KDDI", "👀 監視中"),
    "2428": ("ウェルネット", "👀 監視中"), "4767": ("TOW", "👀 監視中"), "4845": ("スカラ", "👀 監視中"),
    "2181": ("パーソルHD", "👀 監視中"), "1840": ("土屋HD", "👀 監視中"), "7203": ("トヨタ自動車", "👀 監視中"),
    "2411": ("ゲンダイAG", "👀 監視中"), "2926": ("篠崎屋", "👀 監視中"), "8729": ("ソニーFG", "👀 監視中"),
    "6093": ("ミトラG", "👀 監視中"), "9432": ("NTT", "👀 監視中"), "3010": ("ポラリスHD", "👀 監視中"),
    "2183": ("リニカル", "👀 監視中"), "4714": ("リソー教育", "👀 監視中"), "7795": ("KYORITSU", "👀 監視中"),
    "2146": ("UTグループ", "👀 監視中"), "9434": ("ソフトバンク", "👀 監視中"), "8410": ("セブン銀行", "👀 監視中"),
    "4503": ("アステラス製薬", "👀 監視中"), "5032": ("ANYCOLOR", "👀 監視中"), "5253": ("カバー", "👀 監視中"),
    "8306": ("三菱UFJ FG", "👀 監視中"), "8316": ("三井住友FG", "👀 監視中"), "8001": ("伊藤忠商事", "👀 監視中"),
    "2914": ("JT", "👀 監視中"), "1928": ("積水ハウス", "👀 監視中"), "8593": ("三菱HCキャピタル", "👀 監視中"),
    "1414": ("ショーボンド", "👀 監視中"), "197A": ("タウンズ", "👀 監視中")
}

def norm_c(c):
    return unicodedata.normalize("NFKC", str(c)).strip().upper()

# --- 配当データ取得＆検証（警告付き） ---
def get_dividend_data(info_dict, cur_price, ticker_obj=None):
    if not cur_price or pd.isna(cur_price) or cur_price <= 0:
        return 0.0, 0.0, None

    d_rate = info_dict.get("dividendRate")
    t_rate = info_dict.get("trailingAnnualDividendRate")
    
    hist_div_sum = 0.0
    if ticker_obj is not None:
        try:
            div_hist = ticker_obj.dividends
            if not div_hist.empty:
                hist_div_sum = float(div_hist.last("365D").sum())
                if hist_div_sum == 0 and len(div_hist) > 0:
                    hist_div_sum = float(div_hist.iloc[-1]) * 2
        except Exception:
            pass

    annual_d = 0.0
    warn_msg = None

    if d_rate and not pd.isna(d_rate) and float(d_rate) > 0:
        annual_d = float(d_rate)
        if hist_div_sum > 0 and annual_d >= hist_div_sum * 2.5:
            warn_msg = f"⚠️ 予想配当({annual_d:.1f}円)が直近1年実績({hist_div_sum:.1f}円)の{annual_d/hist_div_sum:.1f}倍です。会社開示資料をご確認ください。"
    elif t_rate and not pd.isna(t_rate) and float(t_rate) > 0:
        annual_d = float(t_rate)
    elif hist_div_sum > 0:
        annual_d = hist_div_sum

    if annual_d > 0:
        div_y = (annual_d / float(cur_price)) * 100
        return div_y, annual_d, warn_msg

    raw_y = info_dict.get("dividendYield", 0) or 0
    if raw_y:
        raw_val = float(raw_y)
        parsed_y = raw_val * 100 if raw_val < 0.20 else raw_val
        return parsed_y, (parsed_y / 100.0) * float(cur_price), None

    return 0.0, 0.0, None

# --- 銘柄リスト＆名前＆タグの保存・復元 ---
def load_data():
    names = {norm_c(k): v[0] for k, v in INIT_DATA.items()}
    tags = {norm_c(k): v[1] for k, v in INIT_DATA.items()}
    if os.path.exists(NAMES_FILE):
        try:
            with open(NAMES_FILE, "r", encoding="utf-8") as f:
                names.update({norm_c(k): str(v).strip() for k, v in json.load(f).items()})
        except Exception:
            pass
    tickers = list(names.keys())
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict):
                    tickers = list(d.keys())
                    for k, v in d.items(): tags[norm_c(k)] = v if v in STATUS_OPTS else "👀 監視中"
                elif isinstance(d, list):
                    tickers = [norm_c(c) for c in d]
        except Exception:
            pass
    cln = list(dict.fromkeys([norm_c(c) for c in tickers]))
    for c in cln:
        if c not in tags: tags[c] = "👀 監視中"
    return cln, names, tags

def save_data(tickers, names, tags):
    cln = list(dict.fromkeys([norm_c(c) for c in tickers]))
    st.session_state.watchlist, st.session_state.company_names, st.session_state.company_tags = cln, names, tags
    try:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump({c: tags.get(c, "👀 監視中") for c in cln}, f, ensure_ascii=False, indent=2)
        with open(NAMES_FILE, "w", encoding="utf-8") as f:
            json.dump(names, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

if "watchlist" not in st.session_state:
    w, n, t = load_data()
    st.session_state.watchlist, st.session_state.company_names, st.session_state.company_tags = w, n, t

# --- 8つのものさし ＆ 3軸詳細診断モーダル ---
@st.dialog("📊 銘柄総合診断（健全性 ✕ 買い時 ✕ 配当維持力）", width="large")
def show_detail_dialog(code, name, status, cur_p=None, ma25_dev=None):
    sym = f"{norm_c(code)}.T"
    st.caption(f"対象銘柄: **{name}** ({sym}) ｜ 状態: **{status}**")
    with st.spinner("財務・CFデータおよびテクニカル指標を多角解析中..."):
        try:
            t = yf.Ticker(sym)
            info = t.info
            inc = t.financials
            bal = t.balance_sheet
            cf = t.cashflow
            hist = t.history(period="1y", auto_adjust=False)
            sector = info.get("sector", "") or ""
            is_financial = any(k in sector for k in ["Financial", "Bank", "Insurance"])

            # -------------------------------------------------------------
            # 1. 🏋️ 企業の健全性（8指標・欠損除外加重平均）
            # -------------------------------------------------------------
            h_scores = {}
            h_descs = {}

            # ① 売上高成長 (重み10%)
            if not inc.empty and "Total Revenue" in inc.index:
                rev = inc.loc["Total Revenue"].dropna()[::-1]
                if len(rev) >= 2:
                    yoy = ((rev.iloc[-1] / rev.iloc[0]) ** (1 / (len(rev)-1)) - 1) * 100
                    h_scores['売上成長'] = 100 if yoy >= 3.0 else (80 if yoy > 0 else 30)
                    h_descs['売上成長'] = f"年平均{yoy:+.1f}%"

            # ② 営業利益率 (重み15%)
            raw_m = info.get("operatingMargins")
            if is_financial:
                h_scores['営業利益率'] = 85
                h_descs['営業利益率'] = "金融セクター基準"
            elif raw_m is not None and not pd.isna(raw_m):
                op_m = float(raw_m) * 100 if float(raw_m) < 1 else float(raw_m)
                h_scores['営業利益率'] = 100 if op_m >= 15 else (85 if op_m >= 10 else (65 if op_m >= 5 else 30))
                h_descs['営業利益率'] = f"{op_m:.1f}%"

            # ③ 純利益成長 (重み10%) & ④ 純利益安定性 (重み15%)
            if not inc.empty and "Net Income" in inc.index:
                ni = inc.loc["Net Income"].dropna()[::-1]
                if len(ni) >= 2:
                    h_scores['純利益成長'] = 100 if (ni.iloc[-1] > ni.iloc[0] and (ni > 0).all()) else (75 if (ni > 0).all() else 35)
                    h_descs['純利益成長'] = "増益基調" if ni.iloc[-1] > ni.iloc[0] else "横ばい/減益"
                net_incomes = inc.loc["Net Income"].dropna()
                if len(net_incomes) >= 2:
                    h_scores['純利益安定'] = 100 if (net_incomes > 0).all() else 25
                    h_descs['純利益安定'] = "連続黒字" if (net_incomes > 0).all() else "赤字期あり"

            # ⑤ 配当継続力 (重み15%) - 完了年度ベース
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
                        h_descs['配当継続力'] = "✕ 過去に減配あり"
                elif len(yearly_divs) >= 1:
                    h_scores['配当継続力'] = 70
                    h_descs['配当継続力'] = "配当実績あり"

            # ⑥ 配当性向 (重み10%)
            raw_p = info.get("payoutRatio")
            if raw_p is not None and not pd.isna(raw_p) and float(raw_p) > 0:
                po_r = float(raw_p) * 100 if float(raw_p) < 1 else float(raw_p)
                h_scores['配当性向'] = 100 if 30 <= po_r <= 50 else (80 if (50 < po_r <= 65 or 20 <= po_r < 30) else (55 if po_r <= 80 else 25))
                h_descs['配当性向'] = f"{po_r:.1f}%"

            # ⑦ 自己資本比率 (重み15%)
            if not bal.empty and "Stockholders Equity" in bal.index and "Total Assets" in bal.index:
                ta = bal.loc["Total Assets"].dropna().iloc[0]
                if ta > 0:
                    eq_r = (bal.loc["Stockholders Equity"].dropna().iloc[0] / ta) * 100
                    if is_financial:
                        h_scores['自己資本比率'] = 100 if eq_r >= 10 else (80 if eq_r >= 6 else 60)
                    else:
                        h_scores['自己資本比率'] = 100 if eq_r >= 50 else (80 if eq_r >= 35 else (60 if eq_r >= 20 else 30))
                    h_descs['自己資本比率'] = f"{eq_r:.1f}%"

            # ⑧ 利益剰余金 (重み10%)
            if not bal.empty and "Retained Earnings" in bal.index:
                re_v = bal.loc["Retained Earnings"].dropna()[::-1]
                if len(re_v) >= 2:
                    h_scores['利益剰余金'] = 100 if re_v.iloc[-1] > re_v.iloc[0] else 40
                    h_descs['利益剰余金'] = "蓄積中" if re_v.iloc[-1] > re_v.iloc[0] else "横ばい/減少"

            # 健全性スコア計算（正規化）
            h_weights = {'売上成長': 0.10, '営業利益率': 0.15, '純利益成長': 0.10, '純利益安定': 0.15, '配当継続力': 0.15, '配当性向': 0.10, '自己資本比率': 0.15, '利益剰余金': 0.10}
            avail_h = [k for k in h_weights if k in h_scores]
            h_fullness = f"{len(avail_h)}/8"
            if avail_h:
                h_score = int(sum(h_scores[k] * (h_weights[k] / sum(h_weights[k] for k in avail_h)) for k in avail_h))
            else:
                h_score = 50
            h_rank = "S" if h_score >= 85 else ("A" if h_score >= 70 else ("B" if h_score >= 55 else "C"))

            # -------------------------------------------------------------
            # 2. 🎯 現在の買い時（4指標・厳密Highベース・欠損再正規化）
            # -------------------------------------------------------------
            cur_p = float(cur_p) if cur_p and not pd.isna(cur_p) else (float(hist["Close"].iloc[-1]) if not hist.empty else 0)
            div_y, annual_d, warn_div = get_dividend_data(info, cur_p, ticker_obj=t)

            b_scores = {}
            b_descs = {}

            # ① 25日移動平均乖離率 (重み25%)
            if not hist.empty and len(hist) >= 25:
                ma25 = hist["Close"].rolling(25).mean().iloc[-1]
                ma25_dev_val = ((cur_p - ma25) / ma25) * 100
                b_scores['25日乖離'] = 100 if ma25_dev_val <= -5 else (85 if ma25_dev_val <= -2 else (65 if ma25_dev_val <= 2 else (45 if ma25_dev_val <= 6 else 20)))
                b_descs['25日乖離'] = f"{ma25_dev_val:+.1f}%"
            elif ma25_dev is not None and not pd.isna(ma25_dev):
                b_scores['25日乖離'] = 100 if ma25_dev <= -5 else (85 if ma25_dev <= -2 else (65 if ma25_dev <= 2 else (45 if ma25_dev <= 6 else 20)))
                b_descs['25日乖離'] = f"{ma25_dev:+.1f}%"

            # ② 厳密な52週高値（Highベース）からの下落率 (重み25%)
            if not hist.empty and "High" in hist.columns:
                high_52w = float(hist["High"].max())
                drop_52w = ((cur_p - high_52w) / high_52w) * 100 if high_52w > 0 else 0
                b_scores['52週高値比'] = 100 if -25 <= drop_52w <= -10 else (75 if (-35 <= drop_52w < -25 or -10 < drop_52w <= -5) else (45 if drop_52w > -5 else 30))
                b_descs['52週高値比'] = f"{drop_52w:+.1f}% ({high_52w:,.1f}円)"

            # ③ 配当利回り水準 (重み30%)
            if div_y is not None and not pd.isna(div_y) and div_y > 0:
                b_scores['利回り水準'] = 100 if div_y >= 4.5 else (85 if div_y >= 4.0 else (65 if div_y >= 3.5 else (45 if div_y >= 3.0 else 25)))
                b_descs['利回り水準'] = f"{div_y:.2f}%"

            # ④ PBR水準 (重み20%・欠損時完全除外)
            raw_pbr = info.get("priceToBook")
            if raw_pbr is not None and not pd.isna(raw_pbr) and float(raw_pbr) > 0:
                pbr_val = float(raw_pbr)
                b_scores['PBR水準'] = 100 if pbr_val <= 0.8 else (85 if pbr_val <= 1.0 else (60 if pbr_val <= 1.5 else 35))
                b_descs['PBR水準'] = f"{pbr_val:.2f}倍"
            else:
                pbr_val = None

            # 買い時スコア計算（正規化）
            b_weights = {'25日乖離': 0.25, '52週高値比': 0.25, '利回り水準': 0.30, 'PBR水準': 0.20}
            avail_b = [k for k in b_weights if k in b_scores]
            b_fullness = f"{len(avail_b)}/4"
            if avail_b:
                b_score = int(sum(b_scores[k] * (b_weights[k] / sum(b_weights[k] for k in avail_b)) for k in avail_b))
            else:
                b_score = 50
            b_rank = "S" if b_score >= 80 else ("A" if b_score >= 65 else ("B" if b_score >= 50 else "C"))

            # -------------------------------------------------------------
            # 3. 🛡️ 配当維持力（CF視点を加えた減配リスク評価）
            # -------------------------------------------------------------
            m_scores = {}
            if '配当継続力' in h_scores: m_scores['配当継続力'] = h_scores['配当継続力']
            if '配当性向' in h_scores: m_scores['配当性向'] = h_scores['配当性向']
            if '自己資本比率' in h_scores: m_scores['自己資本比率'] = h_scores['自己資本比率']
            if '純利益安定' in h_scores: m_scores['純利益安定'] = h_scores['純利益安定']

            # キャッシュフロー健全性判定（営業CF & フリーCF）
            if not cf.empty and "Operating Cash Flow" in cf.index:
                ocf = cf.loc["Operating Cash Flow"].dropna()
                if not ocf.empty:
                    capex = cf.loc["Capital Expenditure"].dropna() if "Capital Expenditure" in cf.index else pd.Series([0])
                    fcf = ocf.iloc[0] + capex.iloc[0] if not capex.empty else ocf.iloc[0]
                    if ocf.iloc[0] > 0 and fcf > 0:
                        m_scores['CF余力'] = 100
                    elif ocf.iloc[0] > 0:
                        m_scores['CF余力'] = 75
                    else:
                        m_scores['CF余力'] = 30

            m_weights = {'配当継続力': 0.25, '配当性向': 0.25, '自己資本比率': 0.15, '純利益安定': 0.15, 'CF余力': 0.20}
            avail_m = [k for k in m_weights if k in m_scores]
            m_fullness = f"{len(avail_m)}/5"
            if avail_m:
                d_safety_score = int(sum(m_scores[k] * (m_weights[k] / sum(m_weights[k] for k in avail_m)) for k in avail_m))
            else:
                d_safety_score = 60
            d_safety_rank = "S" if d_safety_score >= 85 else ("A" if d_safety_score >= 70 else ("B" if d_safety_score >= 55 else "C"))

            # 全体診断信頼度（★評価）
            total_available = len(avail_h) + len(avail_b) + len(avail_m)
            total_possible = 8 + 4 + 5 # 17項目
            star_count = 5 if total_available >= 15 else (4 if total_available >= 12 else (3 if total_available >= 9 else 2))
            reliability_stars = "★" * star_count + "☆" * (5 - star_count)

            # -------------------------------------------------------------
            # UI表示レンダリング
            # -------------------------------------------------------------
            c1, c2, c3 = st.columns(3)
            c1.metric("🏋️ 企業の健全性", f"{h_score}点", f"RANK {h_rank} ({h_fullness})")
            c2.metric("🎯 買い時スコア", f"{b_score}点", f"RANK {b_rank} ({b_fullness})")
            c3.metric("🛡️ 配当維持力", f"{d_safety_score}点", f"RANK {d_safety_rank} ({m_fullness})")

            # 投資アクション判定
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
            st.caption(f"診断信頼度: **{reliability_stars}** ｜ 現在値: `{cur_p:,.1f}円` ｜ 利回り: `{div_y:.2f}%` (年間配当: `{annual_d:.1f}円`) ｜ PBR: {pbr_disp}")

            # チャート表示
            cats = ['売上成長', '営業利益率', '純利益成長', '純利益安定', '配当継続力', '配当性向', '自己資本比率', '利益剰余金']
            chart_scores = [h_scores.get(c, 0) for c in cats]
            fig = go.Figure(go.Scatterpolar(r=chart_scores + [chart_scores[0]], theta=cats + [cats[0]], fill='toself', fillcolor='rgba(14,165,233,0.25)', line=dict(color='#0284c7', width=2)))
            fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=False, height=190, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

            # 内訳テーブル
            table_rows = []
            for c in cats:
                table_rows.append({
                    "健全性指標": c,
                    "スコア": f"{h_scores.get(c, '欠損')}点" if c in h_scores else "データなし",
                    "判定・実績値": h_descs.get(c, "-")
                })
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"詳細診断エラー: {e}")

# --- 高速バッチデータ取得 ---
@st.cache_data(ttl=60)
def fetch_watchlist_data(tickers, names_dict, tags_dict):
    if not tickers: return pd.DataFrame(), ""
    cln = list(dict.fromkeys([norm_c(t) for t in tickers]))
    now_str = datetime.now(JST).strftime("%H:%M:%S")
    try:
        data = yf.download([f"{t}.T" for t in cln], period="3mo", interval="1d", group_by="ticker", auto_adjust=False, progress=False)
    except Exception:
        data = pd.DataFrame()
    
    rows = []
    for c in cln:
        sym = f"{c}.T"
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

            div_y, _, _ = get_dividend_data(t_obj.info, cur_p, ticker_obj=t_obj)
        except Exception:
            pass
        rows.append({"状態": tags_dict.get(c, "👀 監視中"), "コード": c, "銘柄名": names_dict.get(c, c), "現在値": cur_p, "前日差": diff, "前日比": diff_pct, "1週": week_pct, "利回り": div_y, "ma25_dev": ma25_dev})
    return pd.DataFrame(rows), now_str

def color_cells(v):
    return 'color: #ff4d4f; font-weight: 700;' if v > 0 else ('color: #1890ff; font-weight: 700;' if v < 0 else 'color: #8c8c8c;') if pd.notna(v) else ''

# --- メイン画面ヘッダー ＆ 銘柄管理 ---
c_t, c_r = st.columns([3, 1])
c_t.title("📈 高配当株 監視ダッシュボード")
if c_r.button("🔄 最新データ更新", use_container_width=True):
    st.cache_data.clear(); st.rerun()

with st.expander("⚙️ 銘柄管理（追加 / 編集 / 削除）"):
    t_add, t_edit, t_del = st.tabs(["➕ 追加", "✏️ 編集", "🗑️ 削除"])
    with t_add:
        in_code = st.text_input("コード（例: 8058:三菱商事, 9432）")
        in_stat = st.selectbox("状態", STATUS_OPTS, key="add_st")
        if st.button("追加する", type="primary"):
            if in_code:
                cur_w, cur_n, cur_t = list(st.session_state.watchlist), dict(st.session_state.company_names), dict(st.session_state.company_tags)
                for it in in_code.split(","):
                    if not it.strip(): continue
                    c, n = (it.split(":", 1) if ":" in it else (it.split("：", 1) if "：" in it else (it, "")))
                    c = norm_c(c)
                    if n.strip(): cur_n[c] = n.strip()
                    cur_t[c] = in_stat
                    if c not in cur_w: cur_w.append(c)
                save_data(cur_w, cur_n, cur_t)
                st.cache_data.clear(); st.rerun()
    with t_edit:
        e_c = st.selectbox("銘柄選択", st.session_state.watchlist, format_func=lambda c: f"{c} ({st.session_state.company_names.get(c, '')})")
        e_n = st.text_input("名前", value=st.session_state.company_names.get(e_c, e_c))
        e_s = st.selectbox("状態", STATUS_OPTS, index=STATUS_OPTS.index(st.session_state.company_tags.get(e_c, "👀 監視中")))
        if st.button("保存する", type="primary"):
            cur_n, cur_t = dict(st.session_state.company_names), dict(st.session_state.company_tags)
            cur_n[norm_c(e_c)], cur_t[norm_c(e_c)] = e_n.strip(), e_s
            save_data(list(st.session_state.watchlist), cur_n, cur_t)
            st.cache_data.clear(); st.toast("保存完了！"); st.rerun()
    with t_del:
        del_targets = st.multiselect("削除銘柄", st.session_state.watchlist, format_func=lambda c: f"{c} - {st.session_state.company_names.get(c, c)}")
        if st.button("一括削除", type="secondary"):
            if del_targets:
                save_data([c for c in st.session_state.watchlist if c not in [norm_c(x) for x in del_targets]], dict(st.session_state.company_names), dict(st.session_state.company_tags))
                st.cache_data.clear(); st.toast("削除完了！"); st.rerun()

# --- データ取得 ＆ 注目シグナル表示 ---
with st.spinner("データ更新中..."):
    df_all, update_time = fetch_watchlist_data(st.session_state.watchlist, st.session_state.company_names, st.session_state.company_tags)

st.caption(f"登録数: **{len(st.session_state.watchlist)} 銘柄** ｜ 時刻: **{update_time}** (約20分ディレイ)")

if not df_all.empty:
    valid_df = df_all.dropna(subset=["現在値"])
    signals = []
    if not valid_df.empty:
        # 1. 押し目候補
        for _, r in valid_df[(valid_df["ma25_dev"] <= -3.0) | (valid_df["前日比"] <= -2.0)].iterrows():
            signals.append(f"🟢 **【押し目候補】** {r['銘柄名']} ({r['コード']}): 25日乖離 `{r['ma25_dev']:+.1f}%`, 利回り `{r['利回り']:.2f}%`")
        # 2. 高利回り突入
        for _, r in valid_df[valid_df["利回り"] >= 5.0].iterrows():
            signals.append(f"💰 **【高利回り突入】** {r['銘柄名']} ({r['コード']}): 利回り `{r['利回り']:.2f}%`")
        # 3. 過熱注意
        for _, r in valid_df[(valid_df["1週"] >= 8.0) | (valid_df["ma25_dev"] >= 8.0)].iterrows():
            signals.append(f"🔴 **【過熱注意】** {r['銘柄名']} ({r['コード']}): 1週 `{r['1週']:+.1f}%`, 25日乖離 `{r['ma25_dev']:+.1f}%`")
    
    st.subheader("🚨 今日見るべき注目シグナル")
    if signals:
        for s in signals[:5]: st.markdown(f"- {s}")
    else:
        st.success("✅ 現在、極端な急落・過熱シグナルはありません。")
    st.divider()

    # --- 銘柄一覧タブ ---
    tab_all, tab_h, tab_b, tab_w = st.tabs([f"📋 すべて ({len(df_all)})", f"💼 保有中 ({len(df_all[df_all['状態'] == '💼 保有中'])})", f"🎯 買いたい ({len(df_all[df_all['状態'] == '🎯 買いたい'])})", f"👀 監視中 ({len(df_all[df_all['状態'] == '👀 監視中'])})"])
    cols = ["状態", "コード", "銘柄名", "現在値", "前日差", "前日比", "1週", "利回り"]
    
    def render_tbl(target_df):
        if target_df.empty: st.info("該当銘柄なし"); return
        v_sub = target_df[cols].copy()
        try:
            styler = v_sub.style
            m_fn = styler.map if hasattr(styler, 'map') else styler.applymap
            styled = m_fn(color_cells, subset=['前日差', '前日比', '1週']).format({'現在値': '{:,.1f} 円', '前日差': '{:+,.1f} 円', '前日比': '{:+.2f}%', '1週': '{:+.2f}%', '利回り': '{:.2f}%'}, na_rep='-')
            st.dataframe(styled, use_container_width=True, hide_index=True)
        except Exception:
            st.dataframe(v_sub, use_container_width=True, hide_index=True)

    with tab_all: render_tbl(df_all)
    with tab_h: render_tbl(df_all[df_all["状態"] == "💼 保有中"])
    with tab_b: render_tbl(df_all[df_all["状態"] == "🎯 買いたい"])
    with tab_w: render_tbl(df_all[df_all["状態"] == "👀 監視中"])

    st.divider()
    # --- 詳細診断エリア ---
    st.subheader("🔍 銘柄詳細診断（健全性 ✕ 買い時 ✕ 配当維持力）")
    if not df_all.empty:
        s_c = st.selectbox("診断する銘柄", df_all["コード"].tolist(), format_func=lambda c: f"{c} - {df_all.loc[df_all['コード']==c, '銘柄名'].values[0]} ({df_all.loc[df_all['コード']==c, '状態'].values[0]})")
        if st.button("🚀 総合診断を実行", type="primary", use_container_width=True):
            r = df_all[df_all["コード"] == s_c].iloc[0]
            show_detail_dialog(s_c, r["銘柄名"], r["状態"], cur_p=r["現在値"], ma25_dev=r["ma25_dev"])
