@echo off
rem Lance Cours IA sur Windows (necessite uv : https://docs.astral.sh/uv/)
cd /d "%~dp0"
set UV_PROJECT_ENVIRONMENT=%LOCALAPPDATA%\cours-ia\.venv
uv sync --quiet && uv run cours-ia
pause
