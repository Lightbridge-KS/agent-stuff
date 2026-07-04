# agent-stuff — task runner
# Python machinery runs via `uv` (self-contained PEP 723 scripts).

# List available recipes
default:
    @just --list

# Validate the SKILL.md + manifest + scripts/hooks contracts
validate:
    uv run bin/validate.py

# List packageable skills
list:
    uv run bin/package.py --list

# Package skills into dist/, validating first (e.g. `just package dcmtk`, `--domain radiology`, `--skill`)
package *args: validate
    uv run bin/package.py {{args}}

# Install skills into agents. Pass flags, e.g. `just install --claude`.
install *args:
    uv run bin/install.py {{args}}

# Run the full test suite
test:
    uv run tests/test_install.py
    uv run tests/test_hooks.py
    uv run tests/test_package.py

# Remove build artifacts
clean:
    rm -rf dist
