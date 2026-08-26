import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import json
import os
import unicodedata
from datetime import datetime
import pytz

# --- ページ基本設定 ---
st.set_page_config(page_title="高配当株 監視＆8指標診断ダッシュボード", layout="wide", page_icon="📈")

WATCHLIST_FILE = "watchlist.json"
NAMES_FILE = "company_names.json"
JST = pytz.timezone('Asia/Tokyo')

STATUS_OPTIONS = ["👀 監視中", "💼 保有中", "🎯 買いたい"]

INITIAL_DATA = {
    "8058": ("三菱商事", "👀 監視中"), "3355": ("クリヤマHD", "👀 監視中"),
    "9433": ("KDDI", "👀 監視中"), "2428": ("ウェルネット", "👀 監視中"),
    "4767": ("TOW", "👀 監視中"), "4845": ("スカラ", "👀 監視中"),
    "2181": ("パーソルHD", "👀 監視中"), "1840": ("土屋HD", "👀 監視中"),
    "7203": ("トヨタ自動車", "👀 監視中"), "2411": ("ゲンダイAG", "👀 監視中"),
    "2926": ("篠崎屋", "👀 監視中"), "8729": ("ソニーFG", "👀 監視中"),
    "6093": ("ミトラG", "👀 監視中"), "9432": ("NTT", "👀 監視中"),
    "3010": ("ポラリスHD", "👀 監視中"), "2183": ("リニカル", "👀 監視中"),
    "4714": ("リソー教育", "👀 監視中"), "7795": ("KYORITSU", "👀 監視中"),
    "2146": ("UTグループ", "👀 監視中"), "9434": ("ソフトバンク", "👀 監視中"),
    "8410": ("セブン銀行", "👀 監視中"), "4503": ("アステラス製薬", "👀 監視中"),
    "5032": ("ANYCOLOR", "👀 監視中"), "5253": ("カバー", "👀 監視中"),
    "8306": ("三菱UFJ FG", "👀 監視中"), "8316": ("三井住友FG", "👀 監視中"),
    "8001": ("伊藤忠商事", "👀 監視中"), "2914": ("JT", "👀 監視中"),
    "1928": ("積水ハウス", "👀 監視中"), "8593": ("三菱HCキャピタル", "👀 監視中"),
    "1414": ("ショーボンド", "👀 監視中"), "197A": ("タウンズ", "👀 監視中")
}

def normalize_code(code):
    norm = unicodedata.normalize("NFKC", str(code))
    return norm.strip().upper()

# --- データ読み込み・保存 ---
def load_data():
    names = {}
    tags = {}
    for k, (n, t) in INITIAL_DATA.items():
        c = normalize_code(k)
        names[c] = n
        tags[c] = t

    if os.path.exists(NAMES_FILE):
        try:
            with open(NAMES_FILE, "r", encoding="utf-8") as f:
                saved_names = json.load(f)
                for k, v in saved_names.items():
                    names[normalize_code(k)] = str(v).strip()
        except:
            pass

    tickers = list(names.keys())
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    tickers = list(loaded.keys())
                    for k, v in loaded.items():
                        tags[normalize_code(k)] = v if v in STATUS_OPTIONS else "👀 監視中"
                elif isinstance(loaded, list):
                    tickers = [normalize_code(c) for c in loaded]
                    for c in tickers:
                        if c not in tags: tags[c] = "👀 監視中"
        except:
            pass

    clean_tickers = list(dict.fromkeys([normalize_code(c) for c in tickers]))
    for c in clean_tickers:
        if c not in tags: tags[c] = "👀 監視中"

    return clean_tickers, names, tags

def save_data(tickers, names, tags):
    clean_tickers = list(dict.fromkeys([normalize_code(c) for c in tickers]))
    st.session_state.watchlist = clean_tickers
    st.session_state.company_names = names
    st.session_state.company_tags = tags
    try:
        tag_dict = {c: tags.get(c, "👀 監視中") for c in clean_tickers}
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(tag_dict, f, ensure_ascii=False, indent=2)
        with open(NAMES_FILE, "w", encoding="utf-8") as f:
            json.dump(names, f, ensure_ascii=False, indent=2)
    except:
        pass

if "watchlist" not in st.session_state or "company_tags" not in st.session_state:
    w, n, t = load_data()
    st.session_state.watchlist = w
    st.session_state.company_names = n
    st.session_state.company_tags = t

# --- 8つのものさし ＆ 買い時詳細診断モーダル ---
@st.dialog("📊 銘柄総合診断（健全性 ✕ 買い時）", width="large")
def show_detail_dialog(code, name, status, cur_p=None, div_y=None, ma25_dev=None):
    ticker_symbol = f"{normalize_code(code)}.T"
    st.caption(f"対象銘柄: **{name}** ({ticker_symbol}) ｜ 状態: **{status}**")
    
    with st.spinner("財務データおよびテクニカル指標を解析中..."):
        try:
            t = yf.Ticker(ticker_symbol)
            info = t.info
            income = t.financials
            balance = t.balance_sheet
            cashflow = t.cashflow
            hist = t.history(period="1y")

            # 1. 企業の健全性スコア（8つのものさし）
            sales_score, sales_desc = 50, "データ不足"
            if not income.empty and "Total Revenue" in income.index:
                rev = income.loc["Total Revenue"].dropna()[::-1]
                if len(rev) >= 2:
                    yoy = ((rev.iloc[-1] / rev.iloc[0]) ** (1 / (len(rev)-1)) - 1) * 100
                    if yoy >= 3.0: sales_score, sales_desc = 100, f"◎ 年平均+{yoy:.1f}%成長"
                    elif yoy > 0: sales_score, sales_desc = 80, f"○ 緩やかに成長 (+{yoy:.1f}%)"
                    else: sales_score, sales_desc = 30, f"✕ 縮小傾向 ({yoy:.1f}%)"

            raw_margin = info.get("operatingMargins", 0) or 0
            op_margin = raw_margin * 100 if raw_margin < 1 else raw_margin
            if op_margin >= 15: op_score = 100
            elif op_margin >= 10: op_score = 85
            elif op_margin >= 5: op_score = 65
            else: op_score = 30

            eps_score, eps_desc = 50, "データ不足"
            if not income.empty and "Net Income" in income.index:
                ni = income.loc["Net Income"].dropna()[::-1]
                if len(ni) >= 2:
                    if ni.iloc[-1] > ni.iloc[0] and (ni > 0).all(): eps_score, eps_desc = 100, "◎ 純利益右肩上がり"
                    elif (ni > 0).all(): eps_score, eps_desc = 75, "○ 安定黒字維持"
                    else: eps_score, eps_desc = 35, "✕ 利益減少または赤字"

            profit_score, profit_desc = 50, "データ不足"
            if not income.empty and "Net Income" in income.index:
                net_incomes = income.loc["Net Income"].dropna()
                profit_score, profit_desc = (100, "◎ 連続黒字") if (net_incomes > 0).all() else (25, "✕ 直近で赤字あり")

            div_score, div_desc = 60, "安定配当"
            if not cashflow.empty and "Cash Dividends Paid" in cashflow.index:
                div_paid = cashflow.loc["Cash Dividends Paid"].dropna().abs()[::-1]
                if len(div_paid) >= 2:
                    diffs = div_paid.diff().dropna()
                    if (diffs >= -0.05 * div_paid.iloc[0]).all() and (div_paid.iloc[-1] >= div_paid.iloc[0]):
                        div_score, div_desc = 100, "◎ 非減配・増配維持"
                    else:
                        div_score, div_desc = 50, "△ 配当総額の波あり"

            raw_payout = info.get("payoutRatio", 0) or 0
            payout_ratio = raw_payout * 100 if raw_payout < 1 else raw_payout
            if 30 <= payout_ratio <= 50: payout_score = 100
            elif (50 < payout_ratio <= 65) or (20 <= payout_ratio < 30): payout_score = 80
            elif 65 < payout_ratio <= 80: payout_score = 55
            elif payout_ratio > 80: payout_score = 25
            else: payout_score = 60

            equity_ratio = 0
            eq_score = 50
            if not balance.empty and "Stockholders Equity" in balance.index and "Total Assets" in balance.index:
                te = balance.loc["Stockholders Equity"].dropna().iloc[0]
                ta = balance.loc["Total Assets"].dropna().iloc[0]
                if ta > 0:
                    equity_ratio = (te / ta) * 100
                    if equity_ratio >= 50: eq_score = 100
                    elif equity_ratio >= 35: eq_score = 80
                    elif equity_ratio >= 20: eq_score = 60
                    else: eq_score = 30

            retained_score, retained_desc = 60, "安定"
            if not balance.empty and "Retained Earnings" in balance.index:
                re = balance.loc["Retained Earnings"].dropna()[::-1]
                if len(re) >= 2:
                    retained_score, retained_desc = (100, "◎ 潤沢に蓄積中") if re.iloc[-1] > re.iloc[0] else (40, "△ 横ばい/減少")

            scores_health = [sales_score, op_score, eps_score, profit_score, div_score, payout_score, eq_score, retained_score]
            health_score = int(np.mean(scores_health))
            health_rank = "S" if health_score >= 85 else ("A" if health_score >= 70 else ("B" if health_score >= 55 else "C"))

            # 2. 買い時スコア（割安度・過熱度・株価位置）
            if cur_p is None or pd.isna(cur_p):
                cur_p = float(hist["Close"].iloc[-1]) if not hist.empty else 0
            if div_y is None or pd.isna(div_y):
                div_y = ((info.get("dividendYield", 0) or 0) * 100)

            # 25日乖離
            if ma25_dev is None or pd.isna(ma25_dev):
                if len(hist) >= 25:
                    ma25 = hist["Close"].rolling(25).mean().iloc[-1]
                    ma25_dev = ((cur_p - ma25) / ma25) * 100
                else:
                    ma25_dev = 0

            if ma25_dev <= -5.0: buy_ma_score = 100
            elif ma25_dev <= -2.0: buy_ma_score = 85
            elif ma25_dev <= 2.0: buy_ma_score = 65
            elif ma25_dev <= 6.0: buy_ma_score = 45
            else: buy_ma_score = 20

            # 52週高値からの下落率
            high_52w = hist["Close"].max() if not hist.empty else cur_p
            drop_from_high = ((cur_p - high_52w) / high_52w) * 100 if high_52w > 0 else 0
            if -25 <= drop_from_high <= -10: buy_pos_score = 100
            elif -35 <= drop_from_high < -25 or -10 < drop_from_high <= -5: buy_pos_score = 75
            elif drop_from_high > -5: buy_pos_score = 45
            else: buy_pos_score = 30

            # 利回り水準
            if div_y >= 4.5: buy_div_score = 100
            elif div_y >= 4.0: buy_div_score = 85
            elif div_y >= 3.5: buy_div_score = 65
            elif div_y >= 3.0: buy_div_score = 45
            else: buy_div_score = 25

            pbr_val = info.get("priceToBook", 1.5) or 1.5
            buy_pbr_score = 100 if pbr_val <= 0.8 else (85 if pbr_val <= 1.0 else (60 if pbr_val <= 1.5 else 35))

            buy_score = int(buy_ma_score * 0.35 + buy_pos_score * 0.25 + buy_div_score * 0.25 + buy_pbr_score * 0.15)
            buy_rank = "S" if buy_score >= 80 else ("A" if buy_score >= 65 else ("B" if buy_score >= 50 else "C"))

            # 総合判定
            if health_score >= 70 and buy_score >= 65:
                verdict_box = ("success", "★【絶好の買い場】企業体力・収益性が高く、株価も魅力的な水準（押し目・高利回り）です。")
            elif health_score >= 70 and buy_score < 50:
                verdict_box = ("info", "✋【待ち・高値圏】非常に優良な企業ですが、現在は株価がやや高値圏です。急落待ちを推奨します。")
            elif health_score < 55 and buy_score >= 65:
                verdict_box = ("warning", "⚠️【罠銘柄リスク】利回りや割安度は高いですが、業績・財務に懸念があります。減配リスクに注意してください。")
            else:
                verdict_box = ("info", "👀【通常監視】標準的な水準です。決算発表や全体相場の急変を監視してください。")

            c_h1, c_b1 = st.columns(2)
            with c_h1:
                st.metric(label="🏋️ 企業の健全性", value=f"{health_score} 点", delta=f"RANK {health_rank}")
            with c_b1:
                st.metric(label="🎯 現在の買い時", value=f"{buy_score} 点", delta=f"RANK {buy_rank}")

            if verdict_box[0] == "success": st.success(verdict_box[1])
            elif verdict_box[0] == "warning": st.warning(verdict_box[1])
            else: st.info(verdict_box[1])

            st.markdown(f"""
            - **現在値**: `{cur_p:,.1f} 円` ｜ **予想利回り**: `{div_y:.2f}%` ｜ **PBR**: `{pbr_val:.2f} 倍`
            - **25日移動平均乖離率**: `{ma25_dev:+.2f}%` ｜ **52週高値からの下落率**: `{drop_from_high:+.2f}%`
            """)

            st.divider()
            c_r1, c_r2 = st.columns([1, 1])
            with c_r1:
                cats = ['売上成長', '営業利益率', '純利益成長', '純利益安定', '配当継続力', '配当性向', '自己資本比率', '利益剰余金']
                fig = go.Figure()
                fig.add_trace(go.Scatterpolar(r=scores_health + [scores_health[0]], theta=cats + [cats[0]], fill='toself', fillcolor='rgba(14, 165, 233, 0.25)', line=dict(color='#0284c7', width=2)))
                fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=False, height=200, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)
            with c_r2:
                st.dataframe(pd.DataFrame({
                    "指標項目": cats, "スコア": scores_health,
                    "判定": [sales_desc, f"{op_margin:.1f}%", eps_desc, profit_desc, div_desc, f"{payout_ratio:.1f}%", f"{equity_ratio:.1f}%", retained_desc]
                }), use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"詳細データ取得エラー: {e}")

# --- 高速バッチデータ取得 ---
@st.cache_data(ttl=60)
def fetch_watchlist_data(tickers, names_dict, tags_dict):
    if not tickers:
        return pd.DataFrame(), ""
    
    clean_tickers = list(dict.fromkeys([normalize_code(t) for t in tickers]))
    symbols = [f"{t}.T" for t in clean_tickers]
    data = yf.download(symbols, period="3mo", interval="1d", group_by="ticker", progress=False)
    
    now_str = datetime.now(JST).strftime("%H:%M:%S")
    rows = []
    
    for code_str in clean_tickers:
        sym = f"{code_str}.T"
        jp_name = names_dict.get(code_str, code_str)
        tag_val = tags_dict.get(code_str, "👀 監視中")
        try:
            df = data[sym] if len(clean_tickers) > 1 else data
            df = df.dropna(how="all")
            if len(df) < 2:
                rows.append({"状態": tag_val, "コード": code_str, "銘柄名": jp_name, "現在値": np.nan, "前日差": np.nan, "前日比": np.nan, "1週": np.nan, "利回り": np.nan, "ma25_dev": 0})
                continue
            
            cur_price = float(df["Close"].iloc[-1])
            prev_price = float(df["Close"].iloc[-2])
            diff = cur_price - prev_price
            diff_pct = (diff / prev_price) * 100
            
            week_price = float(df["Close"].iloc[-6]) if len(df) >= 6 else float(df["Close"].iloc[0])
            week_pct = ((cur_price - week_price) / week_price) * 100

            if len(df) >= 25:
                ma25 = float(df["Close"].rolling(25).mean().iloc[-1])
                ma25_dev = ((cur_price - ma25) / ma25) * 100
            else:
                ma25 = float(df["Close"].mean())
                ma25_dev = ((cur_price - ma25) / ma25) * 100

            info = yf.Ticker(sym).info
            raw_yield = info.get("dividendYield", 0) or 0
            div_yield = raw_yield * 100 if raw_yield < 1 else raw_yield

            rows.append({
                "状態": tag_val, "コード": code_str, "銘柄名": jp_name,
                "現在値": cur_price, "前日差": diff, "前日比": diff_pct,
                "1週": week_pct, "利回り": div_yield, "ma25_dev": ma25_dev
            })
        except:
            rows.append({
                "状態": tag_val, "コード": code_str, "銘柄名": jp_name,
                "現在値": np.nan, "前日差": np.nan, "前日比": np.nan,
                "1週": np.nan, "利回り": np.nan, "ma25_dev": 0
            })
            
    return pd.DataFrame(rows), now_str

def color_diff_cells(val):
    if pd.isna(val): return ''
    if val > 0: return 'color: #ff4d4f; font-weight: 700;'
    elif val < 0: return 'color: #1890ff; font-weight: 700;'
    return 'color: #8c8c8c;'

# --- メイン画面ヘッダー ---
c_title, c_refresh = st.columns([3, 1])
with c_title:
    st.title("📈 高配当株 監視ダッシュボード")
with c_refresh:
    st.write("")
    if st.button("🔄 最新データ更新", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# 銘柄管理エリア
with st.expander("⚙️ 監視銘柄・企業名・状態の管理（追加 / 編集 / 削除）"):
    tab_add, tab_edit, tab_del = st.tabs(["➕ 銘柄を追加", "✏️ 名前・状態（タグ）を変更", "🗑️ 銘柄を削除"])
    
    with tab_add:
        c_add1, c_add2, c_add3 = st.columns([2.5, 1.2, 1])
        with c_add1:
            new_input = st.text_input("銘柄コード（「コード:名前」またはカンマ区切り）", placeholder="例: 8058:三菱商事, 9432")
        with c_add2:
            new_status = st.selectbox("追加時の状態", options=STATUS_OPTIONS, index=0)
        with c_add3:
            st.write("")
            st.write("")
            if st.button("追加する", type="primary", use_container_width=True):
                if new_input:
                    items = [i.strip() for i in new_input.split(",") if i.strip()]
                    cur_w = list(st.session_state.watchlist)
                    cur_n = dict(st.session_state.company_names)
                    cur_t = dict(st.session_state.company_tags)
                    for it in items:
                        if ":" in it or "：" in it:
                            delimiter = ":" if ":" in it else "："
                            c, n = it.split(delimiter, 1)
                            c = normalize_code(c)
                            cur_n[c] = n.strip()
                        else:
                            c = normalize_code(it)
                        cur_t[c] = new_status
                        if c not in cur_w: cur_w.append(c)
                    save_data(cur_w, cur_n, cur_t)
                    st.cache_data.clear()
                    st.rerun()

    with tab_edit:
        c_ed1, c_ed2, c_ed3, c_ed4 = st.columns([1.5, 1.5, 1.2, 1])
        with c_ed1:
            edit_code = st.selectbox(
                "変更する銘柄を選択",
                options=st.session_state.watchlist,
                format_func=lambda c: f"{c} ({st.session_state.company_names.get(c, '未登録')})"
            )
        with c_ed2:
            current_name_val = st.session_state.company_names.get(edit_code, edit_code)
            new_name_val = st.text_input("企業名（略称OK）", value=current_name_val)
        with c_ed3:
            current_tag_val = st.session_state.company_tags.get(edit_code, "👀 監視中")
            tag_idx = STATUS_OPTIONS.index(current_tag_val) if current_tag_val in STATUS_OPTIONS else 0
            new_tag_val = st.selectbox("状態（タグ）", options=STATUS_OPTIONS, index=tag_idx)
        with c_ed4:
            st.write("")
            st.write("")
            if st.button("保存する", type="primary", use_container_width=True):
                cur_n = dict(st.session_state.company_names)
                cur_t = dict(st.session_state.company_tags)
                norm_c = normalize_code(edit_code)
                cur_n[norm_c] = new_name_val.strip()
                cur_t[norm_c] = new_tag_val
                save_data(list(st.session_state.watchlist), cur_n, cur_t)
                st.cache_data.clear()
                st.toast("設定を保存しました！", icon="💾")
                st.rerun()

    with tab_del:
        delete_targets = st.multiselect(
            "削除したい銘柄を選択してください（複数選択可）",
            options=st.session_state.watchlist,
            format_func=lambda c: f"{c} - {st.session_state.company_names.get(c, c)}",
            placeholder="削除する銘柄を選択..."
        )
        if st.button("選択した銘柄を一括削除", type="secondary", use_container_width=True):
            if delete_targets:
                norm_targets = [normalize_code(c) for c in delete_targets]
                cur_w = [c for c in st.session_state.watchlist if c not in norm_targets]
                save_data(cur_w, dict(st.session_state.company_names), dict(st.session_state.company_tags))
                st.cache_data.clear()
                st.toast("選択した銘柄を削除しました！", icon="🗑️")
                st.rerun()

# データ取得
with st.spinner("株価データを更新中..."):
    df_all, update_time = fetch_watchlist_data(
        st.session_state.watchlist,
        st.session_state.company_names,
        st.session_state.company_tags
    )

st.caption(f"登録総数: **{len(st.session_state.watchlist)} 銘柄** ｜ 取得時刻: **{update_time}** (※東証データは約20分ディレイ)")

# --- 🚨 今日見るべき注目シグナル ---
if not df_all.empty:
    valid_df = df_all.dropna(subset=["現在値"])
    signals = []
    
    # 1. 押し目候補（25日乖離 -3.0%以下 または 前日比 -2.0%以下）
    dip_df = valid_df[(valid_df["ma25_dev"] <= -3.0) | (valid_df["前日比"] <= -2.0)]
    for _, r in dip_df.iterrows():
        signals.append(f"🟢 **【押し目候補】** {r['銘柄名']} ({r['コード']}): 25日乖離 `{r['ma25_dev']:+.1f}%`, 利回り `{r['利回り']:.2f}%`")

    # 2. 高利回り突入（利回り 5.0%以上）
    yield_df = valid_df[valid_df["利回り"] >= 5.0]
    for _, r in yield_df.iterrows():
        signals.append(f"💰 **【高利回り突入】** {r['銘柄名']} ({r['コード']}): 利回り `{r['利回り']:.2f}%`")

    # 3. 過熱注意（1週間 +8%以上 または 25日乖離
