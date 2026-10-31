@echo off
title AEGIS-ALPR Police Stolen Vehicle Surveillance System
color 0B
echo =====================================================================
echo  AEGIS-ALPR // POLICE STOLEN VEHICLE SURVEILLANCE & ALERT SYSTEM
echo  Automatic Number Plate Recognition & Real-Time Hotlist Interceptor
echo =====================================================================
echo.
echo Launching surveillance command center server on port 5000...
echo Access in browser: http://127.0.0.1:5000
echo.

"%LOCALAPPDATA%\Python\bin\python.exe" app.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Trying fallback py launcher...
    py app.py
)
pause

