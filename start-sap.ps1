# Double-click this (or run it in PowerShell) to always start the app
# correctly wired to the live SAP BTP Core Banking service.
#
# Usage from PowerShell:
#   .\start-sap.ps1
#
# If double-clicking doesn't work (Windows sometimes opens .ps1 in Notepad
# instead of running it), right-click the file -> "Run with PowerShell".

$env:CORE_BANKING_SAP_URL = "https://core-banking-service.cfapps.ap21.hana.ondemand.com"

Write-Host ""
Write-Host "CORE_BANKING_SAP_URL set to: $env:CORE_BANKING_SAP_URL" -ForegroundColor Green
Write-Host "Starting server on http://localhost:8000 ..." -ForegroundColor Green
Write-Host "(Check the Execution Trace panel shows CORE_BANKING_SAP after your first query)" -ForegroundColor Yellow
Write-Host ""

.\venv\Scripts\python.exe -m uvicorn api.main:app --port 8000
