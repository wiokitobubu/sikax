@echo off
rem Fabrique la distribution Windows de Sikax (voir build_windows.ps1 pour les options).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1" %*
if errorlevel 1 pause
