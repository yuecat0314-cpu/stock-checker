import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import json, os, unicodedata
from datetime import datetime
import pytz

# ==========================================
# 【前半】設定・データ管理・診断ロジック
# ==========================================

# --- ページ設定 ＆ 初期データ ---
st.set_page_config(page_title="高配当株 監視＆8指標診断", layout="wide", page_icon="📈")
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

# --- 銘柄リスト＆名前＆タグの保存・復元 ---
def load_data():
    names = {norm_c(k): v[0] for k, v in INIT_DATA.items()}
    tags = {norm_c(k): v[1] for k, v in INIT_DATA.items()}
    if os.path.exists(NAMES_FILE):
        try:
            with open(NAMES_FILE, "r", encoding="utf-8") as f:
                names.update({norm_c(k): str(v).strip() for k, v in json.load(f).items()})
        except: pass
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
        except: pass
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
    except: pass

if "watchlist" not in st.session_state:
    w, n, t = load_data()
    st.session_state.watchlist, st.session_state.company_names, st.session_state.company_tags = w, n, t

# --- 8つのものさし ＆ 買い時診断モーダル ---
@st.dialog("📊 銘柄総合診断（健全性 ✕ 買い時）", width="large")
def show_detail_dialog(code, name, status, cur_p=None, div_y=None, ma25_dev=None):
    sym = f"{norm_c(code)}.T"
    st.caption(f"対象銘柄: **{name}** ({sym}) ｜ 状態: **{status}**")
    with st.spinner("財務データおよびテクニカル指標を解析中..."):
        try:
            t = yf.Ticker(sym)
            info, inc, bal, cf, hist = t.info, t.financials, t.balance_sheet, t.cashflow, t.history(period="1y")
            
            # 1. 健全性8指標判定
            s_growth, s_g_desc = 50, "データ不足"
            if not inc.empty and "Total Revenue" in inc.index:
                rev = inc.loc["Total Revenue"].dropna()[::-1]
                if len(rev) >= 2:
                    yoy = ((rev.iloc[-1] / rev.iloc[0]) ** (1 / (len(rev)-1)) - 1) * 100
                    s_growth, s_g_desc = (100, f"◎ 年+{yoy:.1f}%") if yoy >= 3 else ((80, f"○ 成長(+{yoy:.1f}%)") if yoy > 0 else (30, f"✕ 縮小({yoy:.1f}%)"))
            
            raw_m = info.get("operatingMargins", 0) or 0
            op_m = raw_m * 100 if raw_m < 1 else raw_m
            s_op = 100 if op_m >= 15 else (85 if op_m >= 10 else (65 if op_m >= 5 else 30))
            
            s_ni, s_ni_desc = 50, "データ不足"
            if not inc.empty and "Net Income" in inc.index:
                ni = inc.loc["Net Income"].dropna()[::-1]
                if len(ni) >= 2:
                    s_ni, s_ni_desc = (100, "◎ 増益基調") if ni.iloc[-1] > ni.iloc[0] and (ni > 0).all() else ((75, "○ 黒字維持") if (ni > 0).all() else (35, "✕ 減益/赤字"))
            
            s_profit, s_p_desc = (100, "◎ 連続黒字") if not inc.empty and "Net Income" in inc.index and (inc.loc["Net Income"].dropna() > 0).all() else (40, "△ 赤字あり/不足")
            
            s_div, s_div_desc = 60, "安定"
            if not cf.empty and "Cash Dividends Paid" in cf.index:
                dp = cf.loc["Cash Dividends Paid"].dropna().abs()[::-1]
                if len(dp) >= 2:
                    s_div, s_div_desc = (100, "◎ 非減配・増配") if (dp.diff().dropna() >= -0.05 * dp.iloc[0]).all() else (50, "△ 配当変動あり")
            
            raw_p = info.get("payoutRatio", 0) or 0
            po_r = raw_p * 100 if raw_p < 1 else raw_p
            s_po = 100 if 30 <= po_r <= 50 else (80 if (50 < po_r <= 65 or 20 <= po_r < 30) else (55 if po_r <= 80 else 25))
            
            eq_r, s_eq = 0, 50
            if not bal.empty and "Stockholders Equity" in bal.index and "Total Assets" in bal.index:
                ta = bal.loc["Total Assets"].dropna().iloc[0]
                if ta > 0:
                    eq_r = (bal.loc["Stockholders Equity"].dropna().iloc[0] / ta) * 100
                    s_eq = 100 if eq_r >= 50 else (80 if eq_r >= 35 else (60 if eq_r >= 20 else 30))
            
            s_re, s_re_desc = 60, "安定"
            if not bal.empty and "Retained Earnings" in bal.index:
                re_v = bal.loc["Retained Earnings"].dropna()[::-1]
                if len(re_v) >= 2:
                    s_re, s_re_desc = (100, "◎ 蓄積中") if re_v.iloc[-1] > re_v.iloc[0] else (40, "△ 横ばい/減少")
            
            h_scores = [s_growth, s_op, s_ni, s_profit, s_div, s_po, s_eq, s_re]
            h_score = int(np.mean(h_scores))
            h_rank = "S" if h_score >= 85 else ("A" if h_score >= 70 else ("B" if h_score >= 55 else "C"))
            
            # 2. 買い時スコア判定
            cur_p = float(cur_p) if cur_p and not pd.isna(cur_p) else (float(hist["Close"].iloc[-1]) if not hist.empty else 0)
            div_y = float(div_y) if div_y and not pd.isna(div_y) else ((info.get("dividendYield", 0) or 0) * 100)
            if ma25_dev is None or pd.isna(ma25_dev):
                ma25_dev = ((cur_p - hist["Close"].rolling(25).mean().iloc[-1]) / hist["Close"].rolling(25).mean().iloc[-1]) * 100 if len(hist) >= 25 else 0
            
            s_b_ma = 100 if ma25_dev <= -5 else (85 if ma25_dev <= -2 else (65 if ma25_dev <= 2 else (45 if ma25_dev <= 6 else 20)))
            high_52w = hist["Close"].max() if not hist.empty else cur_p
            drop_h = ((cur_p - high_52w) / high_52w) * 100 if high_52w > 0 else 0
            s_b_pos = 100 if -25 <= drop_h <= -10 else (75 if (-35 <= drop_h < -25 or -10 < drop_h <= -5) else (45 if drop_h > -5 else 30))
            s_b_div = 100 if div_y >= 4.5 else (85 if div_y >= 4.0 else (65 if div_y >= 3.5 else (45 if div_y >= 3.0 else 25)))
            pbr = info.get("priceToBook", 1.5) or 1.5
            s_b_pbr = 100 if pbr <= 0.8 else (85 if pbr <= 1.0 else (60 if pbr <= 1.5 else 35))
            b_score = int(s_b_ma * 0.35 + s_b_pos * 0.25 + s_b_div * 0.25 + s_b_pbr * 0.15)
            b_rank = "S" if b_score >= 80 else ("A" if b_score >= 65 else ("B" if b_score >= 50 else "C"))
            
            # 診断結果表示
            c1, c2 = st.columns(2)
            c1.metric("🏋️ 健全性", f"{h_score}点", f"RANK {h_rank}")
            c2.metric("🎯 買い時", f"{b_score}点", f"RANK {b_rank}")
            
            if h_score >= 70 and b_score >= 65: st.success("★【絶好の買い場】高財務・高収益＆魅力的な株価水準（押し目/高利回り）です。")
            elif h_score >= 70 and b_score < 50: st.info("✋【待ち・高値圏】優良企業ですが現在はやや高値圏です。押し目待ち推奨。")
            elif h_score < 55 and b_score >= 65: st.warning("⚠️【罠銘柄リスク】利回り/割安感は高いですが、業績・減配リスクに注意。")
            else: st.info("👀【通常監視】標準的な水準です。決算や相場急変を監視してください。")
            
            st.markdown(f"- **現在値**: `{cur_p:,.1f}円` ｜ **利回り**: `{div_y:.2f}%` ｜ **PBR**: `{pbr:.2f}倍` ｜ **25日乖離**: `{ma25_dev:+.2f}%`")
            cats = ['売上成長', '営業利益率', '純利益成長', '純利益安定', '配当継続力', '配当性向', '自己資本比率', '利益剰余金']
            fig = go.Figure(go.Scatterpolar(r=h_scores + [h_scores[0]], theta=cats + [cats[0]], fill='toself', fillcolor='rgba(14,165,233,0.25)', line=dict(color='#0284c7', width=2)))
            fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=False, height=180, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(pd.DataFrame({"指標": cats, "スコア": h_scores, "判定": [s_g_desc, f"{op_m:.1f}%", s_ni_desc, s_p_desc, s_div_desc, f"{po_r:.1f}%", f"{eq_r:.1f}%", s_re_desc]}), use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"診断エラー: {e}")
# ==========================================
# 【後半】データ取得・一覧・画面表示
# ==========================================

# --- 高速バッチデータ取得（3ヶ月データで25日乖離を計算） ---
@st.cache_data(ttl=60)
def fetch_watchlist_data(tickers, names_dict, tags_dict):
    if not tickers: return pd.DataFrame(), ""
    cln = list(dict.fromkeys([norm_c(t) for t in tickers]))
    now_str = datetime.now(JST).strftime("%H:%M:%S")
    try:
        data = yf.download([f"{t}.T" for t in cln], period="3mo", interval="1d", group_by="ticker", progress=False)
    except: data = pd.DataFrame()
    
    rows = []
    for c in cln:
        sym = f"{c}.T"
        cur_p, diff, diff_pct, week_pct, ma25_dev, div_y = np.nan, np.nan, np.nan, np.nan, 0.0, np.nan
        try:
            df = data[sym] if (not data.empty and len(cln) > 1 and sym in data) else (data if not data.empty and len(cln) == 1 else pd.DataFrame())
            if df.empty or len(df.dropna(how="all")) < 2:
                single = yf.Ticker(sym).history(period="1mo")
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
            info = yf.Ticker(sym).info
            raw_y = info.get("dividendYield", 0) or 0
            div_y = raw_y * 100 if raw_y < 1 else raw_y
        except: pass
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
    v_df = df_all.dropna(subset=["現在値"])
    signals = []
    if not v_df.empty:
        for _, r in v_df[(v_df["ma25_dev"] <= -3.0) | (v_df["前日比"] <= -2.0)].iterrows():
            signals.append(f"🟢 **【押し目候補】** {r['銘柄名']} ({r['コード']}): 25日乖離 `{r['ma25_dev']:+.1f}%`, 利回り `{r['利回り']:.2f}%`")
        for _, r in v_df[v_df["利回り"] >= 5.0].iterrows():
            signals.append(f"💰 **【高利回り突入】** {r['銘柄名']} ({r['コード']}): 利回り `{r['利回り']:.2f}%`")
        for _, r in v_df[(v_df["1週"] >= 8.0) | (v_df["ma25_dev"] >= 8.0)].iterrows():
            signals.append(f"🔴 **【過熱注意】** {r['銘柄名']} ({r['コード']}): 1週 `{r['1週']:+.1f}%`, 25日乖離 `{r['ma25_dev']:+.1f}%`")
    
    st.subheader("🚨 今日見るべき注目シグナル")
    if signals:
        for s in signals[:5]: st.markdown(f"- {s}")
    else: st.success("✅ 現在、極端な急落・過熱シグナルはありません。")
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
        except: st.dataframe(v_sub, use_container_width=True, hide_index=True)

    with tab_all: render_tbl(df_all)
    with tab_h: render_tbl(df_all[df_all["状態"] == "💼 保有中"])
    with tab_b: render_tbl(df_all[df_all["状態"] == "🎯 買いたい"])
    with tab_w: render_tbl(df_all[df_all["状態"] == "👀 監視中"])

    st.divider()
    # --- 詳細診断エリア ---
    st.subheader("🔍 銘柄詳細診断（健全性 ✕ 買い時）")
    if not df_all.empty:
        s_c = st.selectbox("診断する銘柄", df_all["コード"].tolist(), format_func=lambda c: f"{c} - {df_all.loc[df_all['コード']==c, '銘柄名'].values[0]} ({df_all.loc[df_all['コード']==c, '状態'].values[0]})")
        if st.button("🚀 総合診断を実行", type="primary", use_container_width=True):
            r = df_all[df_all["コード"] == s_c].iloc[0]
            show_detail_dialog(s_c, r["銘柄名"], r["状態"], cur_p=r["現在値"], div_y=r["利回り"], ma25_dev=r["ma25_dev"])          
