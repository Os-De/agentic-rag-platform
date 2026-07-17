@echo off
REM Start the FULL platform (all profiles) and open every dashboard.
cd /d "%~dp0"

if not exist .env (
    copy .env.example .env
    echo Created .env from .env.example — edit your secrets later.
)

echo Starting all services (first build can take several minutes)...
docker compose --profile monitoring --profile mlops --profile ui --profile tracing up -d --build
if errorlevel 1 (
    echo.
    echo Docker failed — is Docker Desktop running?
    pause
    exit /b 1
)

echo Waiting 20s for services to boot...
timeout /t 20 /nobreak >nul

start "" http://localhost:8000/docs
start "" http://localhost:8501
start "" http://localhost:3000
start "" http://localhost:9090
start "" http://localhost:6333/dashboard
start "" http://localhost:5000
start "" http://localhost:6006
start "" http://localhost:16686

echo.
echo   API docs    http://localhost:8000/docs
echo   Chat UI     http://localhost:8501
echo   Grafana     http://localhost:3000   (admin / admin)
echo   Prometheus  http://localhost:9090
echo   Qdrant      http://localhost:6333/dashboard
echo   MLflow      http://localhost:5000
echo   Phoenix     http://localhost:6006   (LLM traces, TRACING_BACKEND=phoenix)
echo   Jaeger      http://localhost:16686  (LLM traces, TRACING_BACKEND=traceloop)
echo.
echo If a page does not load yet, wait a moment and refresh (first build is slow).
pause
