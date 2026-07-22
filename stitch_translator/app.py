# Mobile-first Streamlit UI for Crochet Stitch Translator.
# Run from the repository root with:
# python3 -m streamlit run stitch_translator/app.py

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st
from typing import Optional
import streamlit.components.v1 as components

APP_VERSION = "v1.9a"

st.markdown("""
<style>
/* v1.8 UI polish */
h1 {
    color: #5f73a8 !important;
    margin-bottom: 1.2rem !important;
}
.stTextInput {
    margin-top: 0.5rem !important;
}
details {
    margin-top: 0.4rem !important;
}
</style>
""", unsafe_allow_html=True)

FEEDBACK_FORM_URL = "https://forms.gle/dNr7BXJuVaaosGyw6"
BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
KNOWLEDGE_BASE_DIR = REPO_ROOT / "knowledge_base"
SOURCE_CSV = KNOWLEDGE_BASE_DIR / "data" / "master_stitches.csv"
SEARCH_INDEX_CSV = BASE_DIR / "stitches_1_9_search_index.csv"
SYMBOLS_DIR = KNOWLEDGE_BASE_DIR / "symbols"

SUPPORTED_LANGS = {
    "en": {"label": "English", "short": "English"},
    "zh-Hant": {"label": "繁體中文", "short": "繁中"},
    "zh-Hans": {"label": "简体中文", "short": "简中"},
    "ja": {"label": "日本語", "short": "日本語"},
}

UI_TEXT = {
    "en": {
        "title": "🧶 Crochet Stitch Translator",
        "placeholder": "dc, double crochet, 長針, 长针, 長編み",
        "hint": "Enter a stitch name or abbreviation.",
        "search_label": "Search",
        "no_result": "No matching stitch found.",
        "try": "Try another term, spelling, or abbreviation.",
        "results": "Results",
        "possible": "Possible matches",
        "symbol_label": "Symbol",
        "feedback_title": "Feedback to developer",
        "feedback_text": "Found a wrong translation, missing stitch, or display problem? Please send feedback using the form below.",
        "feedback_button": "Open feedback form",
        "privacy_note": "This tool may collect feedback and search-related information to improve the database. Please do not enter personal information.",
        "terminology_note": "🧶 Some crochet terms may differ between US and UK patterns.",
        "tutorial_button": "🎥 Search Tutorials",
        "tutorial_note": "Searches YouTube for related crochet tutorials.",
    },
    "zh-Hant": {
        "title": "🧶 鈎織針法翻譯器",
        "placeholder": "dc, double crochet, 長針, 长针, 長編み",
        "hint": "請輸入針法名稱或縮寫。",
        "search_label": "搜尋",
        "no_result": "找不到相符針法。",
        "try": "可試另一個名稱、縮寫或不同寫法。",
        "results": "搜尋結果",
        "possible": "可能相關",
        "symbol_label": "符號 / SYMBOL",
        "feedback_title": "Feedback to developer",
        "feedback_text": "如果發現翻譯錯誤、缺少針法或顯示問題，請使用以下表格回報。",
        "feedback_button": "開啟意見回報表格",
        "privacy_note": "本工具可能會收集意見回報及搜尋相關資料，用作改善資料庫。請勿輸入個人資料。",
        "terminology_note": "🧶 美式與英式織圖的部分術語可能不同。",
        "tutorial_button": "🎥 搜尋教學",
        "tutorial_note": "在 YouTube 搜尋相關鈎織教學。",
    },
    "zh-Hans": {
        "title": "🧶 钩织针法翻译器",
        "placeholder": "dc, double crochet, 長針, 长针, 長編み",
        "hint": "请输入针法名称或缩写。",
        "search_label": "搜索",
        "no_result": "找不到相符针法。",
        "try": "可试另一个名称、缩写或不同写法。",
        "results": "搜索结果",
        "possible": "可能相关",
        "symbol_label": "符号 / SYMBOL",
        "feedback_title": "Feedback to developer",
        "feedback_text": "如果发现翻译错误、缺少针法或显示问题，请使用以下表格回报。",
        "feedback_button": "开启意见回报表格",
        "privacy_note": "本工具可能会收集意见回报及搜索相关资料，用作改善资料库。请勿输入个人资料。",
        "terminology_note": "🧶 美式与英式图解的部分术语可能不同。",
        "tutorial_button": "🎥 搜索教程",
        "tutorial_note": "在 YouTube 搜索相关钩织教程。",
    },
    "ja": {
        "title": "🧶 かぎ針編みステッチ翻訳",
        "placeholder": "dc, double crochet, 長針, 长针, 長編み",
        "hint": "編み目の名前または略語を入力してください。",
        "search_label": "検索",
        "no_result": "一致する編み目が見つかりません。",
        "try": "別の名前、略語、表記で試してください。",
        "results": "検索結果",
        "possible": "候補",
        "symbol_label": "記号 / SYMBOL",
        "feedback_title": "Feedback to developer",
        "feedback_text": "翻訳ミス、不足しているステッチ、表示の問題があれば、以下のフォームから送信してください。",
        "feedback_button": "フィードバックフォームを開く",
        "privacy_note": "このツールはデータベース改善のため、フィードバックや検索関連情報を収集する場合があります。個人情報は入力しないでください。",
        "terminology_note": "🧶 アメリカ式とイギリス式のパターンでは、一部の用語が異なる場合があります。",
        "tutorial_button": "🎥 チュートリアルを検索",
        "tutorial_note": "関連するかぎ針編みチュートリアルを YouTube で検索します。",
    },
}

# Small built-in Traditional/Simplified normalisation for search.
# Not a full converter. It only covers common crochet/data terms.
ZH_VARIANTS = str.maketrans({
    "钩": "鈎", "勾": "鈎", "针": "針", "枣": "棗", "长": "長", "短": "短", "锁": "鎖",
    "编": "編", "织": "織", "线": "線", "绕": "繞", "组": "組", "圈": "圈",
    "环": "環", "双": "雙", "单": "單", "减": "減", "加": "加", "针": "針",
    "裏": "裡", "里": "裡", "钩": "鈎", "辫": "辮", "结": "結", "记": "記",
})

SEARCH_COLUMNS = [
    "US_term", "US_term_alias", "US_abb", "US_abb1",
    "UK_term", "UK_term_alias", "UK_abb", "UK_abb1",
    "Chinese_term", "Chinese_term_alias", "Chinese_abb",
    "Japanese", "Japanese_alias",
]

DISPLAY_COLUMNS = ["US_term", "US_abb", "UK_term", "UK_abb", "Chinese_term", "Chinese_abb", "Japanese"]

ZH_HANS_DISPLAY = str.maketrans({
    "鈎": "钩", "針": "针", "鎖": "锁", "辮": "辫", "環": "环",
    "狀": "状", "長": "长", "併": "并", "內": "内", "繞": "绕",
    "線": "线", "斷": "断", "滿": "满", "輕": "轻", "顏": "颜",
    "轉": "转", "縫": "缝", "連": "连", "單": "单", "雙": "双",
})


def init_page() -> None:
    st.set_page_config(
        page_title="Crochet Stitch Translator",
        page_icon="🧶",
        layout="centered",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
        <style>
        .block-container { padding-top: 0.35rem; padding-bottom: 1.2rem; max-width: 720px; overflow-x: hidden; }
        header, footer { visibility: hidden; }
        [data-testid="stSidebar"] { display: none; }

        .topbar-iframe { margin: 0; padding: 0; }
        .headline-spacer { height: clamp(1.25rem, 5vh, 2.6rem); }
        .app-title { font-size: clamp(1.95rem, 8.8vw, 3.0rem); font-weight: 800; line-height: 1.08; margin: 0 0 1.15rem 0; letter-spacing: -0.04em; color:#3f4f7a !important; -webkit-text-fill-color:#3f4f7a !important; }
        @media (prefers-color-scheme: dark) {
            .app-title { color:#7f8fbd !important; -webkit-text-fill-color:#7f8fbd !important; }
            .hint { color:#9ca3af !important; -webkit-text-fill-color:#9ca3af !important; }
        }
        .hint { margin-top: -0.25rem; color: #6b7280 !important; -webkit-text-fill-color:#6b7280 !important; font-size: .92rem; }
        :root { color-scheme: light; }
        .terminology-note { margin-top: 1.15rem; margin-bottom: .65rem; padding: .65rem .75rem; border-radius: 12px; background: #f7f4ee !important; color: #4f4638 !important; font-size: .88rem; line-height: 1.42; }
        .result-card { border: 1px solid #e5e7eb !important; border-radius: 16px; padding: 1rem; margin: .75rem 0; background: #fffdf9 !important; color: #111827 !important; -webkit-text-fill-color: #111827; }
        .result-card * { color-scheme: light; }
        .term-row { display: grid; grid-template-columns: 88px 1fr; gap: .45rem; padding: .28rem 0; border-bottom: 1px solid #f2f2f2 !important; background: transparent !important; }
        .term-row:last-child { border-bottom: 0 !important; }
        .term-label { color: #6b7280 !important; -webkit-text-fill-color: #6b7280; font-size: .9rem; }
        .term-value { color: #111827 !important; -webkit-text-fill-color: #111827; font-weight: 600; }
        .small-note { color: #6b7280 !important; -webkit-text-fill-color: #6b7280; font-size: .88rem; margin-top: .5rem; }
        .symbol-card { border: 1px solid #e5e7eb !important; border-radius: 16px; padding: 1rem; margin: .75rem 0; background: #fffdf9 !important; text-align: center; min-height: 180px; display:flex; flex-direction:column; justify-content:flex-start; align-items:center; }
        .symbol-title { color: #6b46c1 !important; -webkit-text-fill-color:#6b46c1 !important; font-size: .88rem; font-weight: 700; margin-bottom: .85rem; letter-spacing: .02em; }
        .symbol-image { width:100%; display:flex; justify-content:center; align-items:center; flex:1; }
        .symbol-image svg { max-width: 92px !important; max-height: 118px !important; width: 92px !important; height: auto !important; display:block; margin:0 auto; }
        .symbol-missing { color:#9ca3af !important; font-size:.85rem; padding-top:2rem; }
        .feedback { margin-top: 1.2rem; padding-top: 1.2rem; border-top: 1px solid #eee; color: #666; font-size: .9rem; }
        .footer-push { height: min(22vh, 170px); }
        .feedback-box { border: 1px solid #eee; border-radius: 14px; padding: .85rem; background: #fff !important; color:#111827 !important; margin-top: .6rem; }
        /* Real Streamlit language selector. More reliable than iframe component. */
        div[data-testid="stSelectbox"] { max-width: 142px; margin-left: auto; margin-bottom: 0; }
        div[data-testid="stSelectbox"] label { display: none; }
        div[data-testid="stSelectbox"] div,
        div[data-testid="stSelectbox"] span,
        div[data-testid="stSelectbox"] input,
        div[data-testid="stSelectbox"] p { color:#111827 !important; -webkit-text-fill-color:#111827 !important; }
        div[data-baseweb="select"] > div { min-height: 34px; font-size: .82rem; padding-left: .15rem; padding-right: .15rem; border-radius: 14px; background:#f1f3f7 !important; border:0 !important; color:#111827 !important; -webkit-text-fill-color:#111827 !important; }
        div[data-baseweb="select"] * { color:#111827 !important; -webkit-text-fill-color:#111827 !important; }
        div[data-baseweb="select"] svg { color:#4b5563 !important; fill:#4b5563 !important; }
        div[data-baseweb="popover"] * { color:#111827 !important; -webkit-text-fill-color:#111827 !important; background-color:#ffffff !important; }
        @media (prefers-color-scheme: dark) {
            div[data-testid="stSelectbox"] div,
            div[data-testid="stSelectbox"] span,
            div[data-testid="stSelectbox"] input,
            div[data-testid="stSelectbox"] p { color:#111827 !important; -webkit-text-fill-color:#111827 !important; }
            div[data-baseweb="select"] > div { background:#f1f3f7 !important; color:#111827 !important; -webkit-text-fill-color:#111827 !important; }
            div[data-baseweb="select"] * { color:#111827 !important; -webkit-text-fill-color:#111827 !important; }
            div[data-baseweb="select"] svg { color:#4b5563 !important; fill:#4b5563 !important; }
        }
        .stTextInput input { font-size: 1.05rem; padding: .85rem .75rem; margin-top: .15rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def normalise_text(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    text = text.replace("綫", "線").replace("线", "線")
    text = text.translate(ZH_VARIANTS)
    text = re.sub(r"[\s\-_/]+", " ", text)
    text = re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff ]+", "", text)
    return text.strip()


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text or ""))


def loose_cjk_key(text: str) -> str:
    """Looser Chinese search key for user input such as 棗形 / 棗形花 / 棗形針."""
    text = normalise_text(text)
    if not has_cjk(text):
        return text
    text = re.sub(r"\s+", "", text)
    # Remove common stitch/noun suffixes only for fuzzy Chinese lookup.
    # This does NOT change what is displayed to the user.
    text = re.sub(r"(針法|編み目|編み|針目|針|针|花|目)$", "", text)
    return text


def split_aliases(value: object) -> list[str]:
    if pd.isna(value) or str(value).strip() == "":
        return []
    raw = str(value)
    parts = re.split(r"[;,/|、，]+", raw)
    return [p.strip() for p in parts if p.strip()]


@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    if not SOURCE_CSV.exists():
        st.error(f"Missing data file: {SOURCE_CSV.name}")
        st.stop()
    df = pd.read_csv(SOURCE_CSV).fillna("")
    for col in DISPLAY_COLUMNS + SEARCH_COLUMNS + ["symbol_file", "search_status", "tutorial_search"]:
        if col not in df.columns:
            df[col] = ""
    active_mask = df["search_status"].astype(str).str.strip().str.lower()
    df = df[(active_mask == "") | (active_mask == "active")].reset_index(drop=True)
    return df


@st.cache_data(show_spinner=False)
def build_index(df: pd.DataFrame) -> pd.DataFrame:
    if SEARCH_INDEX_CSV.exists():
        idx = pd.read_csv(SEARCH_INDEX_CSV).fillna("")
        required = {"row_id", "search_term"}
        if required.issubset(idx.columns):
            idx["norm"] = idx["search_term"].map(normalise_text)
            return idx

    rows = []
    for row_id, row in df.iterrows():
        for col in SEARCH_COLUMNS:
            values = [row.get(col, "")] if "alias" not in col.lower() else split_aliases(row.get(col, ""))
            for term in values:
                term = str(term).strip()
                norm = normalise_text(term)
                if term and norm:
                    rows.append({"row_id": row_id, "search_term": term, "norm": norm, "source_col": col})
    return pd.DataFrame(rows).drop_duplicates(subset=["row_id", "norm"])


def detect_lang_from_browser() -> None:
    # Streamlit cannot directly read navigator.language on first render.
    # This tiny component writes ?browser_lang=xx to the URL once, then Streamlit reruns.
    if "browser_lang_checked" not in st.session_state:
        components.html(
            """
            <script>
            const params = new URLSearchParams(window.parent.location.search);
            if (!params.has('browser_lang')) {
                const lang = navigator.language || navigator.userLanguage || 'en';
                params.set('browser_lang', lang);
                window.parent.history.replaceState({}, '', window.parent.location.pathname + '?' + params.toString());
                window.parent.location.reload();
            }
            </script>
            """,
            height=0,
        )
        st.session_state.browser_lang_checked = True


def map_browser_lang(raw: Optional[str]) -> str:
    raw = (raw or "").lower()
    if raw.startswith("zh"):
        if any(x in raw for x in ["hant", "tw", "hk", "mo"]):
            return "zh-Hant"
        if any(x in raw for x in ["hans", "cn", "sg"]):
            return "zh-Hans"
        return "zh-Hant"
    if raw.startswith("ja"):
        return "ja"
    if raw.startswith("en"):
        return "en"
    return "en"


def score_match(query_norm: str, term_norm: str) -> float:
    if not query_norm or not term_norm:
        return 0
    if query_norm == term_norm:
        return 100

    # Chinese users often type the core phrase only, e.g. 棗形, 棗形花, 棗形針.
    # Use a looser CJK key so suffix variation does not block a good result.
    if has_cjk(query_norm):
        q_loose = loose_cjk_key(query_norm)
        t_loose = loose_cjk_key(term_norm)
        if q_loose and t_loose:
            if q_loose == t_loose:
                return 96
            if len(q_loose) >= 2 and (q_loose in t_loose or t_loose in q_loose):
                return 90

    # Avoid the old bug: a long typo such as "single crochete" matched short
    # abbreviations like "ch" because "ch" appears inside the query.
    # Only allow query-in-term partial matching, never short term-in-query matching.
    if len(query_norm) >= 3 and query_norm in term_norm:
        return 86

    if len(query_norm) <= 2:
        return 0

    ratio = SequenceMatcher(None, query_norm, term_norm).ratio()
    return ratio * 100


def search(query: str, df: pd.DataFrame, idx: pd.DataFrame, limit: int = 8) -> pd.DataFrame:
    q = normalise_text(query)
    if not q:
        return pd.DataFrame()

    # Exact match wins. If exact rows exist, stop there.
    # This prevents "dc" from returning dc inc / dc dec / dc2tog etc.
    exact_items = idx[idx["norm"] == q]

    # For Chinese, also treat suffix-normalised matches as high-confidence exact-ish.
    # Example: 棗形 / 棗形花 should match 棗形針.
    if exact_items.empty and has_cjk(q):
        q_loose = loose_cjk_key(q)
        if q_loose:
            exact_items = idx[idx["norm"].map(loose_cjk_key) == q_loose]

    if not exact_items.empty:
        scored = [
            (int(item["row_id"]), 100.0, item.get("search_term", ""), item.get("source_col", ""))
            for _, item in exact_items.iterrows()
        ]
    else:
        scored = []
        for _, item in idx.iterrows():
            s = score_match(q, item["norm"])
            # Fuzzy typo matching should be stricter than partial matching.
            if s >= 74:
                scored.append((int(item["row_id"]), float(s), item.get("search_term", ""), item.get("source_col", "")))

    if not scored:
        return pd.DataFrame()

    best = {}
    for row_id, s, term, col in scored:
        if row_id not in best or s > best[row_id][0]:
            best[row_id] = (s, term, col)

    ordered = sorted(best.items(), key=lambda x: x[1][0], reverse=True)[:limit]
    result_rows = []
    for row_id, (s, term, col) in ordered:
        row = df.loc[row_id].copy()
        row["_score"] = round(s, 1)
        row["_matched_term"] = term
        row["_matched_col"] = col
        result_rows.append(row)
    return pd.DataFrame(result_rows)


def needs_us_uk_choice(query: str, results: pd.DataFrame) -> bool:
    q = normalise_text(query)
    if results.empty or not q or not re.fullmatch(r"[a-z0-9 ]+", q):
        return False
    if len(results) < 2:
        return False
    matched_cols = set(str(x) for x in results.get("_matched_col", []))
    has_us = any(c.startswith("US_") for c in matched_cols)
    has_uk = any(c.startswith("UK_") for c in matched_cols)
    return has_us and has_uk


def filter_by_terminology(results: pd.DataFrame, choice: str) -> pd.DataFrame:
    if results.empty or choice == "not_sure":
        return results
    prefix = "US_" if choice == "us" else "UK_"
    filtered = results[results["_matched_col"].astype(str).str.startswith(prefix)]
    return filtered if not filtered.empty else results


def zh_hans_display(value: str) -> str:
    return str(value or "").translate(ZH_HANS_DISPLAY)


def build_tutorial_search_query(row: pd.Series, ui_lang: str) -> str:
    canonical = str(row.get("US_term", "")).strip()
    localized = ""
    if ui_lang == "zh-Hant":
        localized = str(row.get("Chinese_term", "")).strip()
    elif ui_lang == "zh-Hans":
        localized = zh_hans_display(str(row.get("Chinese_term", "")).strip())
    elif ui_lang == "ja":
        localized = str(row.get("Japanese", "")).strip()

    parts = ["crochet", canonical]
    if localized and localized.casefold() != canonical.casefold():
        parts.append(localized)
    return " ".join(part for part in parts if part).strip()


def build_tutorial_search_url(row: pd.Series, ui_lang: str) -> str:
    query = build_tutorial_search_query(row, ui_lang)
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


def render_result_card(row: pd.Series, text: dict) -> None:
    def raw(col: str) -> str:
        return str(row.get(col, "")).strip()

    rows = []

    if raw("US_term"):
        us = raw("US_term") + (f" ({raw('US_abb')})" if raw("US_abb") else "")
        rows.append(("US", us))

    if raw("UK_term"):
        uk = raw("UK_term") + (f" ({raw('UK_abb')})" if raw("UK_abb") else "")
        rows.append(("UK", uk))

    if raw("Chinese_term"):
        zh = raw("Chinese_term") + (f" ({raw('Chinese_abb')})" if raw("Chinese_abb") else "")
        rows.append(("中文", zh))

    if raw("Japanese"):
        rows.append(("日本語", raw("Japanese")))

    note = raw("ambiguity_note")
    internal_note = "intentional equivalent" in note.lower() or "search-friendly" in note.lower()

    row_html = "".join(
        f'<div class="term-row"><div class="term-label">{label}</div><div class="term-value">{value}</div></div>'
        for label, value in rows
    )

    note_html = f'<div class="small-note">⚠️ {note}</div>' if note and not internal_note else ""

    symbol_file = raw("symbol_file")
    symbol_inner = ""
    has_symbol = False

    if symbol_file:
        symbol_path = SYMBOLS_DIR / symbol_file
        if symbol_path.exists():
            try:
                svg_markup = symbol_path.read_text(encoding="utf-8")
                # Inline the SVG inside the card so it stays inside the bordered symbol area.
                symbol_inner = f'<div class="symbol-image">{svg_markup}</div>'
                has_symbol = True
            except Exception:
                # If the file cannot be read, hide the symbol card rather than showing a broken empty box.
                has_symbol = False

    if has_symbol:
        left, right = st.columns([3, 1], gap="medium")
        with left:
            st.markdown(
                f"""
                <div class="result-card">
                  {row_html}
                  {note_html}
                </div>
                """,
                unsafe_allow_html=True,
            )
        with right:
            st.markdown(
                f"""
                <div class="symbol-card">
                  <div class="symbol-title">{text.get('symbol_label', 'Symbol')}</div>
                  {symbol_inner}
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        # No symbol for this stitch: show only the text result card.
        st.markdown(
            f"""
            <div class="result-card">
              {row_html}
              {note_html}
            </div>
            """,
            unsafe_allow_html=True,
        )

    if raw("tutorial_search").lower() == "yes":
        ui_lang = st.session_state.get("ui_lang", "en")
        st.link_button(text["tutorial_button"], build_tutorial_search_url(row, ui_lang))
        st.caption(text["tutorial_note"])



def render_language_bar(selected: str) -> str:
    """Use native Streamlit selectbox so changing language triggers a real rerun.
    The earlier iframe selector looked better, but did not reliably update the main app state on mobile.
    """
    lang_options = list(SUPPORTED_LANGS.keys())
    index = lang_options.index(selected) if selected in lang_options else 0

    chosen = st.selectbox(
        "Language",
        options=lang_options,
        index=index,
        format_func=lambda code: f"🌐 {SUPPORTED_LANGS[code]['short']}",
        label_visibility="collapsed",
        key="ui_lang_select",
    )
    st.session_state["ui_lang"] = chosen
    return chosen

def render_headline(text: dict) -> None:
    # Separate headline from the language bar so it can sit lower on mobile.
    st.markdown(
        f"""
        <div class="headline-spacer"></div>
        <div class="app-title">{text['title']}</div>
        """,
        unsafe_allow_html=True,
    )


def get_query_param(params, key: str, default: str = "") -> str:
    value = params.get(key, default)
    if isinstance(value, list):
        return value[0] if value else default
    return str(value) if value is not None else default

def main() -> None:
    init_page()
    detect_lang_from_browser()

    params = st.query_params
    browser_lang = get_query_param(params, "browser_lang", "")
    default_lang = map_browser_lang(browser_lang)

    lang_options = list(SUPPORTED_LANGS.keys())

    if "ui_lang" not in st.session_state:
        initial_lang = get_query_param(params, "ui_lang", default_lang)
        st.session_state["ui_lang"] = initial_lang if initial_lang in lang_options else "en"

    selected = render_language_bar(st.session_state["ui_lang"])
    text = UI_TEXT[selected]
    render_headline(text)

    df = load_data()
    idx = build_index(df)

    query = st.text_input(
        text["search_label"],
        placeholder=text["placeholder"],
        label_visibility="collapsed",
        key="search_query",
    )
    st.markdown(f'<div class="hint">{text["hint"]}</div>', unsafe_allow_html=True)
    if query.strip():
        results = search(query, df, idx)
        if results.empty:
            st.warning(text["no_result"])
            st.caption(text["try"])
        else:
            if needs_us_uk_choice(query, results):
                choice = st.radio(
                    "Terminology",
                    options=["us", "uk", "not_sure"],
                    format_func=lambda x: {
                        "us": "US term",
                        "uk": "UK term",
                        "not_sure": "Not sure / show both",
                    }[x],
                    horizontal=True,
                    label_visibility="collapsed",
                    key="terminology_choice",
                )
                results = filter_by_terminology(results, choice)

            st.markdown(f"### {text['results']}")
            for _, row in results.iterrows():
                render_result_card(row, text)

    if not query.strip():
        st.markdown('<div class="footer-push"></div>', unsafe_allow_html=True)

    st.markdown(f'<div class="terminology-note">{text["terminology_note"]}</div>', unsafe_allow_html=True)
    st.markdown('<div class="feedback"></div>', unsafe_allow_html=True)
    with st.expander(f"✉️ {text['feedback_title']}", expanded=False):
        st.caption(text["feedback_text"])
        st.link_button(text["feedback_button"], FEEDBACK_FORM_URL)
        st.caption(text["privacy_note"])
        st.caption(f"{APP_VERSION} · Feedback is collected through Google Forms.")


if __name__ == "__main__":
    main()
