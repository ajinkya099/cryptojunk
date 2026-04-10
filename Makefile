.PHONY: dev test lint format migrate seed clean

# ── Development ───────────────────────────────────────────────────
dev:
	docker-compose up --build

dev-api:
	PYTHONPATH=src uvicorn iga.main:app --reload --host 0.0.0.0 --port 8000

dev-worker:
	PYTHONPATH=src celery -A iga.workers.tasks worker --loglevel=info

dev-scheduler:
	PYTHONPATH=src celery -A iga.workers.tasks beat --loglevel=info

# ── Database ──────────────────────────────────────────────────────
migrate:
	PYTHONPATH=src alembic upgrade head

migrate-new:
	PYTHONPATH=src alembic revision --autogenerate -m "$(msg)"

seed:
	PYTHONPATH=src python -m iga.scripts.seed_data

# ── Testing ───────────────────────────────────────────────────────
test:
	PYTHONPATH=src pytest tests/ -v --cov=iga --cov-report=term-missing

test-agents:
	PYTHONPATH=src pytest tests/test_agents/ -v

# ── Code Quality ──────────────────────────────────────────────────
lint:
	ruff check src/ tests/
	mypy src/

format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

# ── Cleanup ───────────────────────────────────────────────────────
clean:
	docker-compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -f iga_dev.db
