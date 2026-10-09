@echo off
title 啟動 Beta 組合監控工具
echo 正在啟動 Streamlit 網頁服務...
cd /d "%~dp0"
streamlit run app.py
pause