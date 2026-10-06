# PowerShell launcher for BRAC University RAG on Windows
[CmdletBinding()]
param()

$root = $PSScriptRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Starting BRAC University RAG Services on Windows " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Ensure PostgreSQL is up
Write-Host "`n[1/3] Ensuring PostgreSQL container is running..." -ForegroundColor Yellow
powershell -ExecutionPolicy Bypass -File "$root\scripts\setup_postgres.ps1"

# 2. Start Backend
Write-Host "`n[2/3] Launching FastAPI Backend (port 8000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

# 3. Start Frontend
Write-Host "`n[3/3] Launching Next.js Frontend (port 3000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; bun run dev"

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host " All services launched successfully!" -ForegroundColor Green
Write-Host " Frontend:        http://localhost:3000" -ForegroundColor Green
Write-Host " Backend API:     http://127.0.0.1:8000" -ForegroundColor Green
Write-Host " Swagger Docs:    http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host " Health Check:    http://127.0.0.1:8000/health" -ForegroundColor Green
Write-Host " Default Admin:   admin@bracu.ac.bd / AdminPassword123!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
