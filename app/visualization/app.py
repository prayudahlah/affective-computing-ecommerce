import streamlit as st
from datetime import date, timedelta
from streamlit_autorefresh import st_autorefresh
from config import (
    PAGE_SIZE,
    ASUS_BLUE, BG_BORDER, TEXT_PRIMARY, TEXT_SECONDARY,
)
from components import (
    inject_css,
    render_header,
    render_kpi_cards,
    render_time_series,
    render_sentiment_emotion,
    render_top_products,
    render_reviews_table,
    render_alerts_table,
)
from db import (
    get_kpi_metrics,
    get_time_series_rating,
    get_sentiment_distribution,
    get_emotion_distribution,
    get_top_products_by_rating,
    get_reviews_page,
    get_total_reviews_count,
    get_alerts_page,
    get_total_alerts_count,
    get_products,
)

st.set_page_config(
    page_title="ASUS Monitoring Sentimen Shopee",
    page_icon="asus_logo.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()
st_autorefresh(interval=5000)

default_from = date.today() - timedelta(days=7)
default_to   = date.today()

for pk, ak in {
    "pending_date_from": "filter_date_from",
    "pending_date_to": "filter_date_to",
    "pending_product": "filter_product",
    "pending_sentiment": "filter_sentiment",
}.items():
    if pk in st.session_state:
        st.session_state[ak] = st.session_state.pop(pk)

ALL_PRODUCT = "__all__"

with st.sidebar:
    st.markdown(
        f"""<div style="padding:0.5rem 0 1.2rem;border-bottom:1px solid {BG_BORDER};
margin-bottom:1.2rem;">
<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.1em;
text-transform:uppercase;color:{TEXT_SECONDARY};">ASUS Indonesia</div>
<div style="font-size:1.05rem;font-weight:800;color:{TEXT_PRIMARY};">Filter Dashboard</div>
</div>""",
        unsafe_allow_html=True,
    )

    st.markdown("**Kalender**")
    c1, c2 = st.columns(2)
    with c1:
        st.date_input("Dari", key="filter_date_from",
                       value=st.session_state.get("filter_date_from", default_from),
                       max_value=default_to)
    with c2:
        st.date_input("Sampai", key="filter_date_to",
                       value=st.session_state.get("filter_date_to", default_to),
                       min_value=st.session_state.get("filter_date_from", default_from),
                       max_value=date.today())

    st.markdown("**Rentang**")
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        if st.button("Hari Ini", use_container_width=True, key="btn_today"):
            st.session_state["pending_date_from"] = date.today()
            st.session_state["pending_date_to"] = date.today()
            st.rerun()
    with sc2:
        if st.button("7 Hari", use_container_width=True, key="btn_7d"):
            st.session_state["pending_date_from"] = date.today() - timedelta(days=7)
            st.session_state["pending_date_to"] = date.today()
            st.rerun()
    with sc3:
        if st.button("30 Hari", use_container_width=True, key="btn_30d"):
            st.session_state["pending_date_from"] = date.today() - timedelta(days=30)
            st.session_state["pending_date_to"] = date.today()
            st.rerun()

    st.divider()

    product_options = get_products()
    search_query = st.text_input("Cari Produk", key="product_search",
                                  placeholder="Ketik nama produk...")
    filtered = [p for p in product_options
                if search_query.lower() in p.lower()] if search_query else product_options
    selected = st.session_state.get("filter_product", ALL_PRODUCT)
    if selected != ALL_PRODUCT and selected not in filtered:
        selected = ALL_PRODUCT
    st.selectbox("Produk",
                  options=[ALL_PRODUCT, *filtered],
                  format_func=lambda x: "Semua Produk" if x == ALL_PRODUCT else x,
                  key="filter_product")

    st.divider()

    st.pills(
        "Sentimen",
        ["Positif", "Negatif"],
        selection_mode="multi",
        default=st.session_state.get("filter_sentiment", ["Positif", "Negatif"]),
        key="filter_sentiment",
    )

    st.divider()

    if st.button("Reset Filter", use_container_width=True, key="btn_reset"):
        for k in ["pending_date_from", "pending_date_to", "pending_product",
                   "pending_sentiment"]:
            st.session_state.pop(k, None)
        st.session_state["pending_date_from"] = default_from
        st.session_state["pending_date_to"] = default_to
        st.session_state["pending_product"] = ALL_PRODUCT
        st.session_state["pending_sentiment"] = ["Positif", "Negatif"]
        st.session_state["review_page"] = 0
        st.session_state["alert_page"] = 0
        st.rerun()

sel_prod = st.session_state.get("filter_product", ALL_PRODUCT)
sel_sent = st.session_state.get("filter_sentiment", ["Positif", "Negatif"])

filters = {
    "date_from": st.session_state.get("filter_date_from", default_from),
    "date_to": st.session_state.get("filter_date_to", default_to),
    "product": None if sel_prod == ALL_PRODUCT else sel_prod,
    "sentiment": sel_sent,
}

if "review_page" not in st.session_state:
    st.session_state.review_page = 0
if "alert_page" not in st.session_state:
    st.session_state.alert_page = 0

filter_key = str(filters)
if st.session_state.get("_last_filter_key") != filter_key:
    st.session_state.review_page = 0
    st.session_state.alert_page  = 0
    st.session_state["_last_filter_key"] = filter_key

render_header()
st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

metrics = get_kpi_metrics(filters)
render_kpi_cards(metrics)

st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

df_ts = get_time_series_rating(filters)
render_time_series(df_ts)

st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

df_sent = get_sentiment_distribution(filters)
df_emo  = get_emotion_distribution(filters)
render_sentiment_emotion(df_sent, df_emo)

st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

df_products = get_top_products_by_rating(filters)
render_top_products(df_products)

st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

total_reviews = get_total_reviews_count(filters)
df_reviews    = get_reviews_page(
    filters, limit=PAGE_SIZE,
    offset=st.session_state.review_page * PAGE_SIZE,
)
render_reviews_table(df_reviews, st.session_state.review_page, total_reviews, PAGE_SIZE)

st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

total_alerts = get_total_alerts_count(filters)
df_alerts    = get_alerts_page(
    filters, limit=PAGE_SIZE,
    offset=st.session_state.alert_page * PAGE_SIZE,
)
render_alerts_table(df_alerts, st.session_state.alert_page, total_alerts, PAGE_SIZE)

