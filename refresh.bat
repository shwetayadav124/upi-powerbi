@echo off
REM Refreshes data/model/ for Power BI and points the report at this folder.
REM Run with Power BI closed, then open UPI_Ecosystem_Analytics.pbip and click Refresh.
cd /d "%~dp0"
python pipeline\run_pipeline.py
if errorlevel 1 (echo Pipeline FAILED & exit /b 1)
echo Done. Open UPI_Ecosystem_Analytics.pbip and click Refresh.
