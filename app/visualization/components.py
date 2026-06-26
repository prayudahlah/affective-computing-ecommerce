import pandas as pd
import altair as alt
import streamlit as st

from config import (
    BG_BASE, BG_SURFACE, BG_ELEVATED, BG_BORDER,
    ASUS_BLUE, ASUS_BLUE_DIM,
    ACCENT_RED, ACCENT_RED_DIM, ACCENT_PINK,
    ACCENT_PURPLE, ACCENT_PURPLE_DIM,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ALERT_TYPE_LABELS, SENTIMENT_COLORS, EMOTION_COLORS,
    RATING_THRESHOLD,
)

def _short_product_name(name):
    if name and "/" in name:
        return name.split("/")[0].strip()
    return name or ""


def _chart_cfg(chart, height=320):
    return (
        chart
        .properties(
            height=height, background=BG_SURFACE,
            padding={"left": 28, "top": 20, "right": 28, "bottom": 24},
            autosize={"type": "fit", "contains": "padding"},
        )
        .configure(background=BG_SURFACE)
        .configure_view(strokeWidth=0, fill=BG_SURFACE)
        .configure_axis(
            labelColor=TEXT_SECONDARY,
            titleColor=TEXT_SECONDARY,
            gridColor=BG_BORDER,
            domainColor=BG_BORDER,
            tickColor=BG_BORDER,
            labelFont="system-ui, sans-serif",
            titleFont="system-ui, sans-serif",
            labelFontSize=11,
        )
        .configure_legend(
            labelColor=TEXT_SECONDARY,
            titleColor=TEXT_SECONDARY,
            labelFont="system-ui, sans-serif",
            titleFont="system-ui, sans-serif",
            labelFontSize=12,
        )
    )


def inject_css():
    st.markdown(
        f"""
        <style>
        html {{
            font-size: 17px;
        }}
        html, body,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        .main {{
            background-color: {BG_BASE} !important;
            color: {TEXT_PRIMARY};
        }}
        header[data-testid="stHeader"] {{
            background: {BG_SURFACE} !important;
            border-bottom: 1px solid {BG_BORDER};
        }}
        [data-testid="stDecoration"] {{
            display: none;
        }}
        [data-testid="stAppViewContainer"] {{
            margin-top: -0.75rem;
        }}
        [data-testid="stAppViewContainer"] > .main > div {{
            padding-top: 0;
        }}

        [data-testid="stSidebar"] {{
            background-color: {BG_SURFACE} !important;
            border-right: 1px solid {BG_BORDER};
        }}
        [data-testid="stSidebar"] * {{
            color: {TEXT_PRIMARY} !important;
        }}
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] .stDateInput input {{
            background: {BG_ELEVATED} !important;
            border: 1px solid {BG_BORDER} !important;
            color: {TEXT_PRIMARY} !important;
            border-radius: 6px;
        }}
        [data-testid="stSidebar"] input::placeholder {{
            color: {TEXT_SECONDARY} !important;
            opacity: 1;
        }}
        [data-testid="stSidebar"] .stMultiSelect [data-baseweb="select"] {{
            background: {BG_ELEVATED} !important;
            border: 1px solid {BG_BORDER} !important;
        }}
        [data-testid="stSidebar"] .stMultiSelect span {{
            color: {TEXT_PRIMARY} !important;
        }}
        [data-testid="stSelectbox"] > div > div {{
            background: {BG_ELEVATED} !important;
            border: 1px solid {BG_BORDER} !important;
            border-radius: 6px;
        }}
        [data-testid="stSelectbox"] input {{
            color: {TEXT_PRIMARY} !important;
        }}
        [data-baseweb="popover"] ul {{
            background: {BG_SURFACE} !important;
            border: 1px solid {BG_BORDER} !important;
        }}
        [data-baseweb="popover"] li {{
            color: {TEXT_PRIMARY} !important;
            background: {BG_SURFACE} !important;
        }}
        [data-baseweb="popover"] li:hover {{
            background: {BG_ELEVATED} !important;
        }}

        [data-testid="stSidebar"] .stButton > button {{
            background: {ASUS_BLUE} !important;
            color: #fff !important;
            border: none;
            border-radius: 6px;
            font-weight: 600;
            font-size: 0.82rem;
            letter-spacing: 0.04em;
            width: 100%;
        }}
        [data-testid="stSidebar"] .stButton > button:hover {{
            background: #1568B0 !important;
        }}

        .kpi-card {{
            background: {BG_SURFACE};
            border: 1px solid {BG_BORDER};
            border-left: 4px solid {ASUS_BLUE};
            border-radius: 8px;
            padding: 1.1rem 1.25rem 1rem;
            min-height: 114px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}
        .kpi-card.danger {{
            border-left-color: {ACCENT_RED};
        }}
        .kpi-label {{
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: {TEXT_SECONDARY};
            margin-bottom: 0.35rem;
        }}
        .kpi-value {{
            font-size: 2rem;
            font-weight: 700;
            color: {TEXT_PRIMARY};
            line-height: 1.1;
        }}
        .kpi-delta {{
            font-size: 0.75rem;
            font-weight: 500;
            margin-top: 0.4rem;
        }}
        .kpi-delta.up   {{ color: {ASUS_BLUE}; }}
        .kpi-delta.down {{ color: {ACCENT_RED}; }}
        .kpi-delta.flat {{ color: {TEXT_MUTED}; }}

        .section-header {{
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.09em;
            text-transform: uppercase;
            color: {TEXT_SECONDARY};
            margin-bottom: 0.9rem;
            padding-bottom: 0.45rem;
            border-bottom: 2px solid {ASUS_BLUE};
            display: inline-block;
        }}

        hr.section-divider {{
            border: none;
            border-top: 1px solid {BG_BORDER};
            margin: 1.8rem 0;
        }}

        .pagination-info {{
            font-size: 0.78rem;
            color: {TEXT_SECONDARY};
            text-align: right;
            padding-top: 0.4rem;
        }}

        
        .badge {{
            display: inline-block;
            padding: 2px 10px;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.04em;
        }}
        .badge-Positive {{
            background: {ASUS_BLUE_DIM};
            color: {ASUS_BLUE};
        }}
        .badge-Negative {{
            background: {ACCENT_RED_DIM};
            color: {ACCENT_RED};
        }}


        .alert-dot {{
            display: inline-block;
            width: 8px; height: 8px;
            border-radius: 50%;
            margin-right: 8px;
            vertical-align: middle;
        }}
        .alert-dot.rating_drop {{
            background: {ACCENT_PURPLE};
        }}
        .alert-dot.sentiment_negative {{
            background: {ACCENT_RED};
        }}


        .review-row {{
            background: {BG_SURFACE};
            border: 1px solid {BG_BORDER};
            border-radius: 6px;
            padding: 0.6rem 0.8rem;
            margin-bottom: 0.4rem;
        }}
        .review-row.positive {{
            border-left: 3px solid {ASUS_BLUE};
        }}
        .review-row.negative {{
            border-left: 3px solid {ACCENT_RED};
        }}


        .section-header.model {{
            border-bottom-color: {ACCENT_PINK};
        }}


        .model-card {{
            background: {BG_SURFACE};
            border: 1px solid {BG_BORDER};
            border-top: 3px solid {ACCENT_PINK};
            border-radius: 8px;
            padding: 1rem 1.25rem;
            min-height: 90px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .model-card.sentiment {{
            border-top-color: {ASUS_BLUE};
        }}
        .model-card.emotion {{
            border-top-color: {ACCENT_PINK};
        }}
        .model-label {{
            font-size: 0.65rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: {TEXT_SECONDARY};
            margin-bottom: 0.25rem;
        }}
        .model-value {{
            font-size: 1.6rem;
            font-weight: 700;
            color: {TEXT_PRIMARY};
            line-height: 1.1;
        }}


        .stButton > button {{
            background: {BG_ELEVATED};
            color: {TEXT_PRIMARY};
            border: 1px solid {BG_BORDER};
            border-radius: 6px;
            font-size: 0.8rem;
        }}
        .stButton > button:hover {{
            background: {BG_BORDER};
        }}
        .stButton > button:disabled {{
            opacity: 0.35;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header():
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:0;">
            <div style="width:5px;height:50px;background:{ASUS_BLUE};
                        border-radius:3px;flex-shrink:0;"></div>
            <div>
                <div style="font-size:0.68rem;font-weight:700;letter-spacing:0.1em;
                            text-transform:uppercase;color:{TEXT_SECONDARY};">
                    ASUS Indonesia — Shopee Review Intelligence
                </div>
                <div style="font-size:1.5rem;font-weight:800;
                            color:{TEXT_PRIMARY};line-height:1.15;">
                    Monitoring Sentimen Produk
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _delta_html(value, suffix="", invert=False):
    if value is None:
        return f'<span class="kpi-delta flat">— tidak ada data sebelumnya</span>'
    good = (value > 0 and not invert) or (value < 0 and invert)
    bad  = (value < 0 and not invert) or (value > 0 and invert)
    cls  = "up" if good else ("down" if bad else "flat")
    arrow = "▲" if value > 0 else ("▼" if value < 0 else "—")
    sign  = "+" if value > 0 else ""
    return f'<span class="kpi-delta {cls}">{arrow} {sign}{value}{suffix} vs kemarin</span>'


def render_kpi_cards(metrics: dict):
    st.markdown('<div class="section-header">Ringkasan</div>', unsafe_allow_html=True)

    def _card(label, value, delta_html, is_danger, col):
        cls = "kpi-card danger" if is_danger else "kpi-card"
        with col:
            st.markdown(
                f"""
                <div class="{cls}">
                    <div class="kpi-label">{label}</div>
                    <div class="kpi-value">{value}</div>
                    {delta_html}
                </div>
                """,
                unsafe_allow_html=True,
            )

    row1 = st.columns(4)
    _card("Total Ulasan Hari Ini", str(metrics["total_today"]),
          _delta_html(metrics["total_delta"]), False, row1[0])
    _card("Sentimen Negatif Hari Ini",
          f"{metrics['pct_negative']:.1f}%",
          _delta_html(metrics["pct_negative_delta"], suffix="%", invert=True),
          True, row1[1])
    _card("Rata-rata Rating (10 mnt)",
          f"{metrics['avg_rating_now']:.2f}" if metrics['avg_rating_now'] is not None else "—",
          _delta_html(metrics["avg_rating_delta"]),
          False, row1[2])
    _card("Alert Terkirim", str(metrics["alert_count"]), "", True, row1[3])


def render_model_cards(metrics: dict):
    st.markdown(
        f'<div class="section-header model">Akurasi Model</div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    sent_val = f"{metrics.get('f1_sentiment'):.4f}" if metrics.get('f1_sentiment') is not None else "—"
    emo_val  = f"{metrics.get('f1_emotion'):.4f}" if metrics.get('f1_emotion') is not None else "—"

    with c1:
        st.markdown(
            f"""<div class="model-card sentiment">
                <div class="model-label">F1 Sentimen</div>
                <div class="model-value">{sent_val}</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""<div class="model-card emotion">
                <div class="model-label">F1 Emosi</div>
                <div class="model-value">{emo_val}</div>
            </div>""",
            unsafe_allow_html=True,
        )


def render_time_series(df: pd.DataFrame):
    st.markdown('<div class="section-header">Rata-rata Rating per 10 Menit</div>',
                unsafe_allow_html=True)

    if df.empty:
        st.info("Belum ada data untuk rentang waktu yang dipilih.")
    else:
        try:
            df["bucket"] = pd.to_datetime(df["bucket"])

            area = alt.Chart(df).mark_area(
                color=ASUS_BLUE, opacity=0.08, interpolate="monotone",
            ).encode(
                x=alt.X("bucket:T"),
                y=alt.Y("avg_rating:Q", scale=alt.Scale(domain=[1, 5])),
                y2=alt.Y2(value=1),
            )
            line = alt.Chart(df).mark_line(
                color=ASUS_BLUE, strokeWidth=2.5, interpolate="monotone",
                point=alt.OverlayMarkDef(color=ASUS_BLUE, size=55, opacity=0.9),
            ).encode(
                x=alt.X("bucket:T", title=None,
                        axis=alt.Axis(format="%d %b %H:%M", labelAngle=-30, tickCount=8)),
                y=alt.Y("avg_rating:Q", scale=alt.Scale(domain=[1, 5]), title="Rata-rata Rating"),
                tooltip=[
                    alt.Tooltip("bucket:T",       title="Waktu",           format="%d %b %H:%M"),
                    alt.Tooltip("avg_rating:Q",   title="Rata-rata Rating"),
                    alt.Tooltip("review_count:Q", title="Jumlah Ulasan"),
                ],
            )

            chart = _chart_cfg(alt.layer(area, line), height=320)
            st.altair_chart(chart, width='stretch', theme=None)
        except Exception as e:
            st.error(f"Gagal merender grafik: {e}")


def render_sentiment_emotion(df_sent: pd.DataFrame, df_emo: pd.DataFrame):
    col_l, col_r = st.columns(2, gap="large")

    with col_l:
        st.markdown('<div class="section-header">Distribusi Sentimen</div>',
                    unsafe_allow_html=True)
        if df_sent.empty:
            st.info("Tidak ada data.")
        else:
            domain = list(SENTIMENT_COLORS.keys())
            rng    = list(SENTIMENT_COLORS.values())
            donut = (
                alt.Chart(df_sent)
                .mark_arc(innerRadius=58, outerRadius=100,
                          stroke=BG_SURFACE, strokeWidth=2)
                .encode(
                    theta=alt.Theta("count:Q"),
                    color=alt.Color(
                        "sentiment:N",
                        scale=alt.Scale(domain=domain, range=rng),
                        legend=alt.Legend(title=None, orient="bottom", padding=14),
                    ),
                    tooltip=[
                        alt.Tooltip("sentiment:N", title="Sentimen"),
                        alt.Tooltip("count:Q",     title="Jumlah"),
                    ],
                )
            )
            st.altair_chart(
                _chart_cfg(donut, height=300),
                width='stretch',
                theme=None,
            )

    with col_r:
        st.markdown('<div class="section-header">Distribusi Emosi</div>',
                    unsafe_allow_html=True)
        if df_emo.empty:
            st.info("Tidak ada data.")
        else:
            emo_domain = list(EMOTION_COLORS.keys())
            emo_range  = list(EMOTION_COLORS.values())
            bar = (
                alt.Chart(df_emo)
                .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                .encode(
                    x=alt.X("count:Q", title="Jumlah Ulasan",
                             axis=alt.Axis(tickMinStep=1)),
                    y=alt.Y("emotion:N", sort="-x", title=None),
                    color=alt.Color(
                        "emotion:N",
                        scale=alt.Scale(domain=emo_domain, range=emo_range),
                        legend=None,
                    ),
                    tooltip=[
                        alt.Tooltip("emotion:N", title="Emosi"),
                        alt.Tooltip("count:Q",   title="Jumlah"),
                    ],
                )
            )
            st.altair_chart(
                _chart_cfg(bar, height=300),
                width='stretch',
                theme=None,
            )


def render_top_products(df: pd.DataFrame):
    st.markdown('<div class="section-header">Top 5 Produk — Rating Terendah</div>',
                unsafe_allow_html=True)

    if df.empty:
        st.info("Tidak ada data produk.")
        return

    for _, row in df.iterrows():
        pct_neg   = (row["neg_count"] / row["total_reviews"] * 100) if row["total_reviews"] > 0 else 0
        low       = row["avg_rating"] < RATING_THRESHOLD
        bar_color = ACCENT_RED if low else ASUS_BLUE
        bar_bg    = ACCENT_RED_DIM if low else ASUS_BLUE_DIM
        bar_width = int(row["avg_rating"] / 5 * 100)

        st.markdown(
            f"""
            <div style="background:{BG_SURFACE};border:1px solid {BG_BORDER};
                        border-radius:8px;padding:0.85rem 1.1rem;margin-bottom:0.55rem;">
                <div style="display:flex;justify-content:space-between;
                            align-items:baseline;margin-bottom:0.5rem;">
                    <span style="font-weight:600;font-size:0.93rem;color:{TEXT_PRIMARY};">
                        {_short_product_name(row['product_name'])}
                    </span>
                    <span style="font-size:0.82rem;color:{TEXT_SECONDARY};">
                        {row['total_reviews']} ulasan &nbsp;|&nbsp;
                        <span style="color:{ACCENT_RED};font-weight:600;">
                            {pct_neg:.0f}% negatif
                        </span>
                    </span>
                </div>
                <div style="display:flex;align-items:center;gap:10px;">
                    <div style="flex:1;background:{bar_bg};border-radius:999px;
                                height:7px;overflow:hidden;">
                        <div style="width:{bar_width}%;height:100%;
                                    background:{bar_color};border-radius:999px;"></div>
                    </div>
                    <span style="font-size:1rem;font-weight:700;
                                 color:{bar_color};min-width:36px;">
                        {row['avg_rating']:.2f}
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_reviews_table(df: pd.DataFrame, page: int, total: int, page_size: int):
    st.markdown('<div class="section-header">Ulasan Terbaru</div>',
                unsafe_allow_html=True)

    if df.empty:
        st.info("Tidak ada ulasan untuk filter yang dipilih.")
        return

    df = df.copy()
    df["create_time"] = pd.to_datetime(df["create_time"]).dt.strftime("%Y-%m-%d %H:%M")

    for _, row in df.iterrows():
        sent_class = row["sentiment"].lower()
        badge = f'<span class="badge badge-{row["sentiment"]}">{row["sentiment"]}</span>'
        stars = "★" * row["rating_star"] + "☆" * (5 - row["rating_star"])
        comment_trunc = (row["comment"][:80] + "…") if len(row["comment"]) > 80 else row["comment"]

        st.markdown(
            f"""
            <div class="review-row {sent_class}">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
                    <div style="flex:1;min-width:0;">
                        <div style="font-size:0.82rem;font-weight:600;color:{TEXT_PRIMARY};">
                            {_short_product_name(row["product_name"])}
                            <span style="font-size:0.7rem;color:{TEXT_MUTED};margin-left:8px;">
                                {row["create_time"]}
                            </span>
                        </div>
                        <div style="font-size:0.78rem;color:{TEXT_SECONDARY};margin-top:3px;">
                            {comment_trunc}
                        </div>
                    </div>
                    <div style="text-align:right;flex-shrink:0;min-width:100px;">
                        <div style="font-size:0.8rem;color:{TEXT_SECONDARY};letter-spacing:1px;">
                            {stars}
                        </div>
                        <div style="margin-top:3px;">
                            {badge}
                            <span class="badge" style="background:{BG_ELEVATED};color:{TEXT_SECONDARY};margin-left:4px;">
                                {row["emotion"]}
                            </span>
                        </div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    total_pages = max(1, (total + page_size - 1) // page_size)
    info_col, prev_col, next_col = st.columns([4, 1, 1])
    with info_col:
        st.markdown(
            f'<div class="pagination-info">Halaman {page + 1} dari {total_pages} '
            f'({total} ulasan)</div>',
            unsafe_allow_html=True,
        )
    with prev_col:
        if st.button("◀", key="prev_review", disabled=(page == 0), width='stretch'):
            st.session_state.review_page = page - 1
            st.rerun()
    with next_col:
        if st.button("▶", key="next_review", disabled=(page >= total_pages - 1), width='stretch'):
            st.session_state.review_page = page + 1
            st.rerun()


def render_alerts_table(df: pd.DataFrame, page: int, total: int, page_size: int):
    st.markdown('<div class="section-header">Riwayat Alert</div>',
                unsafe_allow_html=True)

    if df.empty:
        st.info("Tidak ada alert untuk rentang waktu yang dipilih.")
        return

    df = df.copy()
    df["triggered_at"]      = pd.to_datetime(df["triggered_at"]).dt.strftime("%Y-%m-%d %H:%M")
    df["review_created_at"] = pd.to_datetime(df["review_created_at"]).dt.strftime("%Y-%m-%d %H:%M")
    df["rating_avg"]        = df["rating_avg"].apply(
        lambda x: f"{float(x):.2f}" if pd.notna(x) else "—"
    )

    for _, row in df.iterrows():
        alert_label = ALERT_TYPE_LABELS.get(row["alert_type"], row["alert_type"])
        dot = f'<span class="alert-dot {row["alert_type"]}"></span>'
        comment_trunc = (row["comment"][:80] + "…") if len(row["comment"]) > 80 else row["comment"]
        is_rating = row["alert_type"] == "rating_drop"
        accent = ACCENT_PURPLE if is_rating else ACCENT_RED
        review_date = row["review_created_at"] if pd.notna(row["review_created_at"]) else row["triggered_at"]

        st.markdown(
            f"""
            <div class="review-row" style="border-left-color:{accent};">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
                    <div style="flex:1;min-width:0;">
                        <div style="font-size:0.82rem;font-weight:600;color:{TEXT_PRIMARY};">
                            {dot}{alert_label}
                            <span style="font-size:0.7rem;color:{TEXT_MUTED};margin-left:8px;">
                                {review_date}
                            </span>
                            <span style="font-size:0.65rem;color:{TEXT_MUTED};margin-left:6px;">
                                ulasan: {row["create_time"]}
                            </span>
                        </div>
                        <div style="font-size:0.72rem;font-weight:500;color:{ASUS_BLUE};margin-top:2px;">
                            {_short_product_name(row["product_name"])}
                        </div>
                        <div style="font-size:0.78rem;color:{TEXT_SECONDARY};margin-top:3px;">
                            {comment_trunc}
                        </div>
                    </div>
                    <div style="text-align:right;flex-shrink:0;">
                        <span style="font-size:0.9rem;font-weight:700;color:{accent};">
                            ⌀ {row["rating_avg"]}
                        </span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    total_pages = max(1, (total + page_size - 1) // page_size)
    info_col, prev_col, next_col = st.columns([4, 1, 1])
    with info_col:
        st.markdown(
            f'<div class="pagination-info">Halaman {page + 1} dari {total_pages} '
            f'({total} alert)</div>',
            unsafe_allow_html=True,
        )
    with prev_col:
        if st.button("◀", key="prev_alert", disabled=(page == 0), width='stretch'):
            st.session_state.alert_page = page - 1
            st.rerun()
    with next_col:
        if st.button("▶", key="next_alert", disabled=(page >= total_pages - 1), width='stretch'):
            st.session_state.alert_page = page + 1
            st.rerun()