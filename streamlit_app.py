import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import urllib.request
import json
import os
import io

# --- ページ基本設定 ---
st.set_page_config(page_title="高配当株 監視＆8指標診断ダッシュボード", layout="wide", page_icon="📈")

WATCHLIST_FILE = "watchlist.json"

# 初期銘柄リスト
DEFAULT_TICKERS = [
    "8058", "3355", "9433", "2428", "4767", "4845", "2181", "1840", "7203", "2411",
    "2926", "8729", "6093", "9432", "3010", "2183", "4714", "7795", "2146", "9434",
    "8410", "4503", "5032", "5253", "8306", "8316", "8001", "2914", "1928", "8593"
]

# 代表的な監視銘柄の日本語マスター辞書（通信エラー時でも100%日本語表示）
KNOWN_NAMES = {
    "8058": "三菱商事", "3355": "クリヤマHD", "9433": "KDDI", "2428": "ウェルネット",
    "4767": "TOW", "4845": "フュージョン", "2181": "パーソルHD", "1840": "土屋HD",
    "7203": "トヨタ自動車", "2411": "ゲンダイAG", "2926": "篠崎屋", "8729": "ソニーFG",
    "6093": "エスクローAJ", "9432": "NTT", "3010": "ポラリスHD", "2183": "リニカル",
    "4714": "リソー教育", "7795": "協立電機", "2146": "UTグループ", "9434": "ソフトバンク",
    "8410": "セブン銀行", "4503": "アステラス製薬", "5032": "ANYCOLOR", "5253": "カバー",
    "8306": "三菱UFJ FG", "8316": "三井住友FG", "8001": "伊藤忠商事", "2914": "日本たばこ産業",
    "1928": "積水ハウス", "8593": "三菱HCキャピタル", "1414": "ショーボンドHD", "197A": "タウンズ"
}

# --- 銘柄リスト保存・復元 ---
def load_watchlist():
    if "tickers" in st.query_params:
        param_tickers = [t.strip().upper() for t in st.query_params["tickers"].split(",") if t.strip()]
        if param_tickers:
            return param_tickers
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except:
            pass
    return DEFAULT_TICKERS.copy()

def save_watchlist(tickers):
    st.session_state.watchlist = tickers
    try:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(tickers, f, ensure_ascii=False, indent=2)
    except:
        pass
    st.query_params["tickers"] = ",".join(tickers)

if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()

# --- 東証全銘柄マスター（JPX公式）の一括読み込み ---
@st.cache_data(ttl=86400 * 7)
def get_jpx_master_dict():
    master = KNOWN_NAMES.copy()
    try:
        url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            content = resp.read()
            df_jpx = pd.read_excel(io.BytesIO(content))
            # JPXエクセルからコードと銘柄名を抽出
            code_col = [c for c in df_jpx.columns if "コード" in str(c)][0]
            name_col = [c for c in df_jpx.columns if "銘柄名" in str(c)][0]
            for _, row in df_jpx.iterrows():
                c_str = str(row[code_col]).strip().upper()
                n_str = str(row[name_col]).strip()
                if c_str and n_str and n_str != "nan":
                    master[c_str] = n_str
    except:
        pass
    return master

JPX_DICT = get_jpx_master_dict()

def get_company_name_jp(code):
    clean_code = str(code).strip().upper()
    return JPX_DICT.get(clean_code, KNOWN_NAMES.get(clean_code, clean_code))

# --- 8つのものさし詳細診断モーダル ---
@st.dialog("📊 銘柄健全性・8つのものさし詳細診断", width="large")
def show_detail_dialog(code, name):
    ticker_symbol = f"{str(code).strip().upper()}.T"
    st.caption(f"対象銘柄: **{name}** ({ticker_symbol})")
    
    with st.spinner("詳細な財務諸表と配当データを取得中..."):
        try:
            t = yf.Ticker(ticker_symbol)
            info = t.info
            income = t.financials
            balance = t.balance_sheet
            cashflow = t.cashflow

            # 1. 売上高成長
            sales_growth_score = 50
            sales_desc = "データ不足"
            if not income.empty and "Total Revenue" in income.index:
                rev = income.loc["Total Revenue"].dropna()[::-1]
                if len(rev) >= 2:
                    yoy = ((rev.iloc[-1] / rev.iloc[0]) ** (1 / (len(rev)-1)) - 1) * 100
                    if yoy >= 3.0: sales_growth_score, sales_desc = 100, f"◎ 年平均+{yoy:.1f}%成長"
                    elif yoy > 0: sales_growth_score, sales_desc = 80, f"○ 緩やかに成長 (+{yoy:.1f}%)"
                    else: sales_growth_score, sales_desc = 30, f"✕ 縮小傾向 ({yoy:.1f}%)"

            # 2. 営業利益率
            raw_margin = info.get("operatingMargins", 0) or 0
            op_margin = raw_margin * 100 if raw_margin < 1 else raw_margin
            if op_margin >= 15: op_score = 100
            elif op_margin >= 10: op_score = 85
            elif op_margin >= 5: op_score = 65
            else: op_score = 30

            # 3. 純利益推移
            eps_score = 50
            eps_desc = "データ不足"
            if not income.empty and "Net Income" in income.index:
                ni = income.loc["Net Income"].dropna()[::-1]
                if len(ni) >= 2:
                    if ni.iloc[-1] > ni.iloc[0] and (ni > 0).all(): eps_score, eps_desc = 100, "◎ 純利益右肩上がり"
                    elif (ni > 0).all(): eps_score, eps_desc = 75, "○ 安定黒字維持"
                    else: eps_score, eps_desc = 35, "✕ 利益減少または赤字"

            # 4. 純利益安定性
            profit_score = 50
            profit_desc = "データ不足"
            if not income.empty and "Net Income" in income.index:
                net_incomes = income.loc["Net Income"].dropna()
                profit_score, profit_desc = (100, "◎ 連続黒字") if (net_incomes > 0).all() else (25, "✕ 直近で赤字あり")

            # 5. 配当継続力
            div_score = 60
            div_desc = "安定配当"
            if not cashflow.empty and "Cash Dividends Paid" in cashflow.index:
                div_paid = cashflow.loc["Cash Dividends Paid"].dropna().abs()[::-1]
                if len(div_paid) >= 2:
                    diffs = div_paid.diff().dropna()
                    if (diffs >= -0.05 * div_paid.iloc[0]).all() and (div_paid.iloc[-1] >= div_paid.iloc[0]):
                        div_score, div_desc = 100, "◎ 非減配・増配維持"
                    else:
                        div_score, div_desc = 50, "△ 配当総額の波あり"

            # 6. 配当性向
            raw_payout = info.get("payoutRatio", 0) or 0
            payout_ratio = raw_payout * 100 if raw_payout < 1 else raw_payout
            if 30 <= payout_ratio <= 50: payout_score = 100
            elif (50 < payout_ratio <= 65) or (20 <= payout_ratio < 30): payout_score = 80
            elif 65 < payout_ratio <= 80: payout_score = 55
            elif payout_ratio > 80: payout_score = 25
            else: payout_score = 60

            # 7. 自己資本比率
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

            # 8. 利益剰余金
            retained_score = 60
            retained_desc = "安定"
            if not balance.empty and "Retained Earnings" in balance.index:
                re = balance.loc["Retained Earnings"].dropna()[::-1]
                if len(re) >= 2:
                    retained_score, retained_desc = (100, "◎ 潤沢に蓄積中") if re.iloc[-1] > re.iloc[0] else (40, "△ 横ばい/減少")

            scores = [sales_growth_score, op_score, eps_score, profit_score, div_score, payout_score, eq_score, retained_score]
            total_score = int(np.mean(scores))
            rank = "S" if total_score >= 85 else ("A" if total_score >= 70 else ("B" if total_score >= 55 else "C"))

            c_score1, c_score2 = st.columns([1, 1])
            with c_score1:
                st.metric(label="総合健全性スコア", value=f"{total_score} 点", delta=f"RANK {rank}")
                st.markdown(f"""
                - **営業利益率**: `{op_margin:.1f}%`
                - **配当性向**: `{payout_ratio:.1f}%`
                - **自己資本比率**: `{equity_ratio:.1f}%`
                """)
            with c_score2:
                cats = ['売上成長', '営業利益率', '純利益成長', '純利益安定', '配当継続力', '配当性向', '自己資本比率', '利益剰余金']
                fig = go.Figure()
                fig.add_trace(go.Scatterpolar(r=scores + [scores[0]], theta=cats + [cats[0]], fill='toself', fillcolor='rgba(14, 165, 233, 0.25)', line=dict(color='#0284c7', width=2)))
                fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=False, height=220, margin=dict(l=20, r=20, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)

            st.dataframe(pd.DataFrame({
                "指標項目": cats, "スコア": scores,
                "判定": [sales_desc, f"{op_margin:.1f}%", eps_desc, profit_desc, div_desc, f"{payout_ratio:.1f}%", f"{equity_ratio:.1f}%", retained_desc]
            }), use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"詳細データ取得エラー: {e}")

# --- 高速バッチデータ取得 ---
@st.cache_data(ttl=180)
def fetch_watchlist_data(tickers):
    if not tickers:
        return pd.DataFrame()
    
    symbols = [f"{str(t).strip().upper()}.T" for t in tickers]
    data = yf.download(symbols, period="1mo", interval="1d", group_by="ticker", progress=False)
    
    rows = []
    for code in tickers:
        code_str = str(code).strip().upper()
        sym = f"{code_str}.T"
        jp_name = get_company_name_jp(code_str)
        try:
            df = data[sym] if len(tickers) > 1 else data
            df = df.dropna(how="all")
            if len(df) < 2:
                rows.append({"コード": code_str, "銘柄名": jp_name, "現在値": np.nan, "前日差": np.nan, "前日比(%)": np.nan, "1週間騰落": np.nan, "配当利回り": np.nan})
                continue
            
            cur_price = float(df["Close"].iloc[-1])
            prev_price = float(df["Close"].iloc[-2])
            diff = cur_price - prev_price
            diff_pct = (diff / prev_price) * 100
            
            week_price = float(df["Close"].iloc[-6]) if len(df) >= 6 else float(df["Close"].iloc[0])
            week_pct = ((cur_price - week_price) / week_price) * 100

            info = yf.Ticker(sym).info
            raw_yield = info.get("dividendYield", 0) or 0
            div_yield = raw_yield * 100 if raw_yield < 1 else raw_yield

            rows.append({
                "コード": code_str,
                "銘柄名": jp_name,
                "現在値": cur_price,
                "前日差": diff,
                "前日比(%)": diff_pct,
                "1週間騰落": week_pct,
                "配当利回り": div_yield
            })
        except:
            rows.append({
                "コード": code_str, "銘柄名": jp_name,
                "現在値": np.nan, "前日差": np.nan, "前日比(%)": np.nan,
                "1週間騰落": np.nan, "配当利回り": np.nan
            })
            
    return pd.DataFrame(rows)

# --- スタイル関数（日本株カラー） ---
def color_diff_cells(val):
    if pd.isna(val): return ''
    if val > 0: return 'color: #ff4d4f; font-weight: 700;'
    elif val < 0: return 'color: #1890ff; font-weight: 700;'
    return 'color: #8c8c8c;'

# --- メイン画面 ---
st.title("📈 高配当株 監視ダッシュボード")
st.caption(f"登録件数: **{len(st.session_state.watchlist)} 銘柄** （自動保存・一括表示）")

# 銘柄管理エリア
with st.expander("⚙️ 監視銘柄の管理（追加・削除）"):
    tab_add, tab_del = st.tabs(["➕ 銘柄を追加", "🗑️ 銘柄を削除"])
    
    with tab_add:
        c_add1, c_add2 = st.columns([3, 1])
        with c_add1:
            new_code = st.text_input("銘柄コード（カンマ区切りで複数追加可能）", placeholder="例: 8058, 8001, 197A")
        with c_add2:
            st.write("")
            st.write("")
            if st.button("追加する", type="primary", use_container_width=True):
                if new_code:
                    codes = [c.strip().upper() for c in new_code.split(",") if c.strip()]
                    current = list(st.session_state.watchlist)
                    for c in codes:
                        if c not in current:
                            current.append(c)
                    save_watchlist(current)
                    st.cache_data.clear()
                    st.rerun()

    with tab_del:
        delete_targets = st.multiselect(
            "削除したい銘柄を選択してください（複数選択可）",
            options=st.session_state.watchlist,
            format_func=lambda c: f"{c} - {get_company_name_jp(c)}",
            placeholder="削除する銘柄を選択..."
        )
        if st.button("選択した銘柄を一括削除", type="secondary", use_container_width=True):
            if delete_targets:
                current = [c for c in st.session_state.watchlist if c not in delete_targets]
                save_watchlist(current)
                st.cache_data.clear()
                st.rerun()

# データ取得＆一覧表示
with st.spinner("株価・騰落・配当利回りを一括更新中..."):
    df_result = fetch_watchlist_data(st.session_state.watchlist)

if not df_result.empty:
    st.write("---")
    st.subheader("📋 監視銘柄一覧")
    
    styled_df = df_result.style.map(
        color_diff_cells, subset=['前日差', '前日比(%)', '1週間騰落']
    ).format({
        '現在値': '{:,.1f} 円',
        '前日差': '{:+,.1f} 円',
        '前日比(%)': '{:+.2f}%',
        '1週間騰落': '{:+.2f}%',
        '配当利回り': '{:.2f}%'
    }, na_rep='-')

    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    # ポップアップ診断エリア
    st.write("---")
    st.subheader("🔍 タップして8つのものさしを診断")
    
    target_code = st.selectbox(
        "診断したい銘柄を選択",
        options=df_result["コード"].tolist(),
        format_func=lambda c: f"{c} - {df_result.loc[df_result['コード']==c, '銘柄名'].values[0]}"
    )
    
    if st.button("🚀 選択した銘柄の8指標をポップアップ診断", type="primary", use_container_width=True):
        target_name = df_result.loc[df_result['コード']==target_code, '銘柄名'].values[0]
        show_detail_dialog(target_code, target_name)
