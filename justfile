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

# Deploy firmware to PocketPD device via mpremote
deploy:
    mpremote fs -r cp app/ :app/
    mpremote fs -r cp drivers/ :drivers/
    mpremote fs -r cp fonts/ :fonts/
    mpremote fs mkdir :lib
    mpremote fs mkdir :lib/nano_gui
    mpremote fs cp lib/nano_gui/__init__.py :lib/nano_gui/__init__.py
    mpremote fs cp lib/nano_gui/writer.py :lib/nano_gui/writer.py
    mpremote fs cp lib/ssd1306.py :lib/ssd1306.py
    mpremote fs cp boot.py main.py config.py :
    mpremote reset

# Generate state machine PNG from Mermaid definition
diagram:
    docker run --rm -u "$(id -u):$(id -g)" -v $(pwd)/docs:/data minlag/mermaid-cli -i state_machine.mmd -o state_machine.png -t dark -b '#1a1a2e'
