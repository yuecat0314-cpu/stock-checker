import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# --- ページ基本設定 ---
st.set_page_config(page_title="高配当株 監視＆8指標診断ダッシュボード", layout="wide", page_icon="📈")

# --- 初期監視銘柄リスト（自由に書き換え可能） ---
DEFAULT_TICKERS = [
    "9432", "9434", "8410", "4503", "5032", "5253", "8306", "8316",
    "8058", "8001", "2914", "1928", "8593", "9433", "7203"
]

if "watchlist" not in st.session_state:
    st.session_state.watchlist = DEFAULT_TICKERS.copy()

# --- 8つのものさし詳細診断（ポップアップモーダル） ---
@st.dialog("📊 銘柄健全性・8つのものさし詳細診断", width="large")
def show_detail_dialog(code, name):
    ticker_symbol = f"{code}.T"
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

            # 3. 純利益推移（EPSの株式分割ノイズを排除）
            eps_score = 50
            eps_desc = "データ不足"
            if not income.empty and "Net Income" in income.index:
                ni = income.loc["Net Income"].dropna()[::-1]
                if len(ni) >= 2:
                    if ni.iloc[-1] > ni.iloc[0] and (ni > 0).all(): eps_score, eps_desc = 100, "◎ 純利益右肩上がり"
                    elif (ni > 0).all(): eps_score, eps_desc = 75, "○ 安定黒字維持"
                    else: eps_score, eps_desc = 35, "✕ 利益減少または赤字"

            # 4. 純利益安定性（赤字履歴）
            profit_score = 50
            profit_desc = "データ不足"
            if not income.empty and "Net Income" in income.index:
                net_incomes = income.loc["Net Income"].dropna()
                profit_score, profit_desc = (100, "◎ 連続黒字") if (net_incomes > 0).all() else (25, "✕ 直近で赤字あり")

            # 5. 配当継続力（支払配当金総額ベースで評価）
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

# --- 高速バッチデータ取得キャッシュ ---
@st.cache_data(ttl=180)
def fetch_watchlist_data(tickers):
    if not tickers:
        return pd.DataFrame()
    
    symbols = [f"{t.strip()}.T" for t in tickers]
    data = yf.download(symbols, period="1mo", interval="1d", group_by="ticker", progress=False)
    
    rows = []
    for code in tickers:
        sym = f"{code}.T"
        try:
            df = data[sym] if len(tickers) > 1 else data
            df = df.dropna(how="all")
            if len(df) < 2:
                continue
            
            cur_price = df["Close"].iloc[-1]
            prev_price = df["Close"].iloc[-2]
            diff = cur_price - prev_price
            diff_pct = (diff / prev_price) * 100
            
            # 1週間（5営業日前）との騰落率
            week_price = df["Close"].iloc[-6] if len(df) >= 6 else df["Close"].iloc[0]
            week_pct = ((cur_price - week_price) / week_price) * 100

            info = yf.Ticker(sym).info
            raw_yield = info.get("dividendYield", 0) or 0
            div_yield = raw_yield * 100 if raw_yield < 1 else raw_yield
            name = info.get("shortName", code)

            rows.append({
                "コード": code,
                "銘柄名": name,
                "現在値": f"{cur_price:,.1f} 円",
                "前日差": f"{diff:+,.1f} 円",
                "前日比(%)": f"{diff_pct:+.2f}%",
                "1週間騰落": f"{week_pct:+.2f}%",
                "配当利回り": f"{div_yield:.2f}%",
            })
        except:
            rows.append({"コード": code, "銘柄名": "取得エラー", "現在値": "-", "前日差": "-", "前日比(%)": "-", "1週間騰落": "-", "配当利回り": "-"})
            
    return pd.DataFrame(rows)

# --- メイン画面ヘッダー ---
st.title("📈 高配当株 監視ダッシュボード")
st.caption(f"登録件数: **{len(st.session_state.watchlist)} 銘柄** （ページ制限なしで一括表示）")

# --- 銘柄の追加・削除管理エリア ---
with st.expander("⚙️ 監視銘柄の管理（追加・削除）"):
    tab_add, tab_del = st.tabs(["➕ 銘柄を追加", "🗑️ 銘柄を削除"])
    
    with tab_add:
        c_add1, c_add2 = st.columns([3, 1])
        with c_add1:
            new_code = st.text_input("銘柄コード（カンマ区切りで複数追加可能）", placeholder="例: 8058, 8001, 2914")
        with c_add2:
            st.write("")
            st.write("")
            if st.button("追加する", type="primary", use_container_width=True):
                if new_code:
                    codes = [c.strip() for c in new_code.split(",") if c.strip()]
                    for c in codes:
                        if c not in st.session_state.watchlist:
                            st.session_state.watchlist.append(c)
                    st.cache_data.clear()
                    st.rerun()

    with tab_del:
        delete_targets = st.multiselect(
            "削除したい銘柄を選択してください（複数選択可）",
            options=st.session_state.watchlist,
            placeholder="削除するコードを選択..."
        )
        if st.button("選択した銘柄を一括削除", type="secondary", use_container_width=True):
            if delete_targets:
                st.session_state.watchlist = [c for c in st.session_state.watchlist if c not in delete_targets]
                st.cache_data.clear()
                st.rerun()

# --- 一覧テーブル表示 ---
with st.spinner("株価・騰落・配当利回りを一括更新中..."):
    df_result = fetch_watchlist_data(st.session_state.watchlist)

if not df_result.empty:
    st.write("---")
    st.subheader("📋 監視銘柄一覧")
    st.dataframe(df_result, use_container_width=True, hide_index=True)

    # --- ポップアップ診断エリア ---
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
