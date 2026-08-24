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
    uv run tests/test_lightbridge.py
    uv run tests/test_lb_graph.py
    uv run tests/test_lb_keys.py
    uv run tests/test_hooks.py
    uv run tests/test_repo_links.py
    uv run tests/test_island_path.py
    uv run tests/test_handoff_hook.py
    uv run tests/test_package.py
    uv run tests/test_research_kit.py
    uv run tests/test_imagegen.py
    uv run tests/test_plan_store.py
    uv run tests/test_notebook_tools.py
    uv run tests/test_codex_plugin.py
    uv run tests/test_skill_vendor.py
    uv run tests/test_skill_health.py
    uv run tests/test_skill_health_telegram_notify.py
    uv run tests/test_validate.py

# Remove build artifacts
clean:
    rm -rf dist
