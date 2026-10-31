# AEGIS-ALPR Police Stolen Vehicle Surveillance System Launcher
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host " AEGIS-ALPR // POLICE STOLEN VEHICLE SURVEILLANCE & ALERT SYSTEM" -ForegroundColor Yellow
Write-Host " Automatic Number Plate Recognition & Real-Time Hotlist Interceptor" -ForegroundColor White
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Starting Web Surveillance Command Center at http://127.0.0.1:5000" -ForegroundColor Green
Write-Host ""

$pythonPath = "$env:LOCALAPPDATA\Python\bin\python.exe"
if (Test-Path $pythonPath) {
    & $pythonPath app.py
} else {
    py app.py
}

