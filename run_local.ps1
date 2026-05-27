# Run Marcelo FastAPI app locally on Windows (DB+Redis stay in Docker)
# Use this instead of Docker when you need dev tools (PyCharm, shell, filesystem)

$env:MARCELO_DATABASE_URL = "postgresql+psycopg://marcelo:marcelo@localhost:5433/marcelo"

# Load remaining keys from .env
Get-Content ".env" | ForEach-Object {
    if ($_ -match "^([^#][^=]+)=(.*)$") {
        $key = $matches[1].Trim()
        $val = $matches[2].Trim()
        if (-not $key.StartsWith("MARCELO_DATABASE_URL")) {
            Set-Item -Path "env:$key" -Value $val
        }
    }
}

$env:GROQ_API_KEY = $env:MARCELO_GROQ_API_KEY

Write-Host "Starting Marcelo locally on http://localhost:8000" -ForegroundColor Cyan
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
