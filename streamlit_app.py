import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import io
import json
import os
import datetime

st.set_page_config(
    page_title="日本株ポートフォリオ管理・診断ダッシュボード",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 定数・ファイル設定 ---
DATA_FILE = "watchlist.json"
JPX_URL = "https://www.jpx.co.jp/markets/statistics-quotes/stocks/tvdivq0000003005-att/data_j.xls"

DEFAULT_DATA = {
    "watchlist": [
        "2982", "197A", "4714", "7291", "2428", "423A", "3010", "2391", "2461", "5253"
    ],
    "company_tags": {
        "2982": "保有", "197A": "保有", "4714": "保有", "7291": "保有", "2428": "保有",
        "423A": "保有", "3010": "保有", "2391": "保有", "2461": "保有", "5253": "趣味"
    },
    "portfolio_details": {
        "2982": {"buy_price": 419.37, "shares": 100, "gain_pct": 20.0, "annual_div": 20.0},
        "197A": {"buy_price": 484.37, "shares": 100, "gain_pct": 20.0, "annual_div": 29.0},
        "4714": {"buy_price": 201.34, "shares": 100, "gain_pct": 20.0, "annual_div": 10.0},
        "7291": {"buy_price": 447.37, "shares": 100, "gain_pct": 20.0, "annual_div": 25.0},
        "2428": {"buy_price": 629.37, "shares": 100, "gain_pct": 20.0, "annual_div": 30.5},
        "423A": {"buy_price": 319.37, "shares": 100, "gain_pct": 20.0, "annual_div": 15.0},
        "3010": {"buy_price": 189.69, "shares": 200, "gain_pct": 20.0, "annual_div": 10.0},
        "2391": {"buy_price": 1176.98, "shares": 100, "gain_pct": 20.0, "annual_div": 44.0},
        "2461": {"buy_price": 396.37, "shares": 100, "gain_pct": 20.0, "annual_div": 21.0},
        "5253": {"buy_price": 0.0, "shares": 0, "gain_pct": 20.0, "annual_div": 0.0}
    }
}

# --- データ永続化関数 ---
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "watchlist" in data and "company_tags" in data:
                    if "portfolio_details" not in data:
                        data["portfolio_details"] = {}
                    return data
        except Exception:
            pass
    return DEFAULT_DATA.copy()

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if "app_data" not in st.session_state:
    st.session_state["app_data"] = load_data()

app_data = st.session_state["app_data"]

# --- JPX銘柄マスター取得 ---
@st.cache_data(ttl=86400)
def fetch_jpx_master():
    try:
        res = requests.get(JPX_URL, timeout=10)
        if res.status_code == 200:
            df = pd.read_excel(io.BytesIO(res.content))
            df = df.rename(columns={
                "コード": "コード",
                "銘柄名": "銘柄名",
                "33業種区分": "業種",
                "市場・商品区分": "市場区分"
            })
            df["コード"] = df["コード"].astype(str).str.strip()
            return df[["コード", "銘柄名", "業種", "市場区分"]]
    except Exception:
        pass
    return pd.DataFrame(columns=["コード", "銘柄名", "業種", "市場区分"])

jpx_df = fetch_jpx_master()

def get_company_info(code):
    if not jpx_df.empty:
        match = jpx_df[jpx_df["コード"] == str(code)]
        if not match.empty:
            return match.iloc[0]["銘柄名"], match.iloc[0]["業種"], match.iloc[0]["市場区分"]
    return f"銘柄 {code}", "-", "-"

# --- 株価データ取得 ---
@st.cache_data(ttl=300)
def fetch_stock_data(codes):
    if not codes:
        return {}
    results = {}
    ticker_symbols = [f"{c}.T" if not c.endswith(".T") else c for c in codes]
    try:
        data = yf.download(ticker_symbols, period="2mo", interval="1d", group_by="ticker", threads=True, progress=False)
        for code in codes:
            sym = f"{code}.T" if not code.endswith(".T") else code
            try:
                if len(codes) == 1:
                    df_ticker = data
                else:
                    df_ticker = data[sym] if sym in data else pd.DataFrame()
                
                df_ticker = df_ticker.dropna(how="all")
                if not df_ticker.empty and len(df_ticker) >= 2:
                    closes = df_ticker["Close"].dropna()
                    if len(closes) >= 2:
                        cur_p = float(closes.iloc[-1])
                        prev_p = float(closes.iloc[-2])
                        chg_p = cur_p - prev_p
                        chg_pct = (chg_p / prev_p) * 100 if prev_p != 0 else 0.0
                        
                        # 1週間騰落率
                        week_ago_idx = -6 if len(closes) >= 6 else 0
                        week_p = float(closes.iloc[week_ago_idx])
                        week_pct = ((cur_p - week_p) / week_p) * 100 if week_p != 0 else 0.0
                        
                        # 25日移動平均乖離率
                        if len(closes) >= 25:
                            ma25 = float(closes.iloc[-25:].mean())
                        else:
                            ma25 = float(closes.mean())
                        ma_dev = ((cur_p - ma25) / ma25) * 100 if ma25 != 0 else 0.0
                        
                        results[code] = {
                            "cur_p": cur_p,
                            "prev_p": prev_p,
                            "chg_p": chg_p,
                            "chg_pct": chg_pct,
                            "week_pct": week_pct,
                            "ma_dev": ma_dev
                        }
                        continue
            except Exception:
                pass
            results[code] = {
                "cur_p": 0.0, "prev_p": 0.0, "chg_p": 0.0,
                "chg_pct": 0.0, "week_pct": 0.0, "ma_dev": 0.0
            }
    except Exception:
        for code in codes:
            results[code] = {
                "cur_p": 0.0, "prev_p": 0.0, "chg_p": 0.0,
                "chg_pct": 0.0, "week_pct": 0.0, "ma_dev": 0.0
            }
    return results

stock_prices = fetch_stock_data(app_data.get("watchlist", []))

# --- サイドバー管理 ---
with st.sidebar:
    st.header("⚙️ 設定 & 銘柄管理")
    
    # 手動更新
    if st.button("🔄 データを再読み込み・更新", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    st.markdown("---")
    st.subheader("➕ 銘柄の追加")
    new_input = st.text_input("銘柄コード（カンマ区切りで複数可）", placeholder="例: 7203, 9432")
    tag_options = ["監視", "保有", "趣味"]
    new_tag = st.selectbox("登録分類", tag_options, index=0)
    
    if st.button("追加する", use_container_width=True):
        if new_input:
            added_codes = [c.strip().upper() for c in new_input.replace("、", ",").split(",") if c.strip()]
            for code in added_codes:
                if code not in app_data["watchlist"]:
                    app_data["watchlist"].append(code)
                app_data["company_tags"][code] = new_tag
                if code not in app_data.get("portfolio_details", {}):
                    if "portfolio_details" not in app_data:
                        app_data["portfolio_details"] = {}
                    app_data["portfolio_details"][code] = {
                        "buy_price": 0.0,
                        "shares": 100 if new_tag == "保有" else 0,
                        "gain_pct": 20.0,
                        "annual_div": 0.0
                    }
            save_data(app_data)
            st.session_state["app_data"] = app_data
            st.success(f"{len(added_codes)}件の銘柄を追加しました！")
            st.rerun()

    st.markdown("---")
    st.subheader("✏️ 銘柄の分類変更・削除")
    if app_data.get("watchlist"):
        code_to_edit = st.selectbox("編集対象の銘柄", app_data["watchlist"], format_func=lambda c: f"{c} - {get_company_info(c)[0]}")
        cur_tag = app_data["company_tags"].get(code_to_edit, "監視")
        new_selected_tag = st.selectbox("分類を変更", tag_options, index=tag_options.index(cur_tag) if cur_tag in tag_options else 0)
        
        col_side1, col_side2 = st.columns(2)
        with col_side1:
            if st.button("分類更新", use_container_width=True):
                app_data["company_tags"][code_to_edit] = new_selected_tag
                save_data(app_data)
                st.session_state["app_data"] = app_data
                st.success("分類を更新しました")
                st.rerun()
        with col_side2:
            if st.button("削除 🗑️", use_container_width=True):
                app_data["watchlist"].remove(code_to_edit)
                if code_to_edit in app_data["company_tags"]:
                    del app_data["company_tags"][code_to_edit]
                if "portfolio_details" in app_data and code_to_edit in app_data["portfolio_details"]:
                    del app_data["portfolio_details"][code_to_edit]
                save_data(app_data)
                st.session_state["app_data"] = app_data
                st.warning(f"{code_to_edit} を削除しました")
                st.rerun()

    st.markdown("---")
    st.subheader("📦 設定のバックアップ・復元")
    
    # エクスポート
    json_data = json.dumps(app_data, ensure_ascii=False, indent=2)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        label="📥 設定をJSONでダウンロード",
        data=json_data,
        file_name=f"stock_watchlist_backup_{timestamp}.json",
        mime="application/json",
        use_container_width=True
    )
    
    # インポート
    uploaded_file = st.file_uploader("📤 JSONバックアップから復元", type=["json"])
    if uploaded_file is not None:
        try:
            uploaded_json = json.load(uploaded_file)
            if "watchlist" in uploaded_json and "company_tags" in uploaded_json:
                app_data = uploaded_json
                if "portfolio_details" not in app_data:
                    app_data["portfolio_details"] = {}
                save_data(app_data)
                st.session_state["app_data"] = app_data
                st.success("設定を正常に復元しました！")
                st.rerun()
            else:
                st.error("JSONファイルの形式が正しくありません。")
        except Exception as e:
            st.error(f"読み込みエラー: {e}")

# --- メインコンテンツ ---
st.title("📈 日本株ウォッチリスト & 診断ダッシュボード")

# タブ定義
tabs = st.tabs(["すべて", "監視", "保有", "趣味", "🎯 釣り合い管理"])

def build_summary_table(filter_tag=None):
    rows = []
    for code in app_data.get("watchlist", []):
        tag = app_data["company_tags"].get(code, "監視")
        if filter_tag and tag != filter_tag:
            continue
        
        name, sector, market = get_company_info(code)
        price_info = stock_prices.get(code, {
            "cur_p": 0.0, "prev_p": 0.0, "chg_p": 0.0, "chg_pct": 0.0, "week_pct": 0.0, "ma_dev": 0.0
        })
        
        cur_p = price_info["cur_p"]
        chg_p = price_info["chg_p"]
        chg_pct = price_info["chg_pct"]
        week_pct = price_info["week_pct"]
        ma_dev = price_info["ma_dev"]
        
        # 状態判定ロジック (4段階判定)
        is_overheated = (week_pct >= 6.0 or ma_dev >= 7.0)
        is_rising = (week_pct >= 4.0 or ma_dev >= 4.0)
        is_downturn = (week_pct <= -5.0 or ma_dev <= -5.0)
        
        if is_overheated:
            status_icon = "🔴 要確認"
        elif is_rising:
            status_icon = "🟡 上昇警戒"
        elif is_downturn:
            status_icon = "🔵 下落・原因確認"
        else:
            status_icon = "🟢 通常"
            
        rows.append({
            "状態": status_icon,
            "コード": code,
            "銘柄名": name,
            "分類": tag,
            "業種": sector,
            "市場区分": market,
            "現在値": f"{cur_p:,.1f} 円" if cur_p > 0 else "-",
            "前日比": f"{'+' if chg_p > 0 else ''}{chg_p:,.1f} 円" if cur_p > 0 else "-",
            "前日比率": f"{'+' if chg_pct > 0 else ''}{chg_pct:.2f}%" if cur_p > 0 else "-",
            "1週間騰落率": f"{'+' if week_pct > 0 else ''}{week_pct:.2f}%" if cur_p > 0 else "-",
            "25日乖離率": f"{'+' if ma_dev > 0 else ''}{ma_dev:.2f}%" if cur_p > 0 else "-"
        })
    return pd.DataFrame(rows)

# 1. すべて
with tabs[0]:
    df_all = build_summary_table()
    if not df_all.empty:
        st.dataframe(df_all, use_container_width=True, hide_index=True)
    else:
        st.info("登録されている銘柄がありません。")

# 2. 監視
with tabs[1]:
    df_watch = build_summary_table(filter_tag="監視")
    if not df_watch.empty:
        st.dataframe(df_watch, use_container_width=True, hide_index=True)
    else:
        st.info("「監視」に登録された銘柄はありません。")

# 3. 保有
with tabs[2]:
    df_hold = build_summary_table(filter_tag="保有")
    if not df_hold.empty:
        st.dataframe(df_hold, use_container_width=True, hide_index=True)
    else:
        st.info("「保有」に登録された銘柄はありません。")

# 4. 趣味
with tabs[3]:
    df_hobby = build_summary_table(filter_tag="趣味")
    if not df_hobby.empty:
        st.dataframe(df_hobby, use_container_width=True, hide_index=True)
    else:
        st.info("「趣味」に登録された銘柄はありません。")

# 5. 🎯 釣り合い管理
with tabs[4]:
    st.subheader("🎯 保有銘柄の釣り合い管理 & 設定")
    
    hold_codes = [c for c in app_data.get("watchlist", []) if app_data["company_tags"].get(c) == "保有"]
    
    if not hold_codes:
        st.info("「保有」分類の銘柄がありません。サイドバーから銘柄を追加または分類を「保有」に設定してください。")
    else:
        selected_code = st.selectbox(
            "設定を変更する保有銘柄",
            hold_codes,
            format_func=lambda c: f"{c} - {get_company_info(c)[0]}"
        )
        
        details = app_data.get("portfolio_details", {}).get(selected_code, {
            "buy_price": 0.0,
            "shares": 100,
            "gain_pct": 20.0,
            "annual_div": 0.0
        })
        
        price_info = stock_prices.get(selected_code, {"cur_p": 0.0})
        cur_p = price_info["cur_p"]
        
        st.markdown(f"### 📌 **{get_company_info(selected_code)[0]}** ({selected_code}) ｜ 現在値: **{cur_p:,.1f} 円**")
        
        col_in1, col_in2 = st.columns(2)
        with col_in1:
            buy_price = st.number_input("取得単価 (円)", min_value=0.0, value=float(details.get("buy_price", 0.0)), step=1.0)
            shares = st.number_input("保持株数", min_value=0, value=int(details.get("shares", 100)), step=100)
        with col_in2:
            gain_pct = st.number_input("目標上昇率 (%)", min_value=0.0, value=float(details.get("gain_pct", 20.0)), step=1.0)
            annual_div = st.number_input("年間配当金(1株・円)", min_value=0.0, value=float(details.get("annual_div", 0.0)), step=0.5)
            
        target_price = buy_price * (1.0 + gain_pct / 100.0) if buy_price > 0 else 0.0
        st.markdown(f"✨ 自動計算される利確ライン: **{target_price:,.1f} 円**")
        
        if st.button("💾 この銘柄の設定を保存する", use_container_width=True):
            if "portfolio_details" not in app_data:
                app_data["portfolio_details"] = {}
            app_data["portfolio_details"][selected_code] = {
                "buy_price": buy_price,
                "shares": shares,
                "gain_pct": gain_pct,
                "annual_div": annual_div
            }
            save_data(app_data)
            st.session_state["app_data"] = app_data
            st.success(f"{selected_code} の個別設定を保存しました！")
            st.rerun()

        st.markdown("---")
        
        # 釣り合い一覧表の作成
        balance_rows = []
        for code in hold_codes:
            name, _, _ = get_company_info(code)
            p_info = stock_prices.get(code, {
                "cur_p": 0.0, "prev_p": 0.0, "chg_p": 0.0, "chg_pct": 0.0, "week_pct": 0.0, "ma_dev": 0.0
            })
            c_p = p_info["cur_p"]
            w_p = p_info["week_pct"]
            m_dev = p_info["ma_dev"]
            
            # 状態アイコン判定 (4段階判定)
            is_overheated = (w_p >= 6.0 or m_dev >= 7.0)
            is_rising = (w_p >= 4.0 or m_dev >= 4.0)
            is_downturn = (w_p <= -5.0 or m_dev <= -5.0)
            
            if is_overheated:
                status_icon = "🔴 要確認"
            elif is_rising:
                status_icon = "🟡 上昇警戒"
            elif is_downturn:
                status_icon = "🔵 下落・原因確認"
            else:
                status_icon = "🟢 通常"
                
            det = app_data.get("portfolio_details", {}).get(code, {
                "buy_price": 0.0, "shares": 0, "gain_pct": 20.0, "annual_div": 0.0
            })
            b_p = float(det.get("buy_price", 0.0))
            shs = int(det.get("shares", 0))
            a_div = float(det.get("annual_div", 0.0))
            
            # 計算
            profit_loss = (c_p - b_p) * shs if (c_p > 0 and b_p > 0) else 0.0
            pl_pct = ((c_p - b_p) / b_p) * 100 if (c_p > 0 and b_p > 0) else 0.0
            total_div = a_div * shs if shs > 0 else 0.0
            yoc = (a_div / b_p) * 100 if b_p > 0 else 0.0
            div_years = (profit_loss / total_div) if total_div > 0 else 0.0
            
            balance_rows.append({
                "状態": status_icon,
                "コード": code,
                "銘柄名": name,
                "現在値": c_p,
                "取得単価": b_p,
                "評価損益": profit_loss,
                "損益率": pl_pct,
                "年間配当総額": total_div,
                "YOC(取得利回り)": yoc,
                "配当何年分": div_years
            })
            
        if balance_rows:
            df_balance = pd.DataFrame(balance_rows)
            
            col_sort1, col_sort2 = st.columns(2)
            with col_sort1:
                sort_col = st.selectbox(
                    "釣り合い一覧の並び替え基準",
                    ["配当何年分", "損益率", "評価損益", "YOC(取得利回り)", "年間配当総額", "取得単価", "現在値", "コード"],
                    index=0
                )
            with col_sort2:
                sort_order = st.selectbox("順序", ["降順 (▼)", "昇順 (▲)"], index=0)
                
            sort_ascending = (sort_order == "昇順 (▲)")
            df_balance = df_balance.sort_values(by=sort_col, ascending=sort_ascending)
            
            # 表示用の整形
            df_disp = df_balance.copy()
            df_disp["現在値"] = df_disp["現在値"].apply(lambda x: f"{x:,.1f} 円" if x > 0 else "-")
            df_disp["取得単価"] = df_disp["取得単価"].apply(lambda x: f"{x:,.2f} 円" if x > 0 else "-")
            df_disp["評価損益"] = df_disp["評価損益"].apply(lambda x: f"{'+' if x > 0 else ''}{x:,.0f} 円")
            df_disp["損益率"] = df_disp["損益率"].apply(lambda x: f"{'+' if x > 0 else ''}{x:.2f}%")
            df_disp["年間配当総額"] = df_disp["年間配当総額"].apply(lambda x: f"{x:,.0f} 円")
            df_disp["YOC(取得利回り)"] = df_disp["YOC(取得利回り)"].apply(lambda x: f"{x:.2f}%")
            df_disp["配当何年分"] = df_disp["配当何年分"].apply(lambda x: f"{x:.2f} 年分")
            
            show_cols = ['状態', 'コード', '銘柄名', '現在値', '取得単価', '評価損益', '損益率', '年間配当総額', 'YOC(取得利回り)', '配当何年分']
            st.markdown("### 📊 評価損益 × 配当金の釣り合い一覧")
            st.dataframe(df_disp[show_cols], use_container_width=True, hide_index=True)