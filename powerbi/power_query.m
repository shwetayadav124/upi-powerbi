// =====================================================================
// Power Query (M) - loads every table from data/model/
// 1. Home > Transform data > Manage Parameters > New Parameter
//      Name: DataFolder   Type: Text
//      Current value: the full path to your data\model\ folder, ending in "\"
//      e.g.  C:\Projects\upi-powerbi\data\model\
// 2. Home > New Source > Blank Query > Advanced Editor, paste ONE block,
//    rename the query to the name in the comment above it. Repeat for each.
// After that, running the pipeline + pressing Refresh updates everything.
// =====================================================================

// ---- Query name: fnLoadCsv  (a reusable function) ----
(fileName as text) as table =>
let
    Source   = Csv.Document(File.Contents(DataFolder & fileName),
                 [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true])
in
    Promoted

// ---- Query name: dim_date ----
let
    Source = fnLoadCsv("dim_date.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"month_date", type date}, {"date_key", Int64.Type}, {"year", Int64.Type},
        {"month_num", Int64.Type}, {"month_name", type text}, {"month_year", type text},
        {"fiscal_year", type text}, {"fiscal_month_num", Int64.Type},
        {"fiscal_quarter", type text}, {"is_festive_season", type text}})
in
    Typed

// ---- Query name: dim_app ----
let
    Source = fnLoadCsv("dim_app.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"app_id", Int64.Type}, {"app", type text}, {"parent", type text}, {"app_group", type text}})
in
    Typed

// ---- Query name: fact_upi_monthly ----
let
    Source = fnLoadCsv("fact_upi_monthly.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"date_key", Int64.Type}, {"banks_live", Int64.Type}, {"volume_mn", type number},
        {"value_cr", type number}, {"days_in_month", Int64.Type},
        {"avg_daily_volume_mn", type number}, {"avg_ticket_rs", type number}, {"source", type text}},
        "en-US")
in
    Typed

// ---- Query name: fact_forecast ----
let
    Source = fnLoadCsv("fact_forecast.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"date_key", Int64.Type}, {"type", type text}, {"forecast_volume_mn", type number},
        {"lower_80_mn", type number}, {"upper_80_mn", type number}}, "en-US")
in
    Typed

// ---- Query name: fact_app_share ----
let
    Source = fnLoadCsv("fact_app_share.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"date_key", Int64.Type}, {"app_id", Int64.Type}, {"volume_share_pct", type number},
        {"value_share_pct", type number}, {"source", type text}}, "en-US")
in
    Typed

// ---- Query name: fact_concentration ----
let
    Source = fnLoadCsv("fact_concentration.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"date_key", Int64.Type}, {"top2_share_pct", type number}, {"top3_share_pct", type number},
        {"hhi_lower_bound", type number}, {"apps_above_30pct_cap", Int64.Type}}, "en-US")
in
    Typed

// ---- Query name: fact_p2p_p2m ----
let
    Source = fnLoadCsv("fact_p2p_p2m.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"date_key", Int64.Type}, {"type", type text}, {"volume_mn", type number},
        {"value_cr", type number}, {"source", type text}}, "en-US")
in
    Typed
