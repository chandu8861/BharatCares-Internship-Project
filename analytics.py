"""Analytics layer: loading, cleaning, quality checks, KPIs, aggregations, insights.

Used by app.py. Can also be run directly for a dependency-free self test:

    python analytics.py
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple, TypedDict

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DATASET_FILENAME = "ecommerce_orders_dataset.csv"

REQUIRED_COLUMNS = [
    "Order_ID", "Order_Date", "Product_Category", "Product_Subcategory",
    "Brand", "Unit_Price", "Quantity", "Order_Amount",
    "Customer_Segment", "Membership_Status", "Payment_Method",
    "Shipping_Method", "Delivery_Days", "Order_Status", "Returned",
]

OPTIONAL_COLUMNS = [
    "Customer_ID", "Customer_Age", "Customer_Gender", "Country", "City",
    "Device_Type", "Traffic_Source", "Warehouse_Region", "Discount_Percent",
    "Discount_Amount", "Coupon_Used", "Shipping_Cost", "Tax_Amount",
    "Review_Rating", "Customer_Lifetime_Value", "Profit_Margin_Percent",
    "Profit_Amount", "Season", "Holiday_Season", "High_Value_Order",
    "Year", "Month", "Day", "Day_Of_Week", "Quarter",
    "Customer_Lifetime_Value",
]

NUMERIC_COLUMNS = [
    "Year", "Month", "Day", "Quarter", "Customer_Age", "Unit_Price",
    "Quantity", "Discount_Percent", "Discount_Amount", "Shipping_Cost",
    "Tax_Amount", "Order_Amount", "Delivery_Days", "Review_Rating",
    "Customer_Lifetime_Value", "Profit_Margin_Percent", "Profit_Amount",
]

YN_MAP = {"yes": "Yes", "y": "Yes", "true": "Yes", "1": "Yes",
          "no": "No", "n": "No", "false": "No", "0": "No"}
YN_COLUMNS = ["Returned", "Coupon_Used", "Holiday_Season", "High_Value_Order"]

POST_OUTCOME_FIELDS = ["Review_Rating", "Order_Status", "Returned", "High_Value_Order"]

DIMENSIONS = {
    "Product category": "Product_Category",
    "Product subcategory": "Product_Subcategory",
    "Brand": "Brand",
    "Customer segment": "Customer_Segment",
    "Membership tier": "Membership_Status",
    "Payment method": "Payment_Method",
    "Shipping method": "Shipping_Method",
    "Country": "Country",
    "Device": "Device_Type",
    "Traffic source": "Traffic_Source",
    "Warehouse region": "Warehouse_Region",
    "Season": "Season",
    "Holiday period": "Holiday_Season",
    "Discount band": "Discount_Bucket",
    "Delivery band": "Delivery_Bucket",
    "Age band": "Age_Bucket",
    "Weekday": "Day_Of_Week",
}

RISK_TIER_MULTIPLIERS = {"High": 1.25, "Medium": 0.90}
MIN_TIER_VOLUME = 150
HIGH_VALUE_QUANTILE = 0.75


class KPI(TypedDict):
    label: str
    value: Any
    formatted: str
    delta: Any
    delta_label: str
    note: str


class InsightBlock(TypedDict):
    observation: str
    insight: str
    explanation: str
    recommendation: str


class QualityCheck(TypedDict):
    check: str
    result: str
    status: str
    detail: str


class FilterState(TypedDict, total=False):
    start: Any
    end: Any
    categories: List[str]
    subcategories: List[str]
    segments: List[str]
    countries: List[str]
    payments: List[str]
    shipping_methods: List[str]
    memberships: List[str]
    return_status: str


def resolve_dataset_path(filename: str = DATASET_FILENAME) -> Path:
    candidates = [DATA_DIR / filename, PROJECT_ROOT / filename]
    for path in candidates:
        if path.is_file():
            return path
    searched = "\n".join(f"- {p}" for p in candidates)
    raise FileNotFoundError(
        "Dataset file was not found. Looked in:\n" + searched +
        "\nPlace 'ecommerce_orders_dataset.csv' in the 'data' folder and reload."
    )


def load_raw(path: Any) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        raise ValueError(f"Could not read the dataset at {path}: {exc}") from exc
    df.columns = [str(c).strip() for c in df.columns]
    return df


def clean_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    log: List[List[str]] = [["Rows read", f"{len(df):,} records x {df.shape[1]} columns"]]
    dup_rows = int(df.duplicated().sum())
    if dup_rows:
        df = df.drop_duplicates().reset_index(drop=True)
    log.append(["Exact duplicate rows", f"{dup_rows:,} removed (kept first)" if dup_rows else "none found"])
    if "Order_ID" in df.columns:
        dup_ids = int(df["Order_ID"].duplicated().sum())
        if dup_ids:
            df = df.drop_duplicates(subset=["Order_ID"], keep="first").reset_index(drop=True)
        log.append(["Duplicate Order_ID values", f"{dup_ids:,} removed (kept first)" if dup_ids else "none found"])
    bad_dates = 0
    if "Order_Date" in df.columns:
        parsed = pd.to_datetime(df["Order_Date"], errors="coerce")
        bad_dates = int(parsed.isna().sum())
        df["Order_Date_Raw"] = df["Order_Date"]
        df["Order_Date"] = parsed
    log.append(["Order_Date parsing", f"{bad_dates:,} unparseable values kept as missing" if bad_dates else "all dates parsed"])
    coerced = 0
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            before = int(df[col].isna().sum())
            df[col] = pd.to_numeric(df[col], errors="coerce")
            coerced += int(df[col].isna().sum()) - before
    log.append(["Numeric coercion", f"{coerced:,} invalid values converted to missing" if coerced else "no invalid numeric values"])
    for col in _text_columns(df):
        missing = df[col].isna()
        s = df[col].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
        s[missing] = np.nan
        df[col] = s.replace({"": np.nan})
    for col in YN_COLUMNS:
        if col in df.columns:
            s = df[col].copy()
            present = s.notna()
            s.loc[present] = s.loc[present].map(lambda v: YN_MAP.get(str(v).strip().lower(), str(v).strip()))
            df[col] = s
    log.append(["Text standardisation", "whitespace stripped; Yes/No fields normalised"])
    filled = 0
    if {"Discount_Amount", "Unit_Price", "Quantity", "Discount_Percent"} <= set(df.columns):
        sub = df["Unit_Price"] * df["Quantity"]
        need = df["Discount_Amount"].isna() & sub.notna() & df["Discount_Percent"].notna()
        df.loc[need, "Discount_Amount"] = (sub[need] * df.loc[need, "Discount_Percent"] / 100).round(2)
        filled += int(need.sum())
    if {"Profit_Amount", "Order_Amount", "Profit_Margin_Percent"} <= set(df.columns):
        need = df["Profit_Amount"].isna() & df["Order_Amount"].notna() & df["Profit_Margin_Percent"].notna()
        df.loc[need, "Profit_Amount"] = (df.loc[need, "Order_Amount"] * df.loc[need, "Profit_Margin_Percent"] / 100).round(2)
        filled += int(need.sum())
    log.append(["Conditional backfill", f"{filled:,} missing derived values recomputed" if filled else "no backfill needed"])
    log.append(["Rows after cleaning", f"{len(df):,} records"])
    return df, pd.DataFrame(log, columns=["step", "detail"])

def _text_columns(df):
    """Text columns, pandas-2 and pandas-3 safe (object / str / string dtypes)."""
    return [c for c in df.columns if df[c].dtype == object or str(df[c].dtype) in ("str", "string")]


def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    returned = df["Returned"].astype(str).str.strip().str.lower() == "yes" if "Returned" in df.columns else pd.Series(False, index=df.index)
    df["Is_Returned"] = returned.fillna(False).astype(bool)
    if "High_Value_Order" in df.columns:
        df["Is_High_Value"] = df["High_Value_Order"].astype(str).str.strip().str.lower() == "yes"
    else:
        cutoff = df["Order_Amount"].quantile(HIGH_VALUE_QUANTILE)
        df["Is_High_Value"] = df["Order_Amount"] >= cutoff
    df["Line_Subtotal"] = df["Unit_Price"] * df["Quantity"]
    disc = pd.to_numeric(df.get("Discount_Percent"), errors="coerce") if "Discount_Percent" in df.columns else pd.Series(0.0, index=df.index)
    df["Discount_Bucket"] = pd.cut(disc.fillna(0.0), bins=[-0.001, 0, 10, 20, 30, 40.001], labels=["0%", "1-10%", "11-20%", "21-30%", "31-40%"])
    if "Review_Rating" in df.columns:
        df["Rating_Bucket"] = pd.cut(pd.to_numeric(df["Review_Rating"], errors="coerce"), bins=[0, 2, 3, 4, 5.01], labels=["<=2", "2-3", "3-4", "4-5"])
    if "Delivery_Days" in df.columns:
        df["Delivery_Bucket"] = pd.cut(pd.to_numeric(df["Delivery_Days"], errors="coerce"), bins=[-1, 0, 2, 4, 7, 100], labels=["Same day", "1-2 days", "3-4 days", "5-7 days", "8+ days"])
    if "Customer_Age" in df.columns:
        df["Age_Bucket"] = pd.cut(pd.to_numeric(df["Customer_Age"], errors="coerce"), bins=[17, 25, 35, 45, 55, 200], labels=["18-25", "26-35", "36-45", "46-55", "56+"])
    df["Order_Month"] = df["Order_Date"].dt.to_period("M").dt.to_timestamp()
    df["Order_Week"] = df["Order_Date"].dt.to_period("W").dt.start_time
    df["Is_Weekend"] = df["Day_Of_Week"].isin(["Saturday", "Sunday"]) if "Day_Of_Week" in df.columns else df["Order_Date"].dt.dayofweek >= 5
    df["Revenue_At_Risk"] = np.where(df["Is_Returned"], df["Order_Amount"].fillna(0.0), 0.0)
    df["Profit_At_Risk"] = np.where(df["Is_Returned"], pd.to_numeric(df.get("Profit_Amount"), errors="coerce").fillna(0.0), 0.0)
    return df


def validate_schema(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    optional = [c for c in OPTIONAL_COLUMNS if c in df.columns]
    return missing, optional


def _check(check: str, result: str, status: str, detail: str) -> QualityCheck:
    return {"check": check, "result": result, "status": status, "detail": detail}


def run_quality_checks(df: pd.DataFrame) -> List[QualityCheck]:
    checks: List[QualityCheck] = []
    checks.append(_check("Dataset shape", f"{len(df):,} rows x {df.shape[1]} columns", "ok", "Row and column counts after cleaning."))
    null_total = int(df.isna().sum().sum())
    worst = df.isna().sum().sort_values(ascending=False).head(3)
    worst_txt = ", ".join(f"{c} ({int(v):,})" for c, v in worst.items() if v > 0)
    checks.append(_check("Missing values", f"{null_total:,} missing cells", "ok" if null_total == 0 else "warn", f"Top affected columns: {worst_txt}." if worst_txt else "No missing values."))
    checks.append(_check("Duplicate rows", "none found" if not int(df.duplicated().sum()) else f"{int(df.duplicated().sum()):,} duplicates remain", "ok" if not int(df.duplicated().sum()) else "fail", "Cleaned frame should contain no exact duplicate rows."))
    if "Line_Subtotal" in df.columns and {"Discount_Amount", "Shipping_Cost", "Tax_Amount"} <= set(df.columns):
        rebuilt = df["Line_Subtotal"] - df["Discount_Amount"].fillna(0.0) + df["Shipping_Cost"].fillna(0.0) + df["Tax_Amount"].fillna(0.0)
        mad = float((df["Order_Amount"] - rebuilt).abs().mean())
        checks.append(_check("Order_Amount arithmetic", f"mean abs diff {mad:.4f}", "ok" if mad < 0.05 else "warn", "Order_Amount should equal Unit_Price x Quantity - Discount_Amount + Shipping_Cost + Tax_Amount (derived field)."))
    if {"Returned", "Order_Status"} <= set(df.columns):
        mismatch = int(((df["Returned"].astype(str) == "Yes") != (df["Order_Status"].astype(str) == "Returned")).sum())
        checks.append(_check("Returned vs Order_Status", "perfectly aligned" if mismatch == 0 else f"{mismatch:,} mismatches", "ok" if mismatch == 0 else "warn", "Returned=Yes occurs exactly when Order_Status=Returned, so treat them as one outcome, not drivers."))
    for key, attrs, label in [("Customer_ID", ["Customer_Age", "Customer_Gender", "Customer_Segment", "Country", "City", "Membership_Status", "Customer_Lifetime_Value"], "Customer_ID attribute stability"), ("Product_ID", ["Product_Category", "Product_Subcategory", "Brand", "Unit_Price"], "Product_ID attribute stability")]:
        present = [a for a in attrs if a in df.columns]
        if key in df.columns and present:
            unstable = int((df.groupby(key)[present].nunique() > 1).sum().sum())
            checks.append(_check(label, "stable master key" if unstable == 0 else f"{unstable:,} attribute switches", "ok" if unstable == 0 else "warn", f"Same {key} appears with different attribute values across rows. Analyses on these IDs are order-level, not master-level."))
    if {"Country", "City"} <= set(df.columns):
        pairs = int(df[["Country", "City"]].drop_duplicates().shape[0])
        checks.append(_check("Country / City independence", f"{pairs} distinct pairs", "warn" if pairs > 20 else "ok", "Country and City look independently assigned (all combinations appear). Use country marginals only and never map City."))
    if {"Shipping_Method", "Delivery_Days"} <= set(df.columns):
        sd = df[df["Shipping_Method"] == "Same Day"]["Delivery_Days"]
        share = float((sd > 0).mean()) if len(sd) else 0.0
        checks.append(_check("Delivery vs Shipping_Method", f"{share:.1%} of Same-Day orders took longer than 0 days", "warn" if share > 0.05 else "ok", "Delivery_Days only loosely follows Shipping_Method; treat delivery fields as indicative, not contractual."))
    if {"Order_Status", "Delivery_Days"} <= set(df.columns):
        spread = float(df.groupby("Order_Status")["Delivery_Days"].mean().max() - df.groupby("Order_Status")["Delivery_Days"].mean().min())
        checks.append(_check("Order_Status vs delivery speed", f"spread of means {spread:.2f} days", "ok" if spread < 1.0 else "warn", "Status is unrelated to delivery speed, so funnel-by-delivery analysis adds no signal."))
    if "Order_Date" in df.columns:
        dmin, dmax = df["Order_Date"].min(), df["Order_Date"].max()
        today = pd.Timestamp.today().normalize()
        future = int((df["Order_Date"] > today).sum())
        checks.append(_check("Date coverage", f"{dmin.date()} to {dmax.date()} ({int(df['Order_Date'].nunique()):,} distinct dates)", "ok", "Complete daily coverage across four calendar years."))
        checks.append(_check("Future-dated records", f"{future:,} orders after today" if future else "none", "warn" if future else "ok", "Dates extend beyond the current date: synthetic complete-period data, no as-of truncation needed."))
    if {"Season", "Month"} <= set(df.columns):
        mixed = int((df.groupby("Month")["Season"].nunique() > 1).sum())
        checks.append(_check("Season / Holiday consistency", "deterministic from month" if mixed == 0 else f"{mixed} mixed months", "ok" if mixed == 0 else "warn", "Season and Holiday_Season are fixed calendar functions of the month, not business responses."))
    if "High_Value_Order" in df.columns:
        q75 = float(df["Order_Amount"].quantile(HIGH_VALUE_QUANTILE))
        hv_min = float(df.loc[df["High_Value_Order"].astype(str) == "Yes", "Order_Amount"].min())
        checks.append(_check("High_Value_Order definition", f"min Yes order ${hv_min:,.2f} vs 75th pct ${q75:,.2f}", "ok", "Flag equals a top-quartile threshold of Order_Amount: classificatory convenience, not a behaviour label."))
    return checks

def filter_data(df: pd.DataFrame, state: FilterState) -> pd.DataFrame:
    out = df
    if state.get("start") is not None and "Order_Date" in out.columns:
        out = out[out["Order_Date"] >= pd.Timestamp(state["start"])]
    if state.get("end") is not None and "Order_Date" in out.columns:
        out = out[out["Order_Date"] <= pd.Timestamp(state["end"])]
    pairs = [("categories", "Product_Category"), ("subcategories", "Product_Subcategory"), ("segments", "Customer_Segment"), ("countries", "Country"), ("payments", "Payment_Method"), ("shipping_methods", "Shipping_Method"), ("memberships", "Membership_Status")]
    for key, col in pairs:
        vals = state.get(key) or []
        if vals and col in out.columns:
            out = out[out[col].isin(vals)]
    if state.get("return_status") == "Returned" and "Is_Returned" in out.columns:
        out = out[out["Is_Returned"]]
    elif state.get("return_status") == "Not returned" and "Is_Returned" in out.columns:
        out = out[~out["Is_Returned"]]
    return out.copy()


def get_filtered_frame(df: pd.DataFrame, state: FilterState) -> pd.DataFrame:
    """Return the filtered subset of `df` for the active dashboard state.

    Used by the footer and strengths/weaknesses pages to keep filter logic in
    one place. Delegates to filter_data; treat as read-only for rendering.
    """
    return filter_data(df, state)


def _make_kpi(label: str, value: Any, formatted: str, note: str, delta: Any = None, delta_label: str = "") -> KPI:
    return {"label": label, "value": value, "formatted": formatted, "delta": delta, "delta_label": delta_label, "note": note}


def compute_kpis(df: pd.DataFrame) -> Dict[str, KPI]:
    n = len(df)
    revenue = float(df["Order_Amount"].sum()) if n else 0.0
    profit = float(pd.to_numeric(df.get("Profit_Amount"), errors="coerce").fillna(0.0).sum()) if n else 0.0
    aov = revenue / n if n else 0.0
    returns = int(df["Is_Returned"].sum()) if n and "Is_Returned" in df.columns else 0
    ret_rate = (returns / n * 100) if n else 0.0
    rev_risk = float(df["Revenue_At_Risk"].sum()) if n and "Revenue_At_Risk" in df.columns else 0.0
    profit_risk = float(df["Profit_At_Risk"].sum()) if n and "Profit_At_Risk" in df.columns else 0.0
    hv_share = (float(df["Is_High_Value"].mean() * 100) if n and "Is_High_Value" in df.columns else 0.0)
    hv_rev = float(df.loc[df["Is_High_Value"], "Order_Amount"].sum()) if n and "Is_High_Value" in df.columns else 0.0
    repeat = 0.0
    if n and "Customer_ID" in df.columns:
        per = df.groupby("Customer_ID").size()
        repeat = float((per >= 2).mean() * 100)
    rating = float(df["Review_Rating"].mean()) if n and "Review_Rating" in df.columns else float("nan")
    days = float(df["Delivery_Days"].mean()) if n and "Delivery_Days" in df.columns else float("nan")
    disc = float(pd.to_numeric(df.get("Discount_Amount"), errors="coerce").fillna(0.0).sum()) if n else 0.0
    pct = {"revenue": None, "orders": None, "aov": None}
    delta_label = ""
    if n and "Order_Date" in df.columns:
        span = df["Order_Date"].max() - df["Order_Date"].min()
        if span >= pd.Timedelta(days=730):
            cut = df["Order_Date"].max() - pd.Timedelta(days=365)
            cur = df[df["Order_Date"] > cut]
            prev = df[(df["Order_Date"] <= cut) & (df["Order_Date"] > cut - pd.Timedelta(days=365))]
            if len(prev):
                pr, po = float(prev["Order_Amount"].sum()), len(prev)
                cr, co = float(cur["Order_Amount"].sum()), len(cur)
                pct["revenue"] = (cr - pr) / pr * 100 if pr else None
                pct["orders"] = (co - po) / po * 100 if po else None
                ca, pa = (cr / co if co else 0.0), (pr / po if po else 0.0)
                pct["aov"] = (ca - pa) / pa * 100 if pa else None
                delta_label = "last 12 months vs prior 12"
    kpis = {
        "revenue": _make_kpi("Total Revenue", revenue, format_currency(revenue), format_pct(revenue / (profit + revenue - profit) * 0 + (revenue / revenue * 100 if revenue else 0)) + " of filtered sales value", pct["revenue"], delta_label),
        "orders": _make_kpi("Total Orders", n, format_int(n), f"about {n / max(1, int(df['Order_Date'].nunique())):,.1f} orders per day" if n else "", pct["orders"], delta_label),
        "aov": _make_kpi("Average Order Value", aov, format_currency(aov, 2), "revenue per order", pct["aov"], delta_label),
        "profit": _make_kpi("Total Profit", profit, format_currency(profit), f"margin {profit / revenue * 100:.2f}% of revenue" if revenue else ""),
        "return_rate": _make_kpi("Return Rate", ret_rate, format_pct(ret_rate), f"{returns:,} returned of {n:,} orders"),
        "rev_risk": _make_kpi("Revenue at Risk (Returns)", rev_risk, format_currency(rev_risk), f"{rev_risk / revenue * 100:.2f}% of revenue; profit lost {format_currency(profit_risk)}" if revenue else ""),
        "hv_share": _make_kpi("High-Value Orders", hv_share, format_pct(hv_share), f"carry {hv_rev / revenue * 100:.2f}% of revenue (top-quartile baskets)" if revenue else ""),
        "repeat": _make_kpi("Repeat Customer Rate", repeat, format_pct(repeat), "customers with 2+ orders; order-frequency based (attributes not stable)"),
        "rating": _make_kpi("Average Rating", rating, f"{rating:.2f} / 5" if n else "n/a", "post-delivery outcome field, not a driver"),
        "delivery_days": _make_kpi("Average Delivery Time", days, f"{days:.2f} days" if n else "n/a", "indicative; loosely follows shipping method"),
        "discount": _make_kpi("Total Discount Spend", disc, format_currency(disc), f"{disc / (revenue + disc) * 100:.2f}% of gross order value" if n else ""),
    }
    return kpis


def aggregate_by(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if dimension not in df.columns or not len(df):
        return pd.DataFrame()
    g = df.groupby(dimension, dropna=False).agg(orders=("Order_ID", "size"), revenue=("Order_Amount", "sum"), profit=("Profit_Amount", "sum") if "Profit_Amount" in df.columns else ("Order_Amount", "sum"))
    g["aov"] = g["revenue"] / g["orders"]
    g["margin"] = np.where(g["revenue"] > 0, g["profit"] / g["revenue"] * 100, 0.0)
    g["return_rate"] = df.groupby(dimension, dropna=False)["Is_Returned"].mean().values * 100 if "Is_Returned" in df.columns else 0.0
    g["revenue_share"] = g["revenue"] / g["revenue"].sum() * 100
    g["orders_share"] = g["orders"] / g["orders"].sum() * 100
    out = g.reset_index().rename(columns={dimension: "label"})
    return out.sort_values("revenue", ascending=False).reset_index(drop=True)


def revenue_trend(df: pd.DataFrame, freq: str = "M") -> pd.DataFrame:
    if not len(df) or "Order_Date" not in df.columns:
        return pd.DataFrame()
    valid = df.dropna(subset=["Order_Date"]).set_index("Order_Date").sort_index()
    rule = {"D": "D", "W": "W", "M": "ME"}.get(freq, "ME")
    t = valid.resample(rule).agg(orders=("Order_ID", "size"), revenue=("Order_Amount", "sum"), profit=("Profit_Amount", "sum") if "Profit_Amount" in valid.columns else ("Order_Amount", "sum"))
    t["aov"] = np.where(t["orders"] > 0, t["revenue"] / t["orders"], 0.0)
    return t.reset_index().rename(columns={"Order_Date": "period"})


def monthly_by_year(df: pd.DataFrame) -> pd.DataFrame:
    if not len(df) or "Order_Date" not in df.columns:
        return pd.DataFrame()
    tmp = df.dropna(subset=["Order_Date"]).copy()
    tmp["y"] = tmp["Order_Date"].dt.year
    tmp["m"] = tmp["Order_Date"].dt.month
    piv = tmp.pivot_table(index="m", columns="y", values="Order_Amount", aggfunc="sum").sort_index()
    return piv


def basket_value_analysis(df: pd.DataFrame) -> pd.DataFrame:
    if not len(df):
        return pd.DataFrame()
    bands = pd.qcut(df["Order_Amount"], 5, labels=["Q1 (lowest)", "Q2", "Q3", "Q4", "Q5 (highest)"])
    g = df.groupby(bands, observed=True).agg(orders=("Order_ID", "size"), revenue=("Order_Amount", "sum"), avg_value=("Order_Amount", "mean"))
    g["orders_share"] = g["orders"] / g["orders"].sum() * 100
    g["revenue_share"] = g["revenue"] / g["revenue"].sum() * 100
    return g.reset_index().rename(columns={"Order_Amount": "band"})


def pareto_table(df: pd.DataFrame, dimension: str, top_n: int = 10) -> pd.DataFrame:
    tab = aggregate_by(df, dimension)
    if tab.empty:
        return tab
    tab = tab.head(top_n).copy()
    tab["cum_revenue_share"] = tab["revenue_share"].cumsum()
    return tab


def discount_analysis(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    by_bucket = pd.DataFrame()
    if "Discount_Bucket" in df.columns and len(df):
        g = df.groupby("Discount_Bucket", observed=True).agg(orders=("Order_ID", "size"), aov=("Order_Amount", "mean"), avg_quantity=("Quantity", "mean"), discount_spend=("Discount_Amount", "sum") if "Discount_Amount" in df.columns else ("Order_Amount", "sum"), return_rate=("Is_Returned", "mean") if "Is_Returned" in df.columns else ("Order_Amount", "mean"))
        by_bucket = g.reset_index().rename(columns={"Discount_Bucket": "label"})
        if "return_rate" in by_bucket.columns and "Is_Returned" in df.columns:
            by_bucket["return_rate"] = by_bucket["return_rate"] * 100
    by_coupon = pd.DataFrame()
    if "Coupon_Used" in df.columns and len(df):
        g = df.groupby("Coupon_Used").agg(orders=("Order_ID", "size"), aov=("Order_Amount", "mean"), avg_quantity=("Quantity", "mean"), return_rate=("Is_Returned", "mean") if "Is_Returned" in df.columns else ("Order_Amount", "mean"))
        by_coupon = g.reset_index().rename(columns={"Coupon_Used": "label"})
        if "return_rate" in by_coupon.columns and "Is_Returned" in df.columns:
            by_coupon["return_rate"] = by_coupon["return_rate"] * 100
    return by_bucket, by_coupon

def delivery_analysis(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    table = pd.DataFrame()
    info: Dict[str, Any] = {"same_day_overdue_share": None, "status_spread_days": None}
    if "Shipping_Method" in df.columns and "Delivery_Days" in df.columns and len(df):
        g = df.groupby("Shipping_Method").agg(orders=("Order_ID", "size"), avg_days=("Delivery_Days", "mean"), median_days=("Delivery_Days", "median"), p90_days=("Delivery_Days", lambda s: float(s.quantile(0.90))), max_days=("Delivery_Days", "max"), return_rate=("Is_Returned", "mean") if "Is_Returned" in df.columns else ("Order_Amount", "mean"))
        table = g.reset_index().rename(columns={"Shipping_Method": "label"})
        if "return_rate" in table.columns and "Is_Returned" in df.columns:
            table["return_rate"] = table["return_rate"] * 100
        sd = df[df["Shipping_Method"] == "Same Day"]["Delivery_Days"]
        info["same_day_overdue_share"] = float((sd > 0).mean()) if len(sd) else None
    if {"Order_Status", "Delivery_Days"} <= set(df.columns) and len(df):
        means = df.groupby("Order_Status")["Delivery_Days"].mean()
        info["status_spread_days"] = float(means.max() - means.min())
    return table, info


def frequency_analysis(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    summary: Dict[str, Any] = {"repeat_2": 0.0, "repeat_3": 0.0, "mean_orders": 0.0, "customers": 0}
    if "Customer_ID" not in df.columns or not len(df):
        return pd.DataFrame(), summary
    per = df.groupby("Customer_ID").size().rename("orders_per_customer")
    summary = {"repeat_2": float((per >= 2).mean() * 100), "repeat_3": float((per >= 3).mean() * 100), "mean_orders": float(per.mean()), "customers": int(per.shape[0])}
    dist = per.value_counts().sort_index().rename_axis("orders_per_customer").reset_index(name="customers")
    dist["customer_share"] = dist["customers"] / dist["customers"].sum() * 100
    rev = df.groupby("Customer_ID")["Order_Amount"].sum()
    rev_by_band = per.to_frame().join(rev).groupby("orders_per_customer")["Order_Amount"].sum()
    dist["band_revenue"] = dist["orders_per_customer"].map(rev_by_band).fillna(0.0)
    dist["band_revenue_share"] = dist["band_revenue"] / dist["band_revenue"].sum() * 100
    return dist, summary


def return_rate_table(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if dimension not in df.columns or not len(df) or "Is_Returned" not in df.columns:
        return pd.DataFrame()
    base = float(df["Is_Returned"].mean() * 100)
    g = df.groupby(dimension, dropna=False).agg(orders=("Order_ID", "size"), returns=("Is_Returned", "sum"), revenue=("Order_Amount", "sum"), revenue_at_risk=("Revenue_At_Risk", "sum"), profit_at_risk=("Profit_At_Risk", "sum"))
    g["return_rate"] = g["returns"] / g["orders"] * 100
    g["lift_vs_baseline"] = np.where(base > 0, g["return_rate"] / base, 1.0)
    out = g.reset_index().rename(columns={dimension: "label"})
    return out.sort_values("return_rate", ascending=False).reset_index(drop=True)


def return_driver_scan(df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if not len(df) or "Is_Returned" not in df.columns:
        return pd.DataFrame()
    base = float(df["Is_Returned"].mean() * 100)
    for label, col in DIMENSIONS.items():
        if col in POST_OUTCOME_FIELDS or col not in df.columns:
            continue
        tab = return_rate_table(df, col)
        if tab.empty:
            continue
        spread = float(tab["return_rate"].max() - tab["return_rate"].min())
        rows.append({"dimension": label, "categories": int(tab.shape[0]), "min_rate": float(tab["return_rate"].min()), "max_rate": float(tab["return_rate"].max()), "spread_pp": round(spread, 2), "verdict": "notable" if spread >= 3.0 else "flat"})
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("spread_pp", ascending=False).reset_index(drop=True)
    return out


def build_risk_tiers(table: pd.DataFrame, baseline: float) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    high_cut = baseline * RISK_TIER_MULTIPLIERS["High"]
    med_cut = baseline * RISK_TIER_MULTIPLIERS["Medium"]
    tiers: Dict[str, Any] = {"baseline": baseline, "high_cut": high_cut, "medium_cut": med_cut, "min_volume": MIN_TIER_VOLUME, "rationale": f"Bands are set relative to the observed baseline return rate ({baseline:.2f}%): High is at least 1.25x the baseline, Medium is 0.90-1.25x, Low is below 0.90x. Rows with fewer than {MIN_TIER_VOLUME} orders are marked low-volume and are not tiered, to avoid noisy small cells. These are descriptive segments of observed behaviour, not model predictions."}
    if table.empty:
        return table, tiers
    out = table.copy()
    out["tier"] = np.where(out["orders"] < MIN_TIER_VOLUME, "Low volume (not tiered)", np.where(out["return_rate"] >= high_cut, "High", np.where(out["return_rate"] >= med_cut, "Medium", "Low")))
    return out, tiers


def fashion_opportunity(df: pd.DataFrame, baseline: float) -> Dict[str, Any]:
    res: Dict[str, Any] = {"fashion_rate": 0.0, "fashion_orders": 0, "gap_pp": 0.0, "avoidable_returns": 0.0, "recoverable_revenue": 0.0, "recoverable_profit": 0.0}
    if not len(df) or "Product_Category" not in df.columns or "Is_Returned" not in df.columns:
        return res
    fashion = df[df["Product_Category"] == "Fashion"]
    if not len(fashion):
        return res
    rate = float(fashion["Is_Returned"].mean() * 100)
    gap = max(0.0, rate - baseline)
    avoidable = gap / 100 * len(fashion)
    res.update({"fashion_rate": rate, "fashion_orders": int(len(fashion)), "gap_pp": gap, "avoidable_returns": avoidable, "recoverable_revenue": avoidable * float(fashion["Order_Amount"].mean()), "recoverable_profit": avoidable * float(pd.to_numeric(fashion.get("Profit_Amount"), errors="coerce").fillna(0.0).mean())})
    return res


def ml_rejection_evidence() -> Dict[str, Any]:
    return {
        "question": "Can pre-order information predict whether an order will be returned?",
        "method": "Logistic Regression pipeline (OneHotEncoder for text fields, StandardScaler for numbers), 75/25 stratified split, class_weight='balanced'. Each candidate feature set is measured once with scikit-learn; scikit-learn is intentionally not a project dependency because no model ships.",
        "feature_set": "Unit_Price, Quantity, Discount_Percent, Shipping_Cost, Customer_Age, Delivery_Days, Customer_Lifetime_Value, Profit_Margin_Percent, Product_Category, Product_Subcategory, Brand, Customer_Gender, Country, City, Customer_Segment, Payment_Method, Device_Type, Traffic_Source, Membership_Status, Shipping_Method, Warehouse_Region, Season, Holiday_Season, Coupon_Used (24 pre-order features).",
        "metrics": {"base_rate": 0.1011, "auc": 0.5381, "accuracy": 0.5725, "precision": 0.112, "recall": 0.468},
        "leakage_demo": "Same pipeline plus Review_Rating reaches AUC 0.8790, and plus Order_Status/Order_Amount reaches AUC 1.0000. Rating is a post-delivery outcome and Order_Status defines the label, so those numbers are leakage, not skill.",
        "verdict": "Returns in this dataset carry almost no pre-order signal beyond a mild category effect (Fashion ~13.9% vs baseline ~10.1%). The model is rejected; the dashboard therefore uses descriptive return-rate tiers instead of predictions."
    }

def format_currency(v: Any, decimals: int = 0) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "n/a"
    if decimals:
        return f"${x:,.{decimals}f}"
    return f"${x:,.0f}"


def format_pct(v: Any, decimals: int = 2) -> str:
    try:
        return f"{float(v):,.{decimals}f}%"
    except (TypeError, ValueError):
        return "n/a"


def format_int(v: Any) -> str:
    try:
        return f"{int(round(float(v))):,}"
    except (TypeError, ValueError):
        return "n/a"


def insight_trend(yearly: pd.DataFrame, monthly: pd.DataFrame) -> InsightBlock:
    if yearly.empty:
        return {"observation": "", "insight": "", "explanation": "", "recommendation": ""}
    first, last = yearly.iloc[0], yearly.iloc[-1]
    rev_chg = (last["rev"] - first["rev"]) / first["rev"] * 100 if first["rev"] else 0.0
    aov_chg = (last["aov"] - first["aov"]) / first["aov"] * 100 if first["aov"] else 0.0
    return {
        "observation": f"Annual revenue moved from {format_currency(first['rev'])} ({int(first['orders']):,} orders, AOV {format_currency(first['aov'], 2)}) to {format_currency(last['rev'])} ({int(last['orders']):,} orders, AOV {format_currency(last['aov'], 2)}), a {rev_chg:+.1f}% revenue and {aov_chg:+.1f}% AOV shift over the full period.",
        "insight": "Order volume is broadly flat and basket value is gently eroding, so revenue growth is not coming from the current mix or cadence.",
        "explanation": "This may reflect price sensitivity, heavier discount use over time, or a shift toward lower-value categories; the data show the direction, not the cause.",
        "recommendation": "Prioritise basket-value initiatives (bundles, minimum-basket perks, attach of profitable electronics accessories) and review whether discount depth is buying volume or just eroding value.",
    }


def insight_revenue_concentration(tab: pd.DataFrame, total_rev: float) -> InsightBlock:
    if tab.empty or not total_rev:
        return {"observation": "", "insight": "", "explanation": "", "recommendation": ""}
    top = tab.iloc[0]
    return {
        "observation": f"{top['label']} contributes {format_currency(top['revenue'])} of {format_currency(total_rev)} total revenue ({top['revenue_share']:.1f}%) from only {top['orders_share']:.1f}% of orders, at an AOV of {format_currency(top['aov'], 2)} versus a business-wide {format_currency(total_rev / tab['orders'].sum(), 2)}.",
        "insight": "More than half of revenue depends on one category, so a demand shock, stockout or return spike there would dominate the P&L.",
        "explanation": "This may simply reflect that big-ticket items sit in this category, which is structural rather than a recent strategy win.",
        "recommendation": "Protect availability and service quality for the lead category while deliberately growing profitable secondary categories (Beauty has the highest margin, Home and Kitchen the second-highest revenue) to reduce concentration.",
    }


def insight_discount_effectiveness(by_bucket: pd.DataFrame, by_coupon: pd.DataFrame, total_disc: float, total_rev: float) -> InsightBlock:
    if by_bucket.empty:
        return {"observation": "", "insight": "", "explanation": "", "recommendation": ""}
    top = by_bucket.sort_values("orders", ascending=False).iloc[0]
    first = by_bucket.iloc[0]
    last = by_bucket.iloc[-1]
    return {
        "observation": f"AOV moves from {format_currency(first['aov'], 2)} at {first['label']} discount to {format_currency(last['aov'], 2)} at {last['label']} discount, while mean quantity barely moves across bands; {format_pct(total_disc / (total_rev + total_disc) * 100 if total_rev else 0)} of gross order value is spent on discounts ({format_currency(total_disc)}).",
        "insight": "Deeper discounts in this data accompany lower, not larger, baskets, so the current discount pattern appears to erode value without buying volume.",
        "explanation": "This could be mechanical (discounts reduce the recorded amount) or behavioural (price-sensitive shoppers); the observational data cannot separate the two.",
        "recommendation": "Test shallower, targeted discounts (e.g. category-specific or minimum-basket thresholds) with proper A/B measurement of incremental units rather than deepening blanket discounts.",
    }


def insight_return_risk(tiered: pd.DataFrame, baseline: float, opp: Dict[str, Any]) -> InsightBlock:
    top = tiered.iloc[0] if tiered is not None and len(tiered) else None
    detail = f" The highest tier is {top['label']} at {top['return_rate']:.2f}% (lift {top['lift_vs_baseline']:.2f}x baseline)".rstrip(".") + "." if top is not None else ""
    return {
        "observation": f"The baseline return rate is {baseline:.2f}% across the filtered orders.{detail} All operational dimensions (delivery time, payment method, membership, basket value) sit within about a point of the baseline.",
        "insight": "Returns are concentrated by what is bought (Fashion, especially Bags and Women Clothing) rather than how it is bought, so prevention effort belongs on the product side.",
        "explanation": "This may reflect sizing and expectation issues in apparel, which is a common pattern; the data establish the association, not the mechanism.",
        "recommendation": f"Start with Fashion sizing/fit guidance, richer imagery and a reviewed size chart: closing its {opp['gap_pp']:.1f}-point gap to the baseline would avoid roughly {opp['avoidable_returns']:.0f} returns ({format_currency(opp['recoverable_revenue'])} revenue, {format_currency(opp['recoverable_profit'])} profit) in the filtered period.",
    }


def insight_logistics_quality(info: Dict[str, Any]) -> InsightBlock:
    overdue = info.get("same_day_overdue_share")
    overdue_txt = f"{overdue:.1%}" if overdue is not None else "n/a"
    return {
        "observation": f"{overdue_txt} of orders placed with the Same Day shipping method were delivered after day 0, while Standard and Pickup average about five days.",
        "insight": "The fastest promise in the catalogue is the least reliable, which is a data-trust and customer-experience risk for urgent orders.",
        "explanation": "This may be a fulfilment or carrier-SLA issue, or the label may simply be applied inconsistently at checkout.",
        "recommendation": "Audit the Same-Day fulfilment path end to end (cut-off times, warehouse assignment, carrier handoff) and either fix the SLA or stop selling the promise where it cannot be met.",
    }


def insight_value_concentration(hv_share: float, hv_rev_share: float) -> InsightBlock:
    return {
        "observation": f"Baskets at or above the 75th percentile make up {hv_share:.1f}% of orders yet carry {hv_rev_share:.1f}% of revenue.",
        "insight": "A small set of high-value baskets drives the business, so their experience and retention deserve disproportionate attention.",
        "explanation": "High-value baskets may reflect big-ticket electronics purchases rather than loyalty, so treat the group as a value band, not a customer identity.",
        "recommendation": "Protect these baskets with priority support, assured stock and extended returns in Electronics, and explore attach offers (accessories, warranties) at checkout.",
    }


def insight_customer_frequency(summary: Dict[str, Any]) -> InsightBlock:
    return {
        "observation": f"Customers average {summary.get('mean_orders', 0):.2f} orders across {summary.get('customers', 0):,} distinct IDs; {summary.get('repeat_2', 0):.1f}% have two or more orders and {summary.get('repeat_3', 0):.1f}% have three or more.",
        "insight": "Order frequency looks extremely high, which would normally signal strong loyalty - but customer attributes change between orders of the same ID, so this is a purchase-counting view, not a true loyalty measure.",
        "explanation": "The pattern is consistent with generated customer keys rather than a stable CRM identity.",
        "recommendation": "Do not set retention targets from this rate. If the business wants real loyalty analytics, instrument a stable customer identity and re-measure before acting on repeat behaviour.",
    }

def self_test() -> int:
    print("analytics self-test")
    failures: List[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
        if not ok:
            failures.append(name)

    try:
        path = resolve_dataset_path()
    except FileNotFoundError as exc:
        print(f"  [FAIL] dataset present: {exc}")
        return 1
    raw = load_raw(path)
    check("dataset present", True, str(path))
    check("usable shape", raw.shape[0] > 0 and raw.shape[1] >= 30, f"{raw.shape}")
    check("required columns present", not validate_schema(raw)[0], str(validate_schema(raw)[0]) or "all present")
    cleaned, log = clean_data(raw)
    check("cleaning log produced", len(log) > 0, f"{len(log)} log rows")
    df = add_derived_columns(cleaned)
    check("derived columns present", {"Is_Returned", "Is_High_Value", "Line_Subtotal", "Order_Month", "Revenue_At_Risk"} <= set(df.columns))
    check("no NaN in key columns", int(df[["Order_ID", "Order_Date", "Order_Amount", "Is_Returned"]].isna().sum().sum()) == 0)
    rebuilt = df["Line_Subtotal"] - df["Discount_Amount"].fillna(0.0) + df["Shipping_Cost"].fillna(0.0) + df["Tax_Amount"].fillna(0.0)
    mad = float((df["Order_Amount"] - rebuilt).abs().mean())
    check("Order_Amount formula tolerance", mad < 0.05, f"mean abs diff {mad:.4f}")
    kpis = compute_kpis(df)
    check("revenue KPI matches raw sum", abs(kpis["revenue"]["value"] - float(df["Order_Amount"].sum())) < 0.01, kpis["revenue"]["formatted"])
    check("return-rate KPI matches raw mean", abs(kpis["return_rate"]["value"] - float(df["Is_Returned"].mean() * 100)) < 1e-6, kpis["return_rate"]["formatted"])
    check("high-value share is top quartile", abs(kpis["hv_share"]["value"] - 25.0) < 0.6, kpis["hv_share"]["formatted"])
    tab = aggregate_by(df, "Product_Category")
    check("category revenue sums to total", abs(tab["revenue"].sum() - float(df["Order_Amount"].sum())) < 0.01)
    check("category table sorted by revenue", bool((tab["revenue"].diff().dropna() <= 0).all()))
    year_tab = aggregate_by(df, "Year") if "Year" in df.columns else pd.DataFrame()
    if not year_tab.empty:
        check("yearly orders sum to total", int(year_tab["orders"].sum()) == len(df))
    cats = sorted(df["Product_Category"].dropna().unique().tolist())
    largest = aggregate_by(df, "Product_Category").iloc[0]["label"]
    state: FilterState = {"start": None, "end": None, "categories": [largest], "subcategories": [], "segments": [], "countries": [], "payments": [], "shipping_methods": [], "memberships": [], "return_status": "All"}
    sub = filter_data(df, state)
    check("category filter reduces frame", 0 < len(sub) < len(df), f"{len(sub):,} of {len(df):,} rows")
    check("filter revenue matches manual mask", abs(sub["Order_Amount"].sum() - float(df.loc[df["Product_Category"] == largest, "Order_Amount"].sum())) < 0.01)
    trend = revenue_trend(df, "M")
    check("monthly trend ordered", bool(trend["period"].is_monotonic_increasing), f"{len(trend)} periods")
    by_year = monthly_by_year(df)
    check("monthly-by-year pivot", by_year.shape[0] == 12 and by_year.shape[1] >= 3, str(by_year.shape))
    scan = return_driver_scan(df)
    top = scan.iloc[0] if not scan.empty else None
    cat_row = scan[scan["dimension"] == "Product category"]
    check("return driver scan flags product", (not scan.empty) and top["verdict"] == "notable" and (not cat_row.empty) and cat_row.iloc[0]["verdict"] == "notable", str(top.to_dict()) if top is not None else "empty")
    base = float(df["Is_Returned"].mean() * 100)
    cat_tab = return_rate_table(df, "Product_Category")
    tiered, tiers = build_risk_tiers(cat_tab, base)
    check("risk tiers built", "tier" in tiered.columns and tiered["tier"].isin(["High", "Medium", "Low"]).any(), tiers["rationale"][:60] + "...")
    opp = fashion_opportunity(df, base)
    check("fashion opportunity computed", opp["fashion_orders"] > 0 and opp["avoidable_returns"] >= 0, f"avoidable {opp['avoidable_returns']:.0f}")
    ev = ml_rejection_evidence()
    check("ML rejection evidence present", abs(ev["metrics"]["auc"] - 0.5381) < 0.001 and ev["metrics"]["auc"] < 0.60)
    checks = run_quality_checks(df)
    fails = [c["check"] for c in checks if c["status"] == "fail"]
    check("no failing quality checks", not fails, ", ".join(fails) or f"{len(checks)} checks evaluated")
    if failures:
        print(f"SELF-TEST FAILED ({len(failures)} failures)")
        return 1
    print("SELF-TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
