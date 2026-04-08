# MicroPython PocketPD

MicroPython port of the [PocketPD](https://github.com/CentyLab/PocketPD) USB-C PD bench power supply firmware.

## Commands

- `just test` — run unit tests in MicroPython Unix Docker container
- `just lint` — ruff linter
- `just format` — ruff formatter
- `just typecheck` — ty type checker
- `just check` — all checks (lint + typecheck + test)
- `just sim` — run web simulator (Docker, port 8080)
- `just diagram` — regenerate state machine PNG from Mermaid

## Architecture

Drivers use `machine` module directly. In tests, `mock_machine.register_as_machine()` replaces
`machine` transparently. Tests run on MicroPython Unix port via Docker (`micropython/unix`).

## Conventions

- Code style: ruff (line-length=99)
- Type hints: checked by ty
- Target: MicroPython on RP2040 (Pico), tested on MicroPython Unix port
- Hardware variant: HW1.1+ only (5mΩ shunt)
- No CPython dependencies in driver/app code — only MicroPython stdlib
