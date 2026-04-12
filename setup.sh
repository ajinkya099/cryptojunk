#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  IGA AI Framework — One-click local setup script
#  Usage: bash setup.sh
# ─────────────────────────────────────────────────────────────────
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[IGA]${NC} $1"; }
warning() { echo -e "${YELLOW}[IGA]${NC} $1"; }
error()   { echo -e "${RED}[IGA]${NC} $1"; exit 1; }

echo ""
echo "  ██╗ ██████╗  █████╗     ███████╗██████╗  █████╗ "
echo "  ██║██╔════╝ ██╔══██╗    ██╔════╝██╔══██╗██╔══██╗"
echo "  ██║██║  ███╗███████║    █████╗  ██████╔╝███████║"
echo "  ██║██║   ██║██╔══██║    ██╔══╝  ██╔══██╗██╔══██║"
echo "  ██║╚██████╔╝██║  ██║    ██║     ██║  ██║██║  ██║"
echo "  ╚═╝ ╚═════╝ ╚═╝  ╚═╝    ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝"
echo "  AI-Powered Identity Governance & Administration"
echo "  AISm — Autonomous Agent System"
echo ""

# ── Check Python ─────────────────────────────────────────────────
info "Checking Python version..."
if ! command -v python3 &>/dev/null; then
    error "Python 3 not found. Install from https://python.org/downloads (3.11+)"
fi
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]); then
    error "Python 3.11+ required. Found: $PY_VER"
fi
info "Python $PY_VER OK"

# ── Install dependencies ──────────────────────────────────────────
info "Installing Python dependencies..."
pip install -e ".[dev]" -q
info "Dependencies installed"

# ── Set up .env ───────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    info "Created .env from .env.example"
    warning ""
    warning "ACTION REQUIRED: Add your Anthropic API key to .env"
    warning "  Edit .env and set: ANTHROPIC_API_KEY=sk-ant-..."
    warning "  Get your key at: https://console.anthropic.com"
    warning ""
else
    info ".env already exists, skipping"
fi

# ── Seed database ─────────────────────────────────────────────────
info "Setting up development database and seeding sample data..."
PYTHONPATH=src python -m iga.scripts.seed_data 2>/dev/null
info "Database ready with sample identities, roles, and SoD policies"

# ── Run tests ─────────────────────────────────────────────────────
info "Running test suite..."
PYTHONPATH=src python -m pytest tests/ -q 2>&1 | tail -3
info "Tests passed"

# ── Done ──────────────────────────────────────────────────────────
echo ""
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  IGA AI Framework is ready!"
echo ""
echo "  Start the API:"
echo "    PYTHONPATH=src uvicorn iga.main:app --reload --port 8000"
echo ""
echo "  Or with Docker (full stack):"
echo "    docker-compose up --build"
echo ""
echo "  Then open:"
echo "    API docs  → http://localhost:8000/docs"
echo "    Health    → http://localhost:8000/health"
echo "    Agents    → http://localhost:8000/api/v1/agents/status"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
