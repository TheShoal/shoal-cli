## ADDED Requirements

### Requirement: CI SHALL use official GitHub Action for uv installation
The CI workflow MUST use `astral-sh/setup-uv@v5` instead of `curl | sh` to install uv, eliminating the remote code execution risk from piping untrusted scripts.

#### Scenario: CI installs uv
- **WHEN** the CI workflow runs the uv installation step
- **THEN** it uses `astral-sh/setup-uv@v5` GitHub Action instead of `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Requirement: CI SHALL validate fish template syntax
The CI workflow MUST include a step that runs `fish -n` (no-execute, syntax check only) on all `.fish` template files to catch syntax errors before merge.

#### Scenario: All fish templates have valid syntax
- **WHEN** the CI runs the fish syntax check step
- **THEN** `fish -n` succeeds for all `.fish` files in `src/shoal/integrations/fish/templates/`

#### Scenario: A fish template has a syntax error
- **WHEN** a fish template contains a syntax error
- **THEN** `fish -n` fails and the CI step reports the error

### Requirement: installer.py SHALL not contain unused imports
The `installer.py` module MUST NOT import `Panel` from `rich.console` or `Table` from `rich.table` since they are not used.

#### Scenario: installer.py imports are clean
- **WHEN** `ruff check` or similar linter runs on `installer.py`
- **THEN** no unused import warnings are reported for `Panel` or `Table`
