"""
UPI Ecosystem Analytics - data pipeline
=======================================
One command refreshes everything Power BI reads:

    python pipeline/run_pipeline.py

What it does
  1. Loads monthly UPI data. If you drop the official NPCI/Dataful CSV into
     data/raw/ (any file name ending in .csv), that is used. Otherwise the
     verified seed file in data/seed/ is used.
  2. Cleans it and standardises units (volume in million, value in Rs crore).
  3. Builds a star schema in data/model/ (dim_date, dim_app, fact_* tables).
  4. Forecasts the next 12 months of volume (Holt-Winters, log scale),
     back-tests it on the last 6 actual months, and writes the accuracy (MAPE).
  5. Computes market-concentration metrics (top-2 / top-3 share, HHI).

Power BI points at data/model/ - after running this, press Refresh.
"""
from __future__ import annotations

import glob
import json
import os
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = os.path.join(ROOT, "data", "seed")
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "model")
FORECAST_MONTHS = 12
BACKTEST_MONTHS = 6

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}


# ---------------------------------------------------------------- 1. load
def load_monthly() -> tuple[pd.DataFrame, str]:
    raw_files = sorted(glob.glob(os.path.join(RAW, "*.csv")))
    if raw_files:
        df = pd.read_csv(raw_files[-1])
        df.columns = [c.strip().lower() for c in df.columns]
        # Dataful / NPCI layout: fiscal_year (e.g. 2025-26), month (name)
        if "fiscal_year" in df.columns:
            def to_date(r):
                start = int(str(r["fiscal_year"])[:4])
                m = MONTHS[str(r["month"]).strip().lower()]
                year = start if m >= 4 else start + 1
                return pd.Timestamp(year=year, month=m, day=1)
            df["month_date"] = df.apply(to_date, axis=1)
        else:
            df["month_date"] = pd.to_datetime(df["month"])
        df = df.rename(columns={
            "number_of_banks_live_on_upi": "banks_live",
            "no. of banks live on upi": "banks_live",
            "volume": "volume_mn", "volume (in mn.)": "volume_mn",
            "value": "value_cr", "value (in cr.)": "value_cr",
        })
        df["source"] = "NPCI official file: " + os.path.basename(raw_files[-1])
        return df, raw_files[-1]
    df = pd.read_csv(os.path.join(SEED, "upi_monthly_seed.csv"))
    df["month_date"] = pd.to_datetime(df["month"] + "-01")
    return df, "seed"


# ---------------------------------------------------------------- 2. clean
def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df[["month_date", "banks_live", "volume_mn", "value_cr", "source"]].copy()
    for c in ["banks_live", "volume_mn", "value_cr"]:
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
    df = (df.dropna(subset=["volume_mn"])
            .drop_duplicates("month_date", keep="last")
            .sort_values("month_date")
            .reset_index(drop=True))
    df["days_in_month"] = df["month_date"].dt.days_in_month
    df["avg_daily_volume_mn"] = (df["volume_mn"] / df["days_in_month"]).round(2)
    # Rs crore -> Rs ; million -> count  => average ticket size in Rs
    df["avg_ticket_rs"] = (df["value_cr"] * 1e7 / (df["volume_mn"] * 1e6)).round(0)
    df["date_key"] = df["month_date"].dt.strftime("%Y%m%d").astype(int)
    return df


# ---------------------------------------------------------------- 3. dims
def build_dim_date(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    d = pd.DataFrame({"month_date": pd.date_range(start, end, freq="MS")})
    d["date_key"] = d["month_date"].dt.strftime("%Y%m%d").astype(int)
    d["year"] = d["month_date"].dt.year
    d["month_num"] = d["month_date"].dt.month
    d["month_name"] = d["month_date"].dt.strftime("%b")
    d["month_year"] = d["month_date"].dt.strftime("%b %Y")
    fy_start = np.where(d["month_num"] >= 4, d["year"], d["year"] - 1)
    d["fiscal_year"] = [f"FY{str(s + 1)[2:]}" for s in fy_start]      # FY26 = Apr25-Mar26
    d["fiscal_month_num"] = ((d["month_num"] - 4) % 12) + 1
    d["fiscal_quarter"] = "Q" + ((d["fiscal_month_num"] - 1) // 3 + 1).astype(str)
    d["is_festive_season"] = d["month_num"].isin([10, 11]).map({True: "Festive (Oct-Nov)", False: "Regular"})
    return d


# ---------------------------------------------------------------- 4. forecast
def fit(series: pd.Series):
    # Holt-Winters (additive trend + additive 12-month seasonality) on log volume.
    # Chosen over SARIMA variants: lowest back-test error (6- and 12-month) and
    # a growth path consistent with recent YoY growth.
    return ExponentialSmoothing(np.log(series), trend="add", seasonal="add",
                                seasonal_periods=12).fit()


def forecast(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    s = df.set_index("month_date")["volume_mn"].asfreq("MS").interpolate()

    # back-test: train on all but the last N months, predict them
    train, test = s[:-BACKTEST_MONTHS], s[-BACKTEST_MONTHS:]
    bt = np.exp(fit(train).forecast(BACKTEST_MONTHS))
    mape = float((np.abs(bt.values - test.values) / test.values).mean() * 100)

    res = fit(s)
    point = res.forecast(FORECAST_MONTHS)
    # 80% interval: residual std on the log scale, widening with sqrt(horizon)
    sigma = float(np.std(res.resid, ddof=1))
    h = np.arange(1, FORECAST_MONTHS + 1)
    band = 1.2816 * sigma * np.sqrt(h)
    out = pd.DataFrame({
        "month_date": point.index,
        "forecast_volume_mn": np.exp(point.values).round(1),
        "lower_80_mn": np.exp(point.values - band).round(1),
        "upper_80_mn": np.exp(point.values + band).round(1),
        "type": "Forecast",
    })
    backtest = pd.DataFrame({
        "month_date": test.index, "forecast_volume_mn": bt.values.round(1),
        "lower_80_mn": np.nan, "upper_80_mn": np.nan, "type": "Backtest",
    })
    out = pd.concat([backtest, out], ignore_index=True)
    out["date_key"] = out["month_date"].dt.strftime("%Y%m%d").astype(int)
    meta = {
        "model": "Holt-Winters additive trend + 12-month seasonality on log(volume)",
        "backtest_months": BACKTEST_MONTHS,
        "backtest_mape_pct": round(mape, 2),
        "forecast_horizon_months": FORECAST_MONTHS,
        "last_actual_month": s.index[-1].strftime("%b %Y"),
        "forecast_end_month": out["month_date"].iloc[-1].strftime("%b %Y"),
        "forecast_end_volume_mn": float(out["forecast_volume_mn"].iloc[-1]),
    }
    return out, meta


# ---------------------------------------------------------------- 5. market share
def app_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    a = pd.read_csv(os.path.join(SEED, "app_share_seed.csv"))
    a["month_date"] = pd.to_datetime(a["month"] + "-01")
    rows = []
    for m, g in a.groupby("month_date"):
        known = g["volume_share_pct"].sum()
        if {"PhonePe", "Google Pay", "Paytm"}.issubset(set(g["app"])):
            rows.append({"month_date": m, "app": "Others", "volume_share_pct": round(100 - known, 2),
                         "value_share_pct": np.nan, "source": "Derived: 100 - listed apps"})
    a = pd.concat([a, pd.DataFrame(rows)], ignore_index=True)

    dim_app = pd.DataFrame({"app": sorted(a["app"].unique())})
    owners = {"PhonePe": "Walmart (Flipkart group)", "Google Pay": "Alphabet", "Paytm": "One97 Communications",
              "Navi": "Navi Technologies", "super.money": "Flipkart", "BHIM": "NPCI", "FamPay": "FamPay",
              "CRED": "CRED", "WhatsApp Pay": "Meta", "Amazon Pay": "Amazon", "Others": "Long tail"}
    dim_app["parent"] = dim_app["app"].map(owners)
    dim_app["app_group"] = dim_app["app"].map(
        lambda x: x if x in ("PhonePe", "Google Pay", "Paytm") else ("Others" if x == "Others" else "Challengers"))
    dim_app["app_id"] = range(1, len(dim_app) + 1)

    # concentration per month (only months where the top 3 are all known)
    conc = []
    for m, g in a.groupby("month_date"):
        sh = g.set_index("app")["volume_share_pct"]
        if not {"PhonePe", "Google Pay", "Paytm"}.issubset(sh.index):
            continue
        named = sh.drop("Others", errors="ignore")
        conc.append({
            "month_date": m,
            "top2_share_pct": round(sh["PhonePe"] + sh["Google Pay"], 2),
            "top3_share_pct": round(sh["PhonePe"] + sh["Google Pay"] + sh["Paytm"], 2),
            # HHI lower bound: 'Others' treated as fully fragmented
            "hhi_lower_bound": round(float((named ** 2).sum()), 0),
            "apps_above_30pct_cap": int((sh.drop("Others", errors="ignore") > 30).sum()),
        })
    conc = pd.DataFrame(conc)
    a = a.merge(dim_app[["app", "app_id"]], on="app")
    a["date_key"] = a["month_date"].dt.strftime("%Y%m%d").astype(int)
    conc["date_key"] = conc["month_date"].dt.strftime("%Y%m%d").astype(int)
    return a, dim_app, conc


# ---------------------------------------------------------------- 6. path fix
def point_power_bi_at_this_folder():
    """Rewrite the DataFolder parameter in the Power BI project (TMDL) so the
    report always reads data/model/ from wherever this folder now lives."""
    import re
    target = os.path.join(OUT, "")  # trailing separator
    for f in glob.glob(os.path.join(ROOT, "*.SemanticModel", "definition", "expressions.tmdl")):
        txt = open(f, encoding="utf-8").read()
        new = re.sub(r'expression DataFolder = "[^"]*"',
                     lambda _: f'expression DataFolder = "{target}"', txt)
        if new != txt:
            open(f, "w", encoding="utf-8").write(new)
            print(f"DataFolder -> {target}")


# ---------------------------------------------------------------- main
def main():
    os.makedirs(OUT, exist_ok=True)
    raw, used = load_monthly()
    monthly = clean(raw)
    fc, meta = forecast(monthly)
    app_share, dim_app, conc = app_tables()
    p2 = pd.read_csv(os.path.join(SEED, "p2p_p2m_seed.csv"))
    p2["month_date"] = pd.to_datetime(p2["month"] + "-01")
    p2["date_key"] = p2["month_date"].dt.strftime("%Y%m%d").astype(int)

    dim_date = build_dim_date(monthly["month_date"].min(), fc["month_date"].max())

    def save(df, name, cols=None):
        (df[cols] if cols else df).to_csv(os.path.join(OUT, name), index=False)

    save(dim_date, "dim_date.csv")
    save(dim_app, "dim_app.csv", ["app_id", "app", "parent", "app_group"])
    save(monthly, "fact_upi_monthly.csv",
         ["date_key", "banks_live", "volume_mn", "value_cr", "days_in_month",
          "avg_daily_volume_mn", "avg_ticket_rs", "source"])
    save(fc, "fact_forecast.csv", ["date_key", "type", "forecast_volume_mn", "lower_80_mn", "upper_80_mn"])
    save(app_share, "fact_app_share.csv", ["date_key", "app_id", "volume_share_pct", "value_share_pct", "source"])
    save(conc, "fact_concentration.csv",
         ["date_key", "top2_share_pct", "top3_share_pct", "hhi_lower_bound", "apps_above_30pct_cap"])
    save(p2, "fact_p2p_p2m.csv", ["date_key", "type", "volume_mn", "value_cr", "source"])

    meta.update({"run_at": datetime.now().isoformat(timespec="seconds"), "input": used,
                 "months_of_actuals": int(len(monthly)),
                 "months_with_value": int(monthly["value_cr"].notna().sum())})
    point_power_bi_at_this_folder()
    with open(os.path.join(OUT, "run_log.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
