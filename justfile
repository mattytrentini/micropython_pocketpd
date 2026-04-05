# MicroPython PocketPD - Task Runner

# Run unit tests in MicroPython Unix Docker container
test *args:
    docker run --rm -v $(pwd):/code -w /code micropython/unix micropython tests/run_tests.py {{args}}

# Run ruff linter
lint:
    ruff check .

# Run ruff formatter
format:
    ruff format .

# Run ty type checker (exclude lib/ and tests/ — MicroPython-only imports)
typecheck:
    ty check --exclude 'lib/' --exclude 'tests/' --exclude 'boot.py' --exclude 'main.py'

# Run all checks (format check + lint + typecheck + tests)
check: lint typecheck test

# Format check (no modification)
format-check:
    ruff format --check .
