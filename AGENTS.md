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
  `tests/conftest.py`. Pass `status=` when the code under test checks the
  response status.

### Shared constants and fixtures

- A value used by more than one test file belongs in `tests/const.py`, for
  example `TEST_SERIAL_1` / `TEST_SERIAL_2` / `TEST_SERIAL_3`,
  `TEST_SERIAL_GROUP`, `TEST_CUSTOMER_ID`, `TEST_DEVICE_TYPE` and
  `TEST_ACCESS_TOKEN`. Use these rather than repeating their literal values
  (such as `"A1B2C3"` or `"CUSTOMER_ID"`) or defining local copies. Values
  used only in one file stay as constants at the top of that file.
- A fixture used by more than one test file belongs in `tests/conftest.py`.
  Check there before writing a new one: for example `make_device`,
  `speaker_group`, `send_message`, `mock_json_response`, `logged_in` and
  `debug_logs`. Don't redefine a local copy of a shared fixture.
- Use `logged_in` for a logged in API (it also stores an access token and
  stubs the token refresh). Use it as `@pytest.mark.usefixtures("logged_in")`
  when the test does not need its value. Tests that check the logged out
  behaviour simply don't request it.
- A file-specific fixture can build on a shared one by requesting it, adding
  only its own setup.
- Don't add a fixture that only wraps a one-line call. Call
  `make_device(TEST_SERIAL_1)` directly rather than a `device` fixture, and use
  its keyword options (such as `media_player_supported=True`) rather than
  `dataclasses.replace`.

### Fixture files

- Put HTML pages in files under `tests/fixtures/<area>/` (for example
  `tests/fixtures/login/mfa.html`) rather than in inline strings, and load them
  with a small helper in the test module.
- Start each HTML fixture with a comment naming the page it represents (its
  URL or the step of the flow), and whether it was trimmed from a real
  response or is a minimal stand-in. Never invent a "real" origin.
- When a test needs to vary a value in an HTML fixture, use a `{placeholder}`
  filled with `str.format`, and keep any other braces out of the file.
- Keep a short snippet inline when the snippet itself is the test case, for
  example a page with an empty or missing element in a parametrized error
  test.
- Large, realistic JSON API responses can go in `.json` files in the same
  way (as in `tests/fixtures/set_feature/`). Keep small builder helpers that
  vary a field or two per test inline. JSON has no comments, so note where a
  response came from in the test that loads it.

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
- Put module constants, helper functions and fixtures at the top of the file,
  before the first test, rather than between tests.
- Tests must not depend on the machine they run on. For example, when freezing
  the time, make the local timezone UTC too, so the tests pass outside UTC.

### Style

- Name fake functions after the method they replace, with no leading
  underscore.
- Write comments as full sentences, capitalised and ending in a full stop.
