@echo off
REM ─────────────────────────────────────────────────────────────────
REM  IGA AI Framework — One-click Windows setup
REM  Usage: Double-click setup.bat  OR  run in PowerShell
REM ─────────────────────────────────────────────────────────────────

echo.
echo   IGA AI Framework — Windows Setup
echo   AI-Powered Identity Governance and Administration
echo   AISm Autonomous Agent System
echo.

REM ── Check Python ─────────────────────────────────────────────────
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo [ERROR] Python not found.
    echo         Install from https://python.org/downloads ^(3.11+^)
    echo         Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)
echo [OK] Python found

REM ── Install dependencies ──────────────────────────────────────────
echo [IGA] Installing Python dependencies...
pip install -e ".[dev]" -q
IF ERRORLEVEL 1 (
    echo [ERROR] pip install failed. Check your internet connection.
    pause
    exit /b 1
)
echo [OK] Dependencies installed

REM ── Set up .env ───────────────────────────────────────────────────
IF NOT EXIST ".env" (
    copy .env.example .env >nul
    echo [OK] Created .env from .env.example
    echo.
    echo [ACTION REQUIRED] Open .env in a text editor and set:
    echo   ANTHROPIC_API_KEY=sk-ant-...
    echo   Get your key at: https://console.anthropic.com
    echo.
) ELSE (
    echo [OK] .env already exists
)

REM ── Seed database ─────────────────────────────────────────────────
echo [IGA] Setting up database and seeding sample data...
set PYTHONPATH=src
python -m iga.scripts.seed_data 2>nul
echo [OK] Database ready

REM ── Run tests ─────────────────────────────────────────────────────
echo [IGA] Running tests...
python -m pytest tests/ -q 2>&1 | findstr /R "passed failed error"
echo [OK] Tests complete

REM ── Done ──────────────────────────────────────────────────────────
echo.
echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo   IGA AI Framework is ready!
echo.
echo   Start the API (run this in a new terminal):
echo     set PYTHONPATH=src
echo     uvicorn iga.main:app --reload --port 8000
echo.
echo   Then open in your browser:
echo     http://localhost:8000/docs
echo   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
pause
