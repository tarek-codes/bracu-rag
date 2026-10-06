# Windows PowerShell script to setup PostgreSQL with pgvector for BRAC RAG
[CmdletBinding()]
param(
    [string]$PostgresPassword = "postgres",
    [string]$DatabaseName = "bracu_rag",
    [int]$Port = 5432
)

$ErrorActionPreference = "Stop"

Write-Host "=== Setting up PostgreSQL with pgvector on Windows ===" -ForegroundColor Cyan

# Check if Docker is available
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue

if ($dockerCmd) {
    Write-Host "[+] Docker detected. Checking Docker daemon..." -ForegroundColor Green
    
    # Check if docker daemon is responding
    $daemonOk = $false
    try {
        docker info 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { $daemonOk = $true }
    } catch {
        $daemonOk = $false
    }

    if (-not $daemonOk) {
        Write-Host "[*] Docker daemon is not running. Attempting to start Docker Desktop Service..." -ForegroundColor Yellow
        $dockerService = Get-Service com.docker.service -ErrorAction SilentlyContinue
        if ($dockerService -and $dockerService.Status -ne "Running") {
            try {
                Start-Service com.docker.service
                Write-Host "[+] Docker service started." -ForegroundColor Green
            } catch {
                Write-Warning "Could not start com.docker.service automatically: $_"
            }
        }
        
        $desktopExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        if (Test-Path $desktopExe) {
            Write-Host "[*] Launching Docker Desktop..." -ForegroundColor Yellow
            Start-Process $desktopExe
            Write-Host "[*] Waiting for Docker daemon to become responsive (up to 45s)..." -ForegroundColor Yellow
            $attempts = 0
            while ($attempts -lt 15) {
                Start-Sleep -Seconds 3
                try {
                    docker info 2>&1 | Out-Null
                    if ($LASTEXITCODE -eq 0) {
                        $daemonOk = $true
                        break
                    }
                } catch {}
                $attempts++
            }
        }
    }

    if ($daemonOk) {
        Write-Host "[+] Docker is ready. Managing pgvector container..." -ForegroundColor Green
        
        # Check if container already exists
        $existingContainer = docker ps -a --filter "name=bracu-rag-postgres" --format "{{.Names}}"
        if ($existingContainer -eq "bracu-rag-postgres") {
            $isRunning = docker ps --filter "name=bracu-rag-postgres" --format "{{.Names}}"
            if ($isRunning -ne "bracu-rag-postgres") {
                Write-Host "[*] Starting existing bracu-rag-postgres container..." -ForegroundColor Yellow
                docker start bracu-rag-postgres | Out-Null
            } else {
                Write-Host "[+] Container bracu-rag-postgres is already running." -ForegroundColor Green
            }
        } else {
            Write-Host "[*] Creating new container bracu-rag-postgres (pgvector/pgvector:pg17)..." -ForegroundColor Yellow
            docker run -d `
                --name bracu-rag-postgres `
                -e POSTGRES_USER=postgres `
                -e POSTGRES_PASSWORD=$PostgresPassword `
                -e POSTGRES_DB=$DatabaseName `
                -p "${Port}:5432" `
                -v bracu_rag_pgdata:/var/lib/postgresql/data `
                pgvector/pgvector:pg17
        }

        # Wait for PostgreSQL to be ready
        Write-Host "[*] Waiting for PostgreSQL to be ready..." -ForegroundColor Yellow
        Start-Sleep -Seconds 3

        # Ensure vector extension is installed
        Write-Host "[*] Enabling pgvector extension..." -ForegroundColor Yellow
        docker exec bracu-rag-postgres psql -U postgres -d $DatabaseName -c "CREATE EXTENSION IF NOT EXISTS vector;"

        # Verify
        $extVersion = docker exec bracu-rag-postgres psql -U postgres -d $DatabaseName -t -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
        Write-Host "[+] pgvector version: $($extVersion.Trim())" -ForegroundColor Green
        Write-Host "=== PostgreSQL with pgvector is ready on localhost:$Port! ===" -ForegroundColor Cyan
        exit 0
    }
}

# If Docker is not available or daemon failed, check native psql
$psqlCmd = Get-Command psql -ErrorAction SilentlyContinue
if ($psqlCmd) {
    Write-Host "[*] Native PostgreSQL client detected. Configuring local PostgreSQL..." -ForegroundColor Yellow
    psql -U postgres -c "CREATE DATABASE $DatabaseName;" 2>$null
    psql -U postgres -d $DatabaseName -c "CREATE EXTENSION IF NOT EXISTS vector;"
    Write-Host "[+] Local PostgreSQL configured." -ForegroundColor Green
    exit 0
}

Write-Error "Neither Docker nor psql could be reached. Please ensure Docker Desktop or PostgreSQL with pgvector is installed and running."
