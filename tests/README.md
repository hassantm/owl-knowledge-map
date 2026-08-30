# Tests

Tests for the vocabulary enrichment pipeline (Component 2) and co-occurrence computation (Component 3).

## Structure

| File | What it tests | DB required |
|---|---|---|
| `test_validation.py` | `validate_enrichment()` in `enrich.py` — all valid/invalid input combinations | No |
| `test_prompts.py` | `build_enrichment_prompt()` in `prompts.py` — prompt structure and content | No |
| `test_db.py` | DB query layer (`db.py`) — enrichment state machine transitions, CRUD | Yes |
| `test_cooccurrences.py` | Co-occurrence SQL correctness — joins, canonical ordering, weights | Yes |
| `test_migrations.py` | Schema after running migrations 001 and 002 — columns, constraints, defaults | Yes |

## Setup

Tests requiring a database use a dedicated `owl_test` database (never the live `owl` database).

```bash
# Create the test database (once)
createdb owl_test

# Install test dependencies
pip install pytest psycopg2-binary python-dotenv

# Run all tests
cd /home/htmadmin/dev/owl-knowledge-map
pytest tests/

# Run only the pure unit tests (no DB needed)
pytest tests/test_validation.py tests/test_prompts.py

# Run with verbose output
pytest tests/ -v

# Run a specific test class
pytest tests/test_cooccurrences.py::TestLessonCooccurrence -v
```

## Environment

By default, DB tests connect to `postgresql://htmadmin:dev@localhost:5432/owl_test`.

Override with:
```bash
export TEST_DATABASE_URL=postgresql://user:pass@host:5432/owl_test
pytest tests/
```

## Test Database Lifecycle

- `conftest.py` drops and recreates all tables in `owl_test` once per test session (session-scoped `db_session` fixture)
- Both migrations are applied automatically as part of session setup
- Each test that uses the `db` fixture starts with a clean (truncated) set of tables
- Migration tests (`test_migrations.py`) use `db_session` directly and inspect `information_schema`

## Notes

- `test_validation.py` and `test_prompts.py` will raise `ImportError` until `enrichment/enrich.py` and `enrichment/prompts.py` exist — this is the correct signal that the module hasn't been built yet
- The co-occurrence SQL in `test_cooccurrences.py` is copied verbatim from the spec; if the implementation diverges, update both
- Migration tests include idempotency checks — running migrations twice should not error
