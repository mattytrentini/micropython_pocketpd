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

# Run PocketPD simulation with browser UI
sim:
    docker run --rm -p 8080:8080 -v $(pwd):/code -w /code micropython/unix micropython sim/main_sim.py

# Generate state machine PNG from Mermaid definition
diagram:
    docker run --rm -u "$(id -u):$(id -g)" -v $(pwd)/docs:/data minlag/mermaid-cli -i state_machine.mmd -o state_machine.png -t dark -b '#1a1a2e'
