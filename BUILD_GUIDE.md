# Build guide: from this kit to a finished Power BI dashboard (~60–90 min)

You need **Power BI Desktop** (free, Windows) and **Python 3.10+**.

---

## Step 0: Run the pipeline (5 min)

```bash
cd upi-powerbi
pip install -r requirements.txt
python pipeline/run_pipeline.py
```

You should see a JSON summary ending in `"months_of_actuals": 49`. The folder `data/model/` now holds 7 CSVs, and these are what Power BI reads.

> **Optional, but recommended before you publish:** download the full official monthly UPI CSV from Dataful (dataset 432, "Year and Month wise number of banks live on UPI…", sourced from NPCI). You can also build one from NPCI's monthly statistics Excel files. Drop it in `data/raw/` and rerun. The pipeline detects it automatically, fills the value gaps in the seed file, and extends history back to 2016.

---

## Step 1: Load data with Power Query (10 min)

1. Open Power BI Desktop and go to **Home → Transform data**.
2. **Manage Parameters → New**: name it `DataFolder`, type Text, and set the value to your full path ending in `\`, e.g. `C:\Projects\upi-powerbi\data\model\`.
3. For each block in `powerbi/power_query.m`: **New Source → Blank Query → Advanced Editor**, paste the block, then rename the query to the name in its comment. Create `fnLoadCsv` first.
4. Right-click `fnLoadCsv` and untick **Enable load**. Then **Close & Apply**.

## Step 2: Data model (star schema) (5 min)

In **Model view**, create these relationships (all single-direction, one-to-many):

| From (1) | To (*) |
|---|---|
| `dim_date[date_key]` | `fact_upi_monthly[date_key]` |
| `dim_date[date_key]` | `fact_forecast[date_key]` |
| `dim_date[date_key]` | `fact_app_share[date_key]` |
| `dim_date[date_key]` | `fact_concentration[date_key]` |
| `dim_date[date_key]` | `fact_p2p_p2m[date_key]` |
| `dim_app[app_id]` | `fact_app_share[app_id]` |

Then set up the columns:
- `dim_date[month_year]` → **Sort by column** → `month_date`
- `dim_date[month_name]` → **Sort by column** → `month_num`
- Hide every `date_key` and `app_id` column, plus the raw numeric fact columns, so report users only see measures.

**Take a screenshot of this model view for your README. Interviewers ask about it.**

## Step 3: Measures (15 min)

1. **Home → Enter data**, name the table `_Measures`, and click Load. Delete its default column after you've added your first measure.
2. Add every measure from `powerbi/measures.dax` (**Modeling → New measure**, paste one at a time).
3. Set the formats: `%` for anything named `%`, `0.0` for Bn and Lakh Cr, and `#,0` for Rs.
4. Optional: put the measures in display folders (Core, Time Intelligence, Forecast, Market, P2P-P2M).

## Step 4: Theme (1 min)

**View → Themes → Browse for themes** → `powerbi/upi_theme.json`

---

## Step 5: Build the 6 pages (40 min)

Use a 16:9 canvas. Put the page title top-left, the `Data Through` measure in a card top-right, and a fiscal year slicer on every page (sync slicers: **View → Sync slicers**).

### Page 1: Executive Overview
- **Title:** a card bound to `Overview Title` (dynamic text)
- **KPI cards (4):** `Latest Month Volume (Bn)`, `Volume YoY %`, `Total Value (Lakh Cr)`, `Avg Ticket Size (Rs)`
- **Line chart:** x = `month_date`, y = `Total Volume (Bn)` + `Volume 3M Rolling Avg (Mn)`/1000
- **Clustered column chart:** x = `fiscal_year`, y = `Total Volume (Bn)`
- **Text box:** 3 bullet insights (copy them from the README)

### Page 2: Growth & Seasonality
- **Column chart:** `Volume YoY %` by `month_year`. Use conditional formatting → fx → field value → `YoY Colour`.
- **Matrix heatmap:** rows = `year`, columns = `month_name`, values = `Avg Daily Volume (Mn)`, with background colour scale. Comparing daily averages removes the short-month effect, and that's a good interview point.
- **Card:** `Volume CAGR %`
- **Line chart:** `Avg Ticket Size (Rs)` over time. Ticket size is falling as small payments grow.

### Page 3: App Market Share
- **100% stacked column:** x = `month_year`, legend = `dim_app[app_group]`, y = `App Volume Share %`
- **Bar chart:** `app` by `App Volume Share %` for the latest month, with a **constant line at 30%** (Analytics pane) labelled "Proposed NPCI cap"
- **Line chart:** `Top 2 Share %` and `Top 3 Share %` over time, constant line at 80%
- **Cards:** `HHI (lower bound)`, `Market Structure`, `Apps Above 30% Cap`

### Page 4: P2P vs P2M
- **Donut charts (2):** volume split and value split by `type`
- **Cards:** `P2M Volume Share %`, `P2M Value Share %`, `P2P Avg Ticket (Rs)`, `P2M Avg Ticket (Rs)`
- **Insight:** merchant payments are about 63% of transactions but only about 29% of the money. UPI has become the default for small everyday purchases.

### Page 5: Forecast
- **Line chart:** x = `month_date`, y = `Total Volume (Bn)`, `Forecast Volume (Bn)`, `Forecast Lower 80 (Bn)`, `Forecast Upper 80 (Bn)`. Make the lower and upper lines thin and light, and make the forecast line dashed.
- **Second line chart:** actual vs. `Backtest Volume (Bn)` for the last 6 months
- **Cards:** `Backtest MAPE %` and the Oct 2027 forecast value
- **Text box:** model name and method (copy from `data/model/run_log.json`)

### Page 6: Insights & Recommendations
Use text boxes and icons. Write 4 findings, each with a "so what". Use the README's insights as a starting point and rewrite them in your own words.

---

## Step 6: Interactivity, where you show advanced skills (10 min)
- **Drill-through:** create a hidden "Month Detail" page with `month_year` as the drill-through field, showing every KPI for that month. Right-click any month on another page to jump there.
- **Bookmarks + buttons:** on page 1, add a toggle between "Volume" and "Value" views.
- **Tooltip page:** a small page (Page size: Tooltip) showing MoM %, YoY % and Avg Ticket. Assign it to the main line chart.
- **Field parameter** (Modeling → New parameter → Fields): let the user switch the main chart between Volume, Value and Avg Ticket.

## Step 7: Automate the refresh
- **Local:** `refresh.bat` runs the pipeline. Schedule it monthly with **Windows Task Scheduler** (e.g. the 3rd of every month, after NPCI publishes), then open the report and click Refresh.
- **Online:** publish to Power BI Service, install the free **on-premises data gateway (personal mode)**, and set a scheduled refresh. Then Task Scheduler plus the gateway keep the dashboard updated with no manual steps.

## Step 8: Publish & show it off
1. Save as `UPI_Ecosystem_Analytics.pbix`.
2. Publish to Power BI Service. Use **Publish to web** only if you're fine with it being public. Otherwise, use screenshots and a screen recording.
3. Push this folder to GitHub (the `.pbix` included), add page screenshots to `docs/`, and update the README.
4. Record a 2-minute walkthrough and post it on LinkedIn with your 3 strongest insights.
