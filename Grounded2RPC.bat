@echo off
rem Lance la Rich Presence dans une console (Ctrl+C pour arreter).
cd /d "%~dp0"
python -m grounded2_rpc %*
if errorlevel 1 pause
