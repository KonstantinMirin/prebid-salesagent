# Development guide

Documentation for contributors to the Prebid Sales Agent codebase, maintained under Prebid.org.

## Get started

```bash
git clone https://github.com/prebid/salesagent.git
cd salesagent
make setup
```

See [Getting started](GETTING_STARTED.md) for prerequisites, manual setup, testing, and common operations.

## Documentation

This directory contains the following guides:

- **[Architecture principles](architecture-principles.md)** - The governing principles behind the layering: where code belongs and why
- **[Architecture](architecture.md)** - System design and component overview
- **[Request lifecycle](request-lifecycle.md)** - How a request travels from the wire to business logic (middleware, identity, compat layers)
- **[Patterns reference](patterns-reference.md)** - Canonical examples for every key pattern (start here for new contributors)
- **[Contributing](contributing.md)** - Development workflows, testing, and code style
- **[Structural guards](structural-guards.md)** - Automated architecture enforcement tests
- **[End-to-end testing](e2e-testing.md)** - The e2e stack, the two "e2e" suites, and how to run and debug them
- **[Troubleshooting](troubleshooting.md)** - Common development issues

## Key resources

- **[CLAUDE.md](../../CLAUDE.md)** - Detailed development patterns and conventions
- **[Tests](../../tests/)** - Test suite and examples
- **[Source](../../src/)** - Application source code

## Quick reference

### Run tests

```bash
./run_all_tests.sh ci     # Full suite: Docker + all 5 suites (DEFAULT)
./run_all_tests.sh quick  # No Docker: unit + integration + integration_v2
# Both modes produce JSON reports in test-results/<ddmmyy_HHmm>/

# Manual pytest
uv run pytest tests/unit/ -x
uv run pytest tests/integration/ -x
```

### Code quality

```bash
# Pre-commit hooks
pre-commit run --all-files

# Type checking
uv run mypy src/core/your_file.py --config-file=mypy.ini
```

### Database migrations

Migrations run automatically on startup. To run them manually:

```bash
# Inside Docker
docker compose exec adcp-server python scripts/ops/migrate.py

# Or locally with uv
uv run python scripts/ops/migrate.py

# Create a migration
uv run alembic revision -m "description"
```
