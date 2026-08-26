import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="高配当株 健全性自動チェッカー", layout="wide", page_icon="📊")

st.title("📊 高配当株 8つのものさし自動チェッカー")
st.caption("銘柄コードを入力するだけで財務・配当データを自動取得し、減配リスクと企業体力を即座に判定します。")

col_in1, col_in2 = st.columns([1, 2])
with col_in1:
    ticker_input = st.text_input("銘柄コード（4桁）", value="9432", max_chars=5)
with col_in2:
    st.write("")
    st.write("")
    fetch_btn = st.button("📈 財務データを自動取得して診断", type="primary")

if ticker_input:
    ticker_symbol = f"{ticker_input.strip()}.T" if not ticker_input.endswith(".T") else ticker_input.strip()
    
    with st.spinner(f"【{ticker_symbol}】の財務データ・配当履歴を取得中..."):
        try:
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info
            income = ticker.financials
            balance = ticker.balance_sheet
            dividends = ticker.dividends

            company_name = info.get("longName", info.get("shortName", ticker_symbol))
            st.success(f"取得完了: **{company_name}** ({ticker_symbol})")

            # 1. 売上高成長
            sales_growth_score = 50
            sales_desc = "データ不足"
            if not income.empty and "Total Revenue" in income.index:
                rev = income.loc["Total Revenue"].dropna()[::-1]
                if len(rev) >= 2:
                    yoy_growth = ((rev.iloc[-1] / rev.iloc[0]) ** (1 / (len(rev)-1)) - 1) * 100
                    if yoy_growth >= 4:
                        sales_growth_score = 100
                        sales_desc = f"◎ 年平均+{yoy_growth:.1f}%で成長"
                    elif yoy_growth > 0:
                        sales_growth_score = 80
                        sales_desc = f"○ 緩やかに成長 (+{yoy_growth:.1f}%)"
                    else:
                        sales_growth_score = 30
                        sales_desc = f"✕ 縮小傾向 ({yoy_growth:.1f}%)"

            # 2. 営業利益率
            op_margin = info.get("operatingMargins", 0) * 100
            if op_margin >= 15: op_score = 100
            elif op_margin >= 10: op_score = 85
            elif op_margin >= 5: op_score = 65
            else: op_score = 30

            # 3. EPS成長
            eps_score = 50
            eps_desc = "データ不足"
            if not income.empty and "Diluted EPS" in income.index:
                eps_series = income.loc["Diluted EPS"].dropna()[::-1]
                if len(eps_series) >= 2:
                    if eps_series.iloc[-1] > eps_series.iloc[0] and (eps_series >= 0).all():
                        eps_score = 100
                        eps_desc = "◎ 右肩上がりに成長"
                    elif eps_series.iloc[-1] >= eps_series.iloc[0]:
                        eps_score = 75
                        eps_desc = "○ 安定水準を維持"
                    else:
                        eps_score = 35
                        eps_desc = "✕ 減少または乱高下"

            # 4. 純利益安定性
            profit_score = 50
            profit_desc = "データ不足"
            if not income.empty and "Net Income" in income.index:
                net_incomes = income.loc["Net Income"].dropna()
                if (net_incomes > 0).all():
                    profit_score = 100
                    profit_desc = "◎ 連続黒字を維持"
                else:
                    profit_score = 25
                    profit_desc = "✕ 直近で赤字年度あり"

            # 5. 非減配年数
            div_years_count = 0
            div_score = 40
            if not dividends.empty:
                annual_div = dividends.resample('YE').sum().dropna()
                annual_div = annual_div[annual_div > 0]
                if len(annual_div) >= 2:
                    diffs = annual_div.diff().dropna()
                    non_cut_years = 0
                    for val in reversed(diffs.values):
                        if val >= -0.01: non_cut_years += 1
                        else: break
                    div_years_count = non_cut_years + 1
                    if div_years_count >= 10: div_score = 100
                    elif div_years_count >= 5: div_score = 80
                    elif div_years_count >= 3: div_score = 60
                    else: div_score = 30
            div_desc = f"{div_years_count} 年以上非減配"

            # 6. 配当性向
            payout_ratio = info.get("payoutRatio", 0) * 100
            if 30 <= payout_ratio <= 50: payout_score = 100
            elif (50 < payout_ratio <= 65) or (20 <= payout_ratio < 30): payout_score = 80
            elif 65 < payout_ratio <= 80: payout_score = 55
            elif payout_ratio > 80: payout_score = 25
            else: payout_score = 60

            # 7. 自己資本比率
            equity_ratio = 0
            eq_score = 50
            if not balance.empty and "Stockholders Equity" in balance.index and "Total Assets" in balance.index:
                total_equity = balance.loc["Stockholders Equity"].dropna().iloc[0]
                total_assets = balance.loc["Total Assets"].dropna().iloc[0]
                if total_assets > 0:
                    equity_ratio = (total_equity / total_assets) * 100
                    if equity_ratio >= 60: eq_score = 100
                    elif equity_ratio >= 40: eq_score = 80
                    elif equity_ratio >= 25: eq_score = 55
                    else: eq_score = 25

            # 8. 利益剰余金
            retained_score = 60
            retained_desc = "安定"
            if not balance.empty and "Retained Earnings" in balance.index:
                re = balance.loc["Retained Earnings"].dropna()[::-1]
                if len(re) >= 2:
                    if re.iloc[-1] > re.iloc[0]:
                        retained_score = 100
                        retained_desc = "◎ 潤沢に積み増し中"
                    else:
                        retained_score = 40
                        retained_desc = "△ 横ばいまたは取り崩し"

            scores = [sales_growth_score, op_score, eps_score, profit_score, div_score, payout_score, eq_score, retained_score]
            total_score = int(np.mean(scores))

            if total_score >= 85:
                rank = "S"
                verdict_text = "【超優良】財務基盤・収益性・減配耐性ともに隙がありません。長期保有の主力に適しています。"
            elif total_score >= 70:
                rank = "A"
                verdict_text = "【優良】全体的に高水準で安定しています。ポートフォリオの有力候補です。"
            elif total_score >= 55:
                rank = "B"
                verdict_text = "【普通】標準的な体力です。景気敏感度や配当方針の変更に注意が必要です。"
            else:
                rank = "C"
                verdict_text = "【注意】配当が高くても減配リスクや財務懸念（罠銘柄リスク）があります。"

            st.divider()
            c1, c2 = st.columns([1, 2])

            with c1:
                st.subheader("診断スコア")
                st.metric(label="総合健全性スコア", value=f"{total_score} / 100 点", delta=f"RANK {rank}")
                st.info(verdict_text)
                div_yield = info.get("dividendYield", 0) * 100 if info.get("dividendYield") else 0
                st.markdown(f"""
                - **予想配当利回り**: `{div_yield:.2f}%`
                - **営業利益率**: `{op_margin:.1f}%`
                - **配当性向**: `{payout_ratio:.1f}%`
                - **自己資本比率**: `{equity_ratio:.1f}%`
                """)

            with c2:
                categories = ['売上成長', '営業利益率', 'EPS成長', '純利益安定', '非減配年数', '配当性向', '自己資本比率', '利益剰余金']
                fig = go.Figure()
                fig.add_trace(go.Scatterpolar(
                    r=scores + [scores[0]],
                    theta=categories + [categories[0]],
                    fill='toself',
                    fillcolor='rgba(56, 189, 248, 0.3)',
                    line=dict(color='#0284c7', width=2),
                    name='評価スコア'
                ))
                fig.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                    showlegend=False,
                    height=350,
                    margin=dict(l=40, r=40, t=30, b=30)
                )
                st.plotly_chart(fig, use_container_width=True)

            st.subheader("📋 8つのものさし詳細内訳")
            detail_df = pd.DataFrame({
                "指標項目": categories,
                "評価スコア": scores,
                "判定状況": [sales_desc, f"{op_margin:.1f}%", eps_desc, profit_desc, div_desc, f"{payout_ratio:.1f}%", f"{equity_ratio:.1f}%", retained_desc]
            })
            st.dataframe(detail_df, use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"データ取得エラー: 銘柄コードが存在しないか、取得制限の可能性があります。({e})")
