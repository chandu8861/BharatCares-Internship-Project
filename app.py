"""EcomPulse — E-Commerce Sales, Customer Behavior & Return Risk Analytics.

Launch: ./.venv/Scripts/streamlit.exe run app.py

The UI layer is theme-adaptive (light / dark / OS auto / custom): design tokens
are resolved at runtime from the live theme (see detect_theme / palette),
all custom CSS uses theme variables with layered fallbacks, and charts use
the Streamlit Plotly template plus the theme categorical colourway.
Analytics live in analytics.py and are unchanged by every UI change here.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

import pandas as pd
import plotly.express as px
import streamlit as st

import analytics as an

LIGHT = {
    "mode": "light",
    "page": "#FFFFFF",
    "surface": "#F3F6FA",
    "text": "#1B2430",
    "muted": "#5B6B7C",
    "primary": "#1F6FEB",
    "accent": "#1F6FEB",
    "tier_high": "#C25127",
    "tier_medium": "#A86A12",
    "tier_low": "#1F6FEB",
    "tier_none": "#6B7683",
    "fact": "#1F6FEB",
    "cognition": "#6D4FCF",
    "hypothesis": "#A86A12",
    "action": "#0E8F6B",
    "bar_single": "#1F6FEB",
    "baseline": "#5B6B7C",
}
DARK = {
    "mode": "dark",
    "page": "#0F1318",
    "surface": "#171D26",
    "text": "#E8EDF4",
    "muted": "#A7B4C6",
    "primary": "#63A9FF",
    "accent": "#63A9FF",
    "tier_high": "#FF9664",
    "tier_medium": "#E7B45C",
    "tier_low": "#63A9FF",
    "tier_none": "#8A94A6",
    "fact": "#7FB2FF",
    "cognition": "#B79BFF",
    "hypothesis": "#E7B45C",
    "action": "#57C99A",
    "bar_single": "#63A9FF",
    "baseline": "#A7B4C6",
}


def detect_theme() -> str:
    """Return 'light' or 'dark' for the live theme, never crash.

    st.context.theme.type is inferred from the app background, so it tracks
    OS-auto and in-app theme switches, but it can lag a beat during a switch
    and is None outside a run context; hence the conservative fallback chain.
    """
    try:
        live = getattr(st.context, "theme", None)
        t = live.get("type", None) if live is not None else None
        if t in ("light", "dark"):
            return t
    except Exception:
        pass
    try:
        configured = st.get_option("theme.base")
        if configured in ("light", "dark"):
            return configured
    except Exception:
        pass
    return "light"


def _opt(key: str):
    try:
        return st.get_option(f"theme.{key}")
    except Exception:
        return None


def palette() -> Dict[str, str]:
    """Theme-resolved colour tokens. Recomputed every run (cheap).

    Configured theme colours win (honours custom user themes); otherwise the
    curated set for the live light/dark mode is used.
    """
    base = dict(DARK if detect_theme() == "dark" else LIGHT)
    for key, token in (("backgroundColor", "page"), ("secondaryBackgroundColor", "surface"),
                        ("textColor", "text"), ("primaryColor", "primary"),
                        ("chartCategoricalColors", None)):
        val = _opt(key)
        if val and token:
            base[token] = str(val)
    configured_cycle = _opt("chartCategoricalColors")
    if configured_cycle:
        base["bar_single"] = str(configured_cycle[0])
        base["accent"] = str(configured_cycle[0])
    base["tier"] = {"High": base["tier_high"], "Medium": base["tier_medium"],
                      "Low": base["tier_low"], "Low volume (not tiered)": base["tier_none"]}
    return base

# Module-level colour sets used by the sales, customer-ops and return-risk charts.
# Kept as fixed lists/maps so chart colour choices are stable across theme switches
# and do not depend on the live categorical palette, which can change when the user
# picks a custom Streamlit theme.
COLORS = [
    "#1F6FEB",
    "#0E8F6B",
    "#C2731A",
    "#6D4FCF",
    "#C43E4E",
    "#0E7C95",
    "#4C8C2B",
    "#B4560F",
]
TIER_COLORS = {"High": "#C25127", "Medium": "#A86A12", "Low": "#1F6FEB"}



def configure_page() -> None:
    st.set_page_config(page_title="EcomPulse", page_icon="chart_with_upwards_trend", layout="wide")


def theme_css(p: Dict[str, str]) -> None:
    """Inject the adaptive design tokens. Every background is paired with an
    explicit foreground; body copy always inherits the theme text colour, so
    the app can never drift into invisible low-contrast states, whatever the
    active Streamlit theme is."""
    tint = f"color-mix(in srgb, {p['primary']} 10%, transparent)"
    st.markdown(f"""
<style>
:root{{--app-page:{p['page']};--app-surface:{p['surface']};--app-text:{p['text']};--app-muted:{p['muted']};--app-primary:{p['primary']};}}
.block-container{{padding-top:1.3rem;max-width:1280px;}}
h1{{font-size:1.85rem;font-weight:700;margin-bottom:0.15rem;color:var(--app-text,var(--text-color,{p['text']}));}}
h2{{font-size:1.3rem;font-weight:650;margin:0.9rem 0 0.4rem;color:var(--app-text,var(--text-color,{p['text']}));}}
h3{{font-size:1.08rem;font-weight:600;color:var(--app-text,var(--text-color,{p['text']}));}}
.section-head{{margin:0.4rem 0 0.2rem;}}
.section-head h3{{margin:0;color:var(--app-text,var(--text-color,{p['text']}));}}
.section-purpose{{font-size:0.85rem;color:var(--app-muted,{p['muted']});margin:0.05rem 0 0.55rem;}}
div[data-testid="stCaptionContainer"] p{{font-size:0.83rem;color:var(--app-muted,{p['muted']});opacity:1;}}
.insight-card{{background:{tint};border:1px solid var(--app-border,var(--border-color,{p['surface']}));border-left:5px solid var(--app-primary,{p['primary']});border-radius:10px;padding:0.65rem 0.95rem;margin:0.55rem 0;max-width:100%;}}
.insight-head{{display:flex;align-items:center;gap:0.5rem;margin-bottom:0.35rem;font-weight:700;font-size:0.85rem;letter-spacing:0.04em;text-transform:uppercase;color:var(--app-text,var(--text-color,{p['text']}));}}
.insight-head .dot{{width:0.6rem;height:0.6rem;border-radius:50%;background:var(--app-primary,{p['primary']});flex-shrink:0;}}
.insight-row{{display:flex;gap:0.6rem;align-items:flex-start;padding:0.28rem 0;border-top:1px solid var(--app-border,var(--border-color,{p['surface']}));}}
.insight-row:first-of-type{{border-top:none;}}
.tag{{flex:0 0 7.6rem;font-size:0.72rem;font-weight:700;letter-spacing:0.05em;text-transform:uppercase;line-height:1.5;padding-top:0.1rem;}}
.insight-row p{{margin:0;font-size:0.86rem;line-height:1.5;color:var(--app-text,var(--text-color,{p['text']}));overflow-wrap:anywhere;}}
.row-fact .tag{{color:{p['fact']};}}
.row-cognition .tag{{color:{p['cognition']};}}
.row-hypothesis .tag{{color:{p['hypothesis']};}}
.row-action .tag{{color:{p['action']};}}
.row-fact{{border-left:3px solid {p['fact']};padding-left:0.55rem;}}
.row-cognition{{border-left:3px solid {p['cognition']};padding-left:0.55rem;}}
.row-hypothesis{{border-left:3px solid {p['hypothesis']};padding-left:0.55rem;}}
.row-action{{border-left:3px solid {p['action']};padding-left:0.55rem;}}
@media (max-width:700px){{
 .insight-row{{flex-direction:column;gap:0.1rem;}}
 .tag{{flex:none;}}
}}
</style>
""", unsafe_allow_html=True)


def inject_css() -> None:
    """Public entry point for CSS injection used by main(). Delegates to theme_css with the live palette."""
    theme_css(palette())


def prepare_any(raw: pd.DataFrame):
    missing, _ = an.validate_schema(raw)
    cleaned, log = an.clean_data(raw)
    df = an.add_derived_columns(cleaned)
    checks = an.run_quality_checks(df)
    return df, log, checks, missing


@st.cache_data(show_spinner=False)
def load_app_data():
    path = an.resolve_dataset_path()
    raw = an.load_raw(path)
    return prepare_any(raw)


def load_with_fallback():
    try:
        df, log, checks, missing = load_app_data()
        return df, log, checks, missing, None
    except Exception as exc:
        st.error(str(exc))
        up = st.file_uploader("Upload ecommerce_orders_dataset.csv to continue", type=["csv"])
        if up is not None:
            try:
                return (*prepare_any(an.load_raw(up)), None)
            except Exception as exc2:
                st.error(f"The uploaded file could not be processed: {exc2}")
        return None, None, None, None, "missing"


def _have(df: pd.DataFrame, *cols: str) -> bool:
    return bool(len(df)) and all(c in df.columns for c in cols)


def empty_state(msg: str) -> None:
    st.info(msg)


CHART_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]}


def money_axis(fig, axis: str = "y") -> None:
    getattr(fig, f"update_{axis}axes")(tickprefix="$", tickformat=",.0f")


def pct_axis(fig, axis: str = "x") -> None:
    getattr(fig, f"update_{axis}axes")(ticksuffix="%", tickformat=",.1f")


def styled(fig, height: int, pal: Dict[str, str], title: str | None = None):
    """Apply the shared chart treatment: live-theme template with explicit
    currency/percent axis formatting and readable tooltips."""
    fig.update_layout(template=None, height=height, margin=dict(l=48, r=24, t=52, b=44),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                      legend_title_text="")
    if title is not None:
        fig.update_layout(title=dict(text=title, font=dict(size=14)))
    return fig


def chart(fig, height: int = 360, title: str | None = None, pal: Dict[str, str] | None = None):
    p = pal or palette()
    styled(fig, height, p, title)
    st.plotly_chart(fig, width="stretch", theme="streamlit", config=CHART_CONFIG)


def bar_h(df, x: str, y: str, title: str, xlabel: str, pal: Dict[str, str], height: int = 360, hover: str | None = None, palette_color: str | None = None):
    fig = px.bar(df, x=x, y=y, orientation="h", title=title,
                 color_discrete_sequence=[palette_color or pal["bar_single"]])
    if hover:
        fig.update_traces(hovertemplate=hover + "<extra></extra>")
    return fig


def bar_v(df, x: str, y: str, title: str, ylabel: str, pal: Dict[str, str], height: int = 330, hover: str | None = None, palette_color: str | None = None):
    fig = px.bar(df, x=x, y=y, title=title,
                 color_discrete_sequence=[palette_color or pal["bar_single"]])
    if hover:
        fig.update_traces(hovertemplate=hover + "<extra></extra>")
    return fig


def kpi_help(kpi: Dict[str, Any]) -> str | None:
    note, delta_label = kpi.get("note") or "", kpi.get("delta_label") or ""
    extra = f" Change vs {delta_label.lower()}." if kpi.get("delta") is not None and delta_label else ""
    return (note + extra).strip() or None


def kpi_card(col, kpi: Dict[str, Any]) -> None:
    with col:
        st.metric(label=kpi["label"], value=kpi["formatted"],
                  delta=(f"{kpi['delta']:+.1f}%" if kpi.get("delta") is not None else None),
                  border=True, help=kpi_help(kpi), width="stretch")
        if kpi.get("note"):
            st.caption(kpi["note"])


def render_insight(block: Dict[str, str], warn: bool = False) -> None:
    """Compact four-row card. Text is unchanged from analytics.py; only the
    labels and presentation differ ("Possible explanation" -> "Hypothesis")."""
    if not block or not block.get("observation"):
        return
    rows = [("Observation", "row-fact", block["observation"]),
            ("Insight", "row-cognition", block["insight"]),
            ("Hypothesis", "row-hypothesis", block["explanation"]),
            ("Recommendation", "row-action", block["recommendation"])]
    body = "".join(f'<div class="insight-row {cls}"><span class="tag">{label}</span><p>{text}</p></div>' for label, cls, text in rows)
    head = "Data caveat" if warn else "Key finding"
    st.markdown(f'<div class="insight-card"><div class="insight-head"><span class="dot"></span>{head}</div>{body}</div>', unsafe_allow_html=True)


def section(title: str, purpose: str) -> None:
    st.markdown(f'<div class="section-head"><h3>{title}</h3><p class="section-purpose">{purpose}</p></div>', unsafe_allow_html=True)

def render_sidebar(df: pd.DataFrame) -> an.FilterState:
    st.sidebar.markdown('<div style="font-size:1.1rem;font-weight:700;letter-spacing:-0.01em;margin-bottom:0.15rem;">EcomPulse</div><div style="font-size:0.7rem;opacity:0.55;margin-bottom:0.6rem;">E-Commerce Sales, Customer Behavior & Return Risk Analytics</div>', unsafe_allow_html=True)
    st.sidebar.header("Filters")
    state = st.session_state.get("filters", {})
    with st.sidebar.expander("Date and catalogue", expanded=True):
        dmin, dmax = df["Order_Date"].min().date(), df["Order_Date"].max().date()
        dates = st.date_input("Order date range", value=(state.get("start", dmin), state.get("end", dmax)), min_value=dmin, max_value=dmax)
        start, end = (dates + (None, None))[:2] if isinstance(dates, (list, tuple)) else (dates, dates)
        cats = sorted(df["Product_Category"].dropna().unique().tolist()) if "Product_Category" in df.columns else []
        sel_cats = st.multiselect("Product category", cats, default=[v for v in state.get("categories", []) if v in cats], placeholder="All (no filter)", help="Leave empty to include every category.")
        sub_pool = df[df["Product_Category"].isin(sel_cats)] if sel_cats else df
        subs = sorted(sub_pool["Product_Subcategory"].dropna().unique().tolist()) if "Product_Subcategory" in df.columns else []
        sel_subs = st.multiselect("Product subcategory", subs, default=[s for s in state.get("subcategories", []) if s in subs], placeholder="All (no filter)", help="Leave empty to include every subcategory.")
    with st.sidebar.expander("Customers and fulfilment", expanded=True):
        def pick(label: str, col: str, key: str) -> List[str]:
            opts = sorted(df[col].dropna().unique().tolist()) if col in df.columns else []
            keep = [v for v in state.get(key, []) if v in opts]
            return st.multiselect(label, opts, default=keep, placeholder="All (no filter)", help="Leave empty to include every option.")
        sel_seg = pick("Customer segment", "Customer_Segment", "segments")
        sel_cty = pick("Customer country (integrity caveat)", "Country", "countries")
        sel_pay = pick("Payment method", "Payment_Method", "payments")
        sel_ship = pick("Shipping method", "Shipping_Method", "shipping_methods")
        sel_mem = pick("Membership tier", "Membership_Status", "memberships")
        sel_ret = st.radio("Return status", ["All", "Returned", "Not returned"], index=["All", "Returned", "Not returned"].index(state.get("return_status", "All")))
    if st.sidebar.button("Reset filters"):
        st.session_state.pop("filters", None)
        st.rerun()
    new_state: an.FilterState = {"start": start, "end": end, "categories": sel_cats, "subcategories": sel_subs, "segments": sel_seg, "countries": sel_cty, "payments": sel_pay, "shipping_methods": sel_ship, "memberships": sel_mem, "return_status": sel_ret}
    st.session_state["filters"] = new_state
    return new_state


def download_filtered(df: pd.DataFrame) -> None:
    st.sidebar.download_button("Download filtered data (CSV)", data=df.to_csv(index=False).encode("utf-8"), file_name="filtered_orders.csv", mime="text/csv", help="Export exactly the rows behind the current KPIs and charts.")


def footer_metrics(df: pd.DataFrame, state: an.FilterState) -> Dict[str, Any]:
    """Mini-KPIs for the footer page: period, volume, value, return and repeat signals.

    All values are computed from the filtered subset so the footer always matches
    the active filter state, including the recommendations filter.
    """
    sub = an.get_filtered_frame(df, state)
    n = len(sub)
    revenue = float(sub["Order_Amount"].sum()) if n else 0.0
    returns = int(sub["Is_Returned"].sum()) if n and "Is_Returned" in sub.columns else 0
    ret_rate = (returns / n * 100) if n else 0.0
    profit = float(pd.to_numeric(sub.get("Profit_Amount"), errors="coerce").fillna(0.0).sum()) if n else 0.0
    hv = int(sub["Is_High_Value"].sum()) if n and "Is_High_Value" in sub.columns else 0
    aov = revenue / n if n else 0.0
    return {
        "n_orders": n,
        "revenue": revenue,
        "profit": profit,
        "returns": returns,
        "ret_rate": ret_rate,
        "hv_orders": hv,
        "aov": aov,
    }


def strength_weakness_cards(df: pd.DataFrame, state: an.FilterState) -> List[Dict[str, str]]:
    """Return a small list of strength and weakness insight cards for the filtered state.

    Each card is a 4-row insight block (fact / reading / hypothesis / action) so the
    strengths and weaknesses page reuses the same visual language as the overview.
    """
    sub = an.get_filtered_frame(df, state)
    n = len(sub)
    cards: List[Dict[str, str]] = []
    if n == 0:
        return cards

    revenue = float(sub["Order_Amount"].sum())
    ret_rate = float(sub["Is_Returned"].mean() * 100) if n else 0.0
    base_ret = float(df["Is_Returned"].mean() * 100)

    # Strength 1: revenue scale
    cards.append({
        "tag": "Strength",
        "fact": f"${revenue:,.0f} in filtered revenue across {n:,} orders.",
        "reading": "The filtered segment carries meaningful scale; even narrow slices (single category or segment) can represent thousands of dollars.",
        "hypothesis": "Revenue concentration reflects genuine demand, not just more orders; the same slice can look strong on volume and weak on value if AOV is low.",
        "action": "Use this slice as a baseline for campaign targeting and stock planning; pair the scale view with AOV and return rate before committing budget.",
    })

    # Strength 2 / Weakness: return rate relative to baseline
    if ret_rate < base_ret - 0.5:
        cards.append({
            "tag": "Strength",
            "fact": f"Return rate {ret_rate:.1f}% is below the {base_ret:.1f}% all-order baseline.",
            "reading": "This filtered group returns less often than the overall book, which is a positive quality signal.",
            "hypothesis": "Lower returns may be associated with better product fit, clearer expectations, or more reliable fulfilment for this slice.",
            "action": "Protect the conditions behind the lower return rate: keep the same product mix, shipping options and communication style where possible.",
        })
    elif ret_rate > base_ret + 0.5:
        cards.append({
            "tag": "Weakness",
            "fact": f"Return rate {ret_rate:.1f}% is above the {base_ret:.1f}% all-order baseline.",
            "reading": "This filtered group returns more often than the overall book, which is a risk flag worth understanding.",
            "hypothesis": "Higher returns may be associated with product fit, description accuracy, delivery experience or price sensitivity for this slice.",
            "action": "Review the top-return subcategories and delivery bands inside this slice; small changes to expectations or fulfilment may reduce avoidable returns.",
        })
    else:
        cards.append({
            "tag": "Neutral",
            "fact": f"Return rate {ret_rate:.1f}% is close to the {base_ret:.1f}% all-order baseline.",
            "reading": "This filtered group returns at roughly the same rate as the overall book.",
            "hypothesis": "No obvious return advantage or disadvantage stands out for this slice in the current data.",
            "action": "Treat return performance as average; watch for shifts when the filter changes or new data arrives.",
        })

    # Strength / Weakness: high-value concentration
    if "Is_High_Value" in sub.columns:
        hv_share = float(sub["Is_High_Value"].mean() * 100)
        if hv_share >= 30:
            cards.append({
                "tag": "Strength",
                "fact": f"{hv_share:.0f}% of filtered orders are top-quartile by value.",
                "reading": "A high share of orders sit in the upper value band, which is attractive for revenue and profit per order.",
                "hypothesis": "This may reflect a higher average order value, larger baskets, premium categories or stronger purchasing power in this slice.",
                "action": "Prioritise retention and upsell for this group; ensure premium items stay in stock and shipping promises are met.",
            })
        elif hv_share <= 18:
            cards.append({
                "tag": "Weakness",
                "fact": f"Only {hv_share:.0f}% of filtered orders are top-quartile by value.",
                "reading": "A low share of orders sit in the upper value band, which limits revenue per order.",
                "hypothesis": "This may reflect smaller baskets, lower unit prices, discount-driven purchases or a price-sensitive segment.",
                "action": "Test whether bundling, cross-sell or targeted offers can lift basket size without eroding margin.",
            })

    return cards


def render_overview(df: pd.DataFrame, kpis: Dict[str, an.KPI], pal: Dict[str, str]) -> None:
    section("Executive Overview", "Headline performance for the filtered orders: value, volume, risk and the stories behind them.")
    row = st.columns(4)
    for key, i in [("revenue", 0), ("orders", 1), ("aov", 2), ("profit", 3)]:
        kpi_card(row[i], kpis[key])
    row = st.columns(4)
    for key, i in [("return_rate", 0), ("rev_risk", 1), ("hv_share", 2), ("repeat", 3)]:
        kpi_card(row[i], kpis[key])
    c1, c2 = st.columns([1.5, 1])
    with c1:
        trend = an.revenue_trend(df, "M")
        if trend.empty:
            empty_state("No monthly trend available for the current filters.")
        else:
            fig = px.line(trend, x="period", y="revenue", labels={"period": "Month", "revenue": "Revenue ($)"}, color_discrete_sequence=[pal["accent"]])
            fig.update_traces(mode="lines+markers", name="Revenue", hovertemplate="%{x|%b %Y}: $%{y:,.0f}<extra></extra>", yaxis="y")
            fig.add_scatter(x=trend["period"], y=trend["orders"], mode="lines+markers", name="Orders", yaxis="y2", marker=dict(color=pal["baseline"]), line=dict(color=pal["baseline"]), hovertemplate="%{x|%b %Y}: %{y:,.0f} orders<extra></extra>")
            fig.update_layout(yaxis2=dict(overlaying="y", side="right", title="Orders"))
            money_axis(fig, "y")
            chart(fig, 380, title="Monthly revenue and order volume", pal=pal)
    with c2:
        cat = an.aggregate_by(df, "Product_Category") if "Product_Category" in df.columns else pd.DataFrame()
        if cat.empty:
            empty_state("Category mix unavailable.")
        else:
            fig = px.pie(cat.sort_values("revenue", ascending=False), names="label", values="revenue", title="Revenue share by category", hole=0.45)
            fig.update_traces(textposition="inside", textinfo="percent", hovertemplate="%{label}: $%{value:,.0f} (%{percent})<extra></extra>")
            chart(fig, 380, title="", pal=pal)
    sub = an.aggregate_by(df, "Product_Subcategory") if "Product_Subcategory" in df.columns else pd.DataFrame()
    if not sub.empty:
        fig = bar_h(sub.head(10).sort_values("revenue"), "revenue", "label", "Top 10 subcategories by revenue", "Revenue ($)", pal, 360, hover="$%{x:,.0f}")
        chart(fig, 360, title="", pal=pal)
    section("Business summary", "Computed from the filtered data; each card separates fact, reading, hypothesis and next action.")
    if _have(df, "Product_Category") and kpis["revenue"]["value"]:
        render_insight(an.insight_revenue_concentration(an.aggregate_by(df, "Product_Category"), float(kpis["revenue"]["value"])))
    if _have(df, "Order_Date"):
        yearly = an.aggregate_by(df, "Year") if "Year" in df.columns else pd.DataFrame()
        if not yearly.empty:
            render_insight(an.insight_trend(yearly.rename(columns={"orders": "orders", "revenue": "rev", "aov": "aov"}), an.revenue_trend(df, "M")))
    if _have(df, "Is_High_Value"):
        hv_rev = float(df.loc[df["Is_High_Value"], "Order_Amount"].sum())
        render_insight(an.insight_value_concentration(float(kpis["hv_share"]["value"]), hv_rev / float(kpis["revenue"]["value"]) * 100 if kpis["revenue"]["value"] else 0.0))

def render_sales(df: pd.DataFrame, pal: Dict[str, str]) -> None:
    section("Sales and Product Analysis", "How revenue moves over time and where value and margin concentrate across the catalogue.")
    freq = st.radio("Trend granularity", ["Daily", "Weekly", "Monthly"], horizontal=True, index=2)
    trend = an.revenue_trend(df, {"Daily": "D", "Weekly": "W", "Monthly": "M"}[freq])
    if trend.empty:
        empty_state("No trend available for the current filters.")
    else:
        fig = bar_v(trend, "period", "revenue", f"Revenue over time ({freq.lower()})", "Revenue ($)", pal, 340, hover="$%{y:,.0f}")
        chart(fig, 340, title="", pal=pal)
    piv = an.monthly_by_year(df)
    if not piv.empty:
        fig = px.line(piv.reset_index(), x="m", y=piv.columns.tolist())
        fig.update_traces(mode="lines+markers", hovertemplate="Month %{x}: $%{y:,.0f}<extra></extra>")
        chart(fig, 340, title="Monthly revenue by year (seasonality check)", pal=pal)
        money_axis(fig, "y")
        chart(fig, 340)
    cat = an.aggregate_by(df, "Product_Category") if "Product_Category" in df.columns else pd.DataFrame()
    if not cat.empty:
        c1, c2 = st.columns(2)
        with c1:
            fig = bar_h(cat.sort_values("revenue"), "revenue", "label", "Revenue by category", "Revenue ($)", pal, 380, hover="$%{x:,.0f}")
            chart(fig, 380, title="", pal=pal)
        with c2:
            fig = px.scatter(cat, x="orders", y="aov", size="revenue", color="label", hover_name="label", hover_data={"orders": ":,", "aov": ":$,.0f", "revenue": ":$,.0f"})
            chart(fig, 380, title="Volume vs value by category (bubble = revenue)", pal=pal)
        st.dataframe(cat.rename(columns={"label": "Category", "orders": "Orders", "revenue": "Revenue", "aov": "AOV", "profit": "Profit", "margin": "Margin %", "return_rate": "Return %", "revenue_share": "Revenue share %", "orders_share": "Orders share %"}).round(2), use_container_width=True, hide_index=True)
    sub = an.aggregate_by(df, "Product_Subcategory").head(12) if "Product_Subcategory" in df.columns else pd.DataFrame()
    if not sub.empty:
        fig = px.bar(sub.sort_values("revenue"), x="revenue", y="label", orientation="h", title="Top subcategories by revenue", labels={"revenue": "Revenue ($)", "label": ""}, color_discrete_sequence=[COLORS[2]])
        chart(fig, 400)
    brand = an.aggregate_by(df, "Brand") if "Brand" in df.columns else pd.DataFrame()
    if not brand.empty:
        fig = px.bar(brand.sort_values("revenue"), x="revenue", y="label", orientation="h", title="Revenue by brand", labels={"revenue": "Revenue ($)", "label": ""}, color_discrete_sequence=[COLORS[3]])
        chart(fig, 360)
    par = an.pareto_table(df, "Product_Category")
    if not par.empty:
        fig = px.bar(par, x="label", y="revenue_share", title="Revenue concentration (category share of revenue)", labels={"revenue_share": "Share of revenue (%)", "label": "Category"}, color_discrete_sequence=[COLORS[0]])
        fig.add_scatter(x=par["label"], y=par["cum_revenue_share"], mode="lines+markers", name="Cumulative %", yaxis="y2", line=dict(color=COLORS[3]))
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", title="Cumulative %", range=[0, 105]))
        chart(fig, 360)
    by_bucket, by_coupon = an.discount_analysis(df)
    if not by_bucket.empty:
        c1, c2 = st.columns(2)
        with c1:
            fig = px.bar(by_bucket, x="label", y="aov", labels={"aov": "AOV ($)", "label": "Discount"}, color_discrete_sequence=[COLORS[1]])
            chart(fig, 330)
        with c2:
            fig = px.bar(by_bucket, x="label", y="avg_quantity")
            chart(fig, 330)
    if not by_coupon.empty:
        st.dataframe(by_coupon.rename(columns={"label": "Coupon used", "orders": "Orders", "aov": "AOV", "avg_quantity": "Mean quantity", "return_rate": "Return %"}).round(2), use_container_width=True, hide_index=True)
    if not by_bucket.empty:
        render_insight(an.insight_discount_effectiveness(by_bucket, by_coupon, float(df["Discount_Amount"].sum()) if "Discount_Amount" in df.columns else 0.0, float(df["Order_Amount"].sum())))
    if "Day_Of_Week" in df.columns:
        wd = an.aggregate_by(df, "Day_Of_Week")
        order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        wd["label"] = pd.Categorical(wd["label"], categories=order, ordered=True)
        wd = wd.sort_values("label")
        fig = px.bar(wd, x="label", y="revenue", labels={"revenue": "Revenue ($)", "label": ""}, color_discrete_sequence=[COLORS[5]])
        chart(fig, 320)
    if "Season" in df.columns:
        seas = an.aggregate_by(df, "Season")
        fig = px.bar(seas, x="label", y="revenue", labels={"revenue": "Revenue ($)", "label": ""}, color_discrete_sequence=[COLORS[6]])
        chart(fig, 320)

def render_customer_ops(df: pd.DataFrame, pal: Dict[str, str]) -> None:
    section("Customer and Operations", "Basket mix by segment and tier, delivery reliability, and how orders arrive and are paid for.")
    seg = an.aggregate_by(df, "Customer_Segment") if "Customer_Segment" in df.columns else pd.DataFrame()
    if not seg.empty:
        c1, c2 = st.columns(2)
        with c1:
            fig = px.bar(seg.sort_values("revenue"), x="revenue", y="label", orientation="h", title="Revenue by customer segment (order-level attribute)", labels={"revenue": "Revenue ($)", "label": ""}, color_discrete_sequence=[COLORS[0]])
            chart(fig, 340)
        with c2:
            fig = px.bar(seg.sort_values("aov"), x="aov", y="label", orientation="h", title="AOV by customer segment", labels={"aov": "AOV ($)", "label": ""}, color_discrete_sequence=[COLORS[1]])
            chart(fig, 340)
        st.caption("Segments are recorded per order and change between orders of the same customer in this dataset; read these as basket mixes, not as tracked customer cohorts.")
    mem = an.aggregate_by(df, "Membership_Status") if "Membership_Status" in df.columns else pd.DataFrame()
    if not mem.empty and "Customer_Lifetime_Value" in df.columns:
        clv = df.groupby("Membership_Status")["Customer_Lifetime_Value"].mean().reset_index().rename(columns={"Membership_Status": "label", "Customer_Lifetime_Value": "avg_clv"})
        mem = mem.merge(clv, on="label", how="left")
        fig = px.scatter(mem, x="aov", y="avg_clv", size="orders", color="label", title="AOV vs recorded CLV by membership tier (bubble = orders)", labels={"aov": "AOV ($)", "avg_clv": "Mean recorded CLV ($)", "label": "Tier"}, color_discrete_sequence=COLORS)
        chart(fig, 360)
    dist, summary = an.frequency_analysis(df)
    if not dist.empty:
        c1, c2 = st.columns(2)
        with c1:
            fig = px.bar(dist, x="orders_per_customer", y="customers")
            chart(fig, 330)
        with c2:
            fig = px.bar(dist, x="orders_per_customer", y="band_revenue_share", labels={"orders_per_customer": "Orders per customer ID", "band_revenue_share": "Revenue share (%)"}, color_discrete_sequence=[COLORS[3]])
            chart(fig, 330)
        render_insight(an.insight_customer_frequency(summary), warn=True)
    deliv, dinfo = an.delivery_analysis(df)
    if not deliv.empty:
        section("Delivery performance", "Promised speed versus actual delivery days across shipping methods.")
        fig = px.bar(deliv.sort_values("avg_days", ascending=False), x="avg_days", y="label", orientation="h", title="Mean delivery days by shipping method", labels={"avg_days": "Mean days", "label": ""}, color_discrete_sequence=[COLORS[4]])
        chart(fig, 320)
        st.dataframe(deliv.rename(columns={"label": "Method", "orders": "Orders", "avg_days": "Mean days", "median_days": "Median days", "p90_days": "P90 days", "max_days": "Max days", "return_rate": "Return %"}).round(2), use_container_width=True, hide_index=True)
        render_insight(an.insight_logistics_quality(dinfo), warn=True)
    pay = an.aggregate_by(df, "Payment_Method") if "Payment_Method" in df.columns else pd.DataFrame()
    if not pay.empty:
        fig = px.bar(pay.sort_values("orders"), x="orders", y="label", orientation="h", title="Orders by payment method", labels={"orders": "Orders", "label": ""}, color_discrete_sequence=[COLORS[5]])
        chart(fig, 320)
    dev = an.aggregate_by(df, "Device_Type") if "Device_Type" in df.columns else pd.DataFrame()
    traf = an.aggregate_by(df, "Traffic_Source") if "Traffic_Source" in df.columns else pd.DataFrame()
    if not dev.empty or not traf.empty:
        c1, c2 = st.columns(2)
        with c1:
            if not dev.empty:
                fig = px.pie(dev, names="label", values="revenue", hole=0.45)
                chart(fig, 330)
        with c2:
            if not traf.empty:
                t = traf.sort_values("aov")
                fig = px.bar(t, x="aov", y="label", orientation="h", labels={"aov": "AOV ($)", "label": ""}, color_discrete_sequence=[COLORS[6]])
                chart(fig, 330)
    cty = an.aggregate_by(df, "Country") if "Country" in df.columns else pd.DataFrame()
    if not cty.empty:
        fig = px.bar(cty.sort_values("revenue"), x="revenue", y="label", orientation="h", title="Revenue by country (marginal split; cities are not mapped)", labels={"revenue": "Revenue ($)", "label": ""}, color_discrete_sequence=[COLORS[1]])
        chart(fig, 340)

def render_return_risk(df: pd.DataFrame, kpis: Dict[str, an.KPI], pal: Dict[str, str]) -> None:
    section("Return Risk", "Which segments of observed behaviour return most, and what closing the gap would recover.")
    if not _have(df, "Is_Returned"):
        empty_state("Return analysis needs the Returned field, which is unavailable.")
        return
    base = float(df["Is_Returned"].mean() * 100)
    st.caption(f"Baseline return rate in the filtered data: {base:.2f}%. Extra revenue at risk: {kpis['rev_risk']['formatted']} ({kpis['rev_risk']['note']}). Tiers below are descriptive segments of observed behaviour, not model predictions.")
    cat = an.return_rate_table(df, "Product_Category") if "Product_Category" in df.columns else pd.DataFrame()
    if not cat.empty:
        fig = px.bar(cat.sort_values("return_rate"), x="return_rate", y="label", orientation="h", title="Return rate by category", labels={"return_rate": "Return rate (%)", "label": ""}, color_discrete_sequence=[COLORS[3]])
        fig.add_vline(x=base, line_dash="dash", line_color=COLORS[0], annotation_text=f"baseline {base:.2f}%", annotation_position="bottom right")
        chart(fig, 340)
    tier_dim = "Product_Category"
    sub_tab = an.return_rate_table(df, "Product_Subcategory") if "Product_Subcategory" in df.columns else pd.DataFrame()
    view = st.radio("Risk tier view", ["Subcategory", "Category"], horizontal=True, index=0)
    table = sub_tab if view == "Subcategory" and not sub_tab.empty else cat
    tiered, tiers = an.build_risk_tiers(table, base)
    if not tiered.empty:
        show = tiered[["label", "tier", "orders", "return_rate", "lift_vs_baseline", "revenue", "revenue_at_risk", "profit_at_risk"]].rename(columns={"label": view, "tier": "Risk tier", "orders": "Orders", "return_rate": "Return %", "lift_vs_baseline": "Lift vs baseline", "revenue": "Revenue", "revenue_at_risk": "Revenue at risk", "profit_at_risk": "Profit at risk"})
        st.dataframe(show.style.format({"Return %": "{:.2f}", "Lift vs baseline": "{:.2f}", "Revenue": "${:,.0f}", "Revenue at risk": "${:,.0f}", "Profit at risk": "${:,.0f}"}), use_container_width=True, hide_index=True)
        st.caption(tiers["rationale"])
        fig = px.bar(tiered[tiered["tier"].isin(["High", "Medium", "Low"])].sort_values("return_rate"), x="return_rate", y="label", color="tier", orientation="h", title=f"Return-rate tiers ({view.lower()} level)", labels={"return_rate": "Return rate (%)", "label": "", "tier": "Tier"}, color_discrete_map=TIER_COLORS)
        chart(fig, 380)
    opp = an.fashion_opportunity(df, base)
    render_insight(an.insight_return_risk(tiered if not tiered.empty else pd.DataFrame(), base, opp))
    section("Driver check", "Return rates across operational dimensions; flat means no driver there.")
    scan = an.return_driver_scan(df)
    if not scan.empty:
        st.dataframe(scan.rename(columns={"dimension": "Dimension", "categories": "Levels", "min_rate": "Min %", "max_rate": "Max %", "spread_pp": "Spread (pp)", "verdict": "Verdict"}).round(2), use_container_width=True, hide_index=True)
        st.caption("Only the product dimensions are marked notable. Post-outcome fields (rating, order status) are excluded on purpose: they describe what happened after the return decision, they do not predict it.")
    for label, col in [("Delivery band", "Delivery_Bucket"), ("Discount band", "Discount_Bucket"), ("Customer segment", "Customer_Segment"), ("Payment method", "Payment_Method")]:
        tab = an.return_rate_table(df, col) if col in df.columns else pd.DataFrame()
        if not tab.empty:
            fig = px.bar(tab.sort_values("return_rate"), x="return_rate", y="label", orientation="h", title=f"Return rate by {label.lower()}", labels={"return_rate": "Return rate (%)", "label": ""}, color_discrete_sequence=[COLORS[5]])
            fig.add_vline(x=base, line_dash="dash", line_color=COLORS[0])
            chart(fig, 300)
    with st.expander("Why no prediction model? Rejected experiment and evidence", expanded=False):
        ev = an.ml_rejection_evidence()
        st.markdown(f"**{ev['question']}**")
        st.markdown(f"**Method.** {ev['method']}")
        st.markdown(f"**Features.** {ev['feature_set']}")
        m = ev["metrics"]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Base rate", f"{m['base_rate']*100:.2f}%")
        c2.metric("AUC", f"{m['auc']:.4f}")
        c3.metric("Accuracy", f"{m['accuracy']:.4f}")
        c4.metric("Precision", f"{m['precision']:.3f}")
        c5.metric("Recall", f"{m['recall']:.3f}")
        st.markdown(f"**Leakage check.** {ev['leakage_demo']}")
        st.markdown(f"**Verdict.** {ev['verdict']}")

def render_notes(df: pd.DataFrame, log: pd.DataFrame, checks, missing: List[str]) -> None:
    section("Data and Method Notes", "What was checked, what the data cannot support, and how each field should be read.")
    c1, c2, c3 = st.columns(3)
    c1.metric("Records", f"{len(df):,}")
    c2.metric("Columns", f"{df.shape[1]}")
    c3.metric("Date range", f"{df['Order_Date'].min().date()} to {df['Order_Date'].max().date()}" if "Order_Date" in df.columns else "n/a")
    if missing:
        st.warning("Missing expected columns (affected charts are skipped, the rest of the app still works): " + ", ".join(missing))
    section("Cleaning log", "Every transformation the loader applied, in order.")
    st.dataframe(log, use_container_width=True, hide_index=True)
    section("Quality checks", "Independent checks on the prepared data; review anything that is not a pass.")
    ctab = pd.DataFrame(checks)
    icon = {"ok": "pass", "warn": "review", "fail": "fail"}
    ctab["status"] = ctab["status"].map(icon).fillna(ctab["status"])
    st.dataframe(ctab.rename(columns={"check": "Check", "result": "Result", "status": "Status", "detail": "Detail"}), use_container_width=True, hide_index=True)
    section("Field integrity caveats", "Read before drawing conclusions: each row states the limitation and its analytical impact.")
    st.markdown("- **Customer IDs are not a stable master.** Age, gender, segment, country, city, membership and lifetime value change between orders of the same ID, so segment and loyalty views are order-level mixes, not tracked cohorts."
                "\n- **Product IDs are not a product master.** Every ID maps to several categories, subcategories, brands and prices, so performance is analysed at category, subcategory and brand level only."
                "\n- **Country and City are independently assigned** (all combinations appear, e.g. Germany / Dubai). Country is shown as a marginal split; City is not mapped."
                "\n- **Returned equals Order_Status = Returned** exactly. They are one outcome, not two signals."
                "\n- **Review_Rating is a post-delivery outcome** (sharply lower for returned orders). It is displayed for context only and never used as a driver or predictor."
                "\n- **High_Value_Order is a top-quartile label of Order_Amount** (threshold about $388), a classificatory convenience rather than a behaviour."
                "\n- **Season and Holiday_Season are calendar functions** of the month. Delivery_Days only loosely follows Shipping_Method. Order_Status is unrelated to delivery speed."
                "\n- **Dates run past the current date** (coverage to 2026-12-31): synthetic complete-period data; no as-of truncation is needed.")
    section("Derived fields", "Cleaning adds new columns and never overwrites raw values.")
    st.caption("Cleaning adds new columns and never overwrites raw values. Backfill of Discount_Amount and Profit_Amount happens only when they are missing, using the verified subtotal formulas, and is recorded in the cleaning log.")


def render_footer(df: pd.DataFrame, state: an.FilterState) -> None:
    """Compact closing summary: filtered snapshot, active filters and credits.

    Kept to one screen so it reads as a footer, not a second dashboard. All
    numbers come from get_filtered_frame so the footer tracks the live filters,
    including any recommendation-driven selection.
    """
    section("Session footer", "Filtered snapshot, active filters, methodology pointer and credits.")
    m = footer_metrics(df, state)
    c1, c2, c3, c4 = st.columns(4)
    kpi_card(c1, {"label": "Orders in view", "value": f"{m['n_orders']:,}", "formatted": f"{m['n_orders']:,} orders", "delta": None, "delta_label": "", "note": f"{pd.Timestamp(state['start']).date()} to {pd.Timestamp(state['end']).date()}"})
    kpi_card(c2, {"label": "Revenue in view", "value": m["revenue"], "formatted": f"${m['revenue']:,.0f}", "delta": None, "delta_label": "", "note": "Filtered total"})
    kpi_card(c3, {"label": "Return rate", "value": m["ret_rate"], "formatted": f"{m['ret_rate']:.2f}%", "delta": None, "delta_label": "", "note": f"{m['returns']:,} returned orders"})
    kpi_card(c4, {"label": "Avg order value", "value": m["aov"], "formatted": f"${m['aov']:,.2f}", "delta": None, "delta_label": "", "note": "Revenue / orders"})
    section("Active filters", "Non-default filter values behind the numbers above.")
    parts: List[str] = []
    if state.get("categories"):
        parts.append(f"Categories: {', '.join(state['categories'])}")
    if state.get("segments"):
        parts.append(f"Segments: {', '.join(state['segments'])}")
    if state.get("countries"):
        parts.append(f"Countries: {', '.join(state['countries'])}")
    if state.get("payments"):
        parts.append(f"Payments: {', '.join(state['payments'])}")
    if state.get("shipping_methods"):
        parts.append(f"Shipping: {', '.join(state['shipping_methods'])}")
    if state.get("memberships"):
        parts.append(f"Memberships: {', '.join(state['memberships'])}")
    if state.get("return_status") != "All":
        parts.append(f"Returns: {state['return_status']}")
    if state.get("de_selected_categories"):
        parts.append(f"Excluded categories: {', '.join(state['de_selected_categories'])}")
    st.caption("\n".join(parts) if parts else "No active filters; showing all orders in range.")
    section("Methodology", "Where each part of the dashboard gets its numbers.")
    st.caption("- **KPIs and aggregations:** analytics.py, computed from the filtered data at runtime.\n"
               "- **Insights and recommendations:** analytics.py insight blocks and the recommendation builder in app.py.\n"
               "- **Return-risk tiers:** analytics.py return_rate_table + build_risk_tiers.\n"
               "- **ML panel:** a rejected logistic-regression experiment, documented on the Return Risk tab with evidence.\n"
               "- **Cleaning:** analytics.py clean_data + add_derived_columns; never overwrites raw values.")
    section("Credits", "Product and data note.")
    st.caption("**EcomPulse** &mdash; E-Commerce Sales, Customer Behavior & Return Risk Analytics.\n"
               "Dataset: ecommerce_orders_dataset.csv (30,000 orders, 2023-2026). Insights describe association, not proven causation.")


def render_strengths_weaknesses(df: pd.DataFrame, state: an.FilterState) -> None:
    """Strengths and weaknesses of the currently filtered segment.

    Reuses the insight-card visual language so strengths/weaknesses read the same
    way as the overview blocks: fact, reading, hypothesis, action.
    """
    section("Strengths and weaknesses", "What the current filter slice does well and where it is exposed, with hedged interpretation.")
    cards = strength_weakness_cards(df, state)
    if not cards:
        empty_state("No orders match the current filters, so no strengths or weaknesses can be read.")
        return
    for card in cards:
        tag = card["tag"]
        render_insight({"observation": card["fact"], "insight": card["reading"], "explanation": card["hypothesis"], "recommendation": card["action"]}, warn=(tag == "Weakness"))

def main() -> None:
    configure_page()
    inject_css()
    st.title("E-Commerce Sales, Customer Behavior & Return Risk Analytics")
    st.markdown('<div style="font-size:0.78rem;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:var(--app-muted,var(--muted-color,#5B6B7C));margin-top:-0.2rem;margin-bottom:0.5rem;">EcomPulse &middot; Analytics Dashboard</div>', unsafe_allow_html=True)
    st.caption("Order, revenue, customer-mix, operations and return-risk evidence from 30,000 orders (2023-2026). Insights are computed from the filtered data; recommendations use hedged language because the data establish association, not causation.")
    df, log, checks, missing, err = load_with_fallback()
    if df is None or err:
        return
    state = render_sidebar(df)
    sub = an.get_filtered_frame(df, state)
    active = [f"{k}={v}" for k, v in {"de_selected_categories": state.get("de_selected_categories"), "categories": state["categories"], "segments": state["segments"], "countries": state["countries"], "payments": state["payments"], "shipping": state["shipping_methods"], "memberships": state["memberships"], "returns": state["return_status"]}.items() if v and v != "All"]
    st.caption(f"Analysing {len(sub):,} of {len(df):,} orders ({pd.Timestamp(state['start']).date()} to {pd.Timestamp(state['end']).date()})" + (" | " + "; ".join(active[:6]) if active else ""))
    download_filtered(sub)
    if not len(sub):
        empty_state("No orders match the current filters. Widen the date range or re-select filter values.")
        return
    kpis = an.compute_kpis(sub)
    pal = palette()
    tabs = st.tabs(["Executive Overview", "Sales and Product", "Customer and Operations", "Return Risk", "Strengths and Weaknesses", "Footer"])
    with tabs[0]:
        render_overview(sub, kpis, pal)
    with tabs[1]:
        render_sales(sub, pal)
    with tabs[2]:
        render_customer_ops(sub, pal)
    with tabs[3]:
        render_return_risk(sub, kpis, pal)
    with tabs[4]:
        render_strengths_weaknesses(df, state)
    with tabs[5]:
        render_footer(df, state)


if __name__ == "__main__":
    main()
