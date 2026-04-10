# IGA AI Framework — Claude Memory (AISm System)

## Project Identity

**Project**: IGA (Identity Governance & Administration) powered by AI  
**Codename**: AISm — AI Self-Management System  
**Repo**: ajinkya099/cryptojunk  
**Branch**: claude/iga-ai-framework-2bUVS  
**Started**: 2026-04-10  

## What is AISm?

AISm (AI Self-Management) is the autonomous AI agent layer that runs the IGA system
24/7 without human intervention. It consists of:

- **Lifecycle Agent** — Handles Joiner/Mover/Leaver identity events automatically
- **Certification Agent** — Runs access review campaigns, makes AI-driven decisions
- **Role Mining Agent** — Discovers roles from access patterns, suggests optimizations
- **SoD Detector Agent** — Detects Segregation of Duties violations, auto-remediates
- **Orchestrator** — Master agent that coordinates all sub-agents, schedules work

## Architecture Decisions

- **Language**: Python 3.11+
- **API Framework**: FastAPI (async, high-performance)
- **AI Engine**: Anthropic Claude SDK (`claude-sonnet-4-6`)
- **Database**: SQLAlchemy 2.0 + PostgreSQL (SQLite for dev/test)
- **Task Queue**: Celery + Redis (for async 24/7 agent execution)
- **Containerization**: Docker + docker-compose

## IGA Domain Coverage

1. **User Lifecycle Management** — Joiner/Mover/Leaver (JML) workflows
2. **Access Certification** — Automated access review campaigns
3. **Role Management** — RBAC/ABAC, role mining, role engineering
4. **Privileged Access & SoD** — PAM governance, conflict detection

## Project Structure

```
src/iga/
├── main.py              # FastAPI application entry point
├── config.py            # Settings & environment config
├── database.py          # DB engine, session management
├── models/              # SQLAlchemy ORM models
│   ├── identity.py      # User, Account, Application
│   ├── role.py          # Role, Permission, Entitlement
│   ├── access.py        # AccessAssignment, AccessRequest
│   └── policy.py        # SoDPolicy, CertificationCampaign
├── agents/              # AISm — Autonomous AI agents
│   ├── base.py          # BaseAgent with Claude SDK integration
│   ├── lifecycle.py     # LifecycleAgent (JML automation)
│   ├── certification.py # CertificationAgent (access reviews)
│   ├── role_miner.py    # RoleMinerAgent (role discovery)
│   ├── sod_detector.py  # SoDDetectorAgent (conflict detection)
│   └── orchestrator.py  # AgentOrchestrator (master scheduler)
├── api/                 # REST API routes
│   ├── identities.py
│   ├── roles.py
│   ├── access.py
│   ├── certifications.py
│   └── agents.py        # Agent status & trigger endpoints
├── services/            # Business logic layer
│   ├── lifecycle.py
│   ├── certification.py
│   ├── role_management.py
│   └── sod.py
└── workers/             # Celery async task workers
    └── tasks.py
```

## Autonomous Operation (24/7)

The AISm system is designed to run without human input:

- Celery Beat scheduler triggers agents on cron schedules
- Agents use Claude API to make intelligent decisions
- Decisions are logged with reasoning for audit
- Humans can review/override but are not required
- Self-healing: agents detect anomalies and auto-remediate

## Key Conventions

- All agent decisions include an AI reasoning trace (stored in DB)
- All access changes are audited with `changed_by`, `reason`, `timestamp`
- FastAPI endpoints use async/await throughout
- Pydantic v2 for request/response validation
- Database migrations via Alembic
- Tests in `tests/` using pytest + pytest-asyncio

## Environment Variables

```
ANTHROPIC_API_KEY=       # Claude API key (required for agents)
DATABASE_URL=            # PostgreSQL connection string
REDIS_URL=               # Redis for Celery broker
SECRET_KEY=              # JWT signing key
ENVIRONMENT=             # development | staging | production
```

## Agent Schedule (default)

| Agent              | Schedule       | Purpose                          |
|--------------------|----------------|----------------------------------|
| LifecycleAgent     | Every 5 min    | Process pending JML events       |
| CertificationAgent | Daily 2am      | Run certification campaigns       |
| RoleMinerAgent     | Weekly Sunday  | Discover new role patterns        |
| SoDDetectorAgent   | Every 30 min   | Scan for SoD violations           |
| Orchestrator       | Continuous     | Coordinate agents, handle alerts  |

## Development Notes

- Always run `pytest` before committing
- Use `make dev` to start local stack (FastAPI + Celery + Redis + DB)
- Agent logs go to `logs/agents/` with structured JSON format
- Keep agent prompts in `src/iga/agents/prompts/` for easy tuning
