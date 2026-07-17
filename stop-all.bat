@echo off
REM Stop every service (data volumes are kept).
cd /d "%~dp0"
docker compose --profile monitoring --profile mlops --profile ui --profile tracing down
echo All services stopped. Data volumes