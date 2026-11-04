# Agent Instructions

Guidance for AI coding agents (and humans) working in this repository. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the development setup.

## Tooling

- Dependencies are managed with `uv`. Run tests with `uv run pytest`.
- Lint, format and type check with `uv run prek run --files <files>` (or
  `--all-files`). This runs ruff, mypy and the other hooks CI runs.

## Test conventions

These come from review feedback. Follow them for any new or changed test.

### No suppressions

- Don't use `# type: ignore` in tests. Patch methods with
  `monkeypatch.setattr` instead of assigning mocks onto them, and keep a
  reference to the mock (for example from a fixture that returns it) so you can
  assert on it without `attr-defined` ignores.
- Don't suppress ruff rules such as `PLR2004` with `# noqa`. For example, use
  `assert mock.await_args_list == [call(), call()]` rather than
  `assert mock.await_count == 2`.
- Ruff caps tests at 5 arguments (`PLR0913`/`PLR0917`). Get under it by moving
  shared setup into a fixture or combining parameters, not by suppressing the
  rule.
- Don't use private imports such as `unittest.mock._Call`, even just for type
  hints. Use `list[Any]` or similar instead.

### Mocking

- Use `monkeypatch.setattr`, not `patch.object`.
- Use `AsyncMock` (with `side_effect` when it must do something) and
  `assert_awaited_once()` / `assert_not_awaited()` rather than `nonlocal` call
  counters.
- To stub an HTTP JSON response, use the `mock_json_response` fixture in
  `tests/conftest.py`.
- Use `TEST_SERIAL_1` / `TEST_SERIAL_2` from `tests/const.py` rather than
  local serial constants.

### Structure

- Put `@pytest.mark.anyio` on each async test, not a module-level
  `pytestmark`.
- Use `@pytest.mark.parametrize` where tests differ only in their inputs and
  expected outputs, rather than writing near-duplicate test functions. Give
  each case a `pytest.param(..., id="kebab-case")`, and put
  `@pytest.mark.anyio` above `@pytest.mark.parametrize`.
- No `if` statements in tests. Don't branch on a parameter or result inside a
  test body. List the expected values explicitly (for example an
  `expected_calls` parameter compared with `==`), or split the test.

### Style

- Name fake functions after the method they replace, with no leading
  underscore.
- Write comments as full sentences, capitalised and ending in a full stop.
