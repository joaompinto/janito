# Testing guidelines: behavior over strings

453 exact-string pins were found in `tests/` (audit Sept 2026, 112 files).
String assertions duplicate the implementation: any reword breaks the suite
with zero logic bug. Prefer state and behavior assertions.

## Rules

1. **Assert state, not rendering.** `shell.provider`, `messages_history`,
   `get_config_value()`, `accounting.get_records()`, `TurnInfo` fields,
   mock calls, `table.row_count`, return values.
2. **One smoke assert per renderer.** A command that prints may assert
   `handle() is True` + `out.strip() != ""` (+ at most one stable header
   such as `"Current provider:"`). Do not pin every word, row, or sentence.
3. **Drive expectations from the source of truth.** If `/help` must list
   every command, loop over `get_registered_commands()` instead of
   hardcoding `"/tools"`, `"List all loaded tools"`, ... New commands then
   pass without editing the test.
4. **Error paths: assert kind + no side effects.** `handle() is True`,
   config/state unchanged, and at most `"error" in out.lower()`. Never pin
   the full `"Unknown provider 'x'"` sentence in every test — pin it once,
   if at all.
5. **Command matching/registration: use shared helpers.** `tests/conftest.py`
   provides `assert_command_registered(name)` and
   `assert_command_matching(handler_or_cls, name)`. Do not copy the
   `name == /x`, `/X`, whitespace, `/other is False` block into every file.
6. **Numbers over words for usage/accounting.** Assert
   `row["input_tokens"] == 180`, `u.turn_input == 60`, not `"In: 60/65.5k"`.

## Examples

Bad (duplicates copy):

```python
assert "Provider switched to 'deepseek'" in out
assert "Conversation history cleared (provider changed)." in out
```

Good (behavior):

```python
assert shell.provider == "deepseek"
assert shell.messages_history == [{"role": "system", "content": "sys"}]
assert get_config_value("provider") is None
```

Bad (pins every description):

```python
assert "List all loaded tools" in out
assert "Exit the chat session" in out
```

Good (registry-driven smoke):

```python
for cmd in get_registered_commands():
    assert cmd.name in out
```

## Parallel execution (pytest-xdist, default)

The suite runs multiprocess-parallel by default (`tox` uses
`pytest tests/ -n auto`; ~2x faster: 26s serial vs ~11-15s parallel
for 1502 tests). `pytest-xdist` is in the dev dependencies.

```bash
pytest tests/ -n auto -q        # default scheduling (test-level)
pytest tests/ -n auto --dist loadfile -q  # file-level (keeps each file on one worker)
pytest tests/ -q -n 0           # force serial (e.g. when debugging ordering)
```

- Multiprocess (`pytest-xdist`) isolates `tmp_path`,
  `monkeypatch.chdir`, FastAPI `TestClient` (port 0) per worker, and
  `tests/conftest.py::_isolate_process_global_state` snapshots/restores
  the remaining process globals (`running_privileges`, the tools
  registry, the config-dir override) around every test — workers run
  many files sequentially in one process, so without this a leaked
  global in one file breaks another depending on scheduling. Fixed
  Sept 2026: `test_patch_api_type_empty_clears_override` seeded a
  flat `"openai.api-type"` key nothing reads (real key is model-scoped
  `openai.models.gpt-6-luna.api-type`) and only passed on leftover
  state; `test_tools_endpoint_shape` saw a privilege-filtered registry
  leaked from another file.
- Multithreading (`pytest-run-parallel` / `pytest-parallel`) is NOT
  safe: `os.chdir` / `Path.cwd()`-dependent local mode (`./.janito`),
  the `janito.config_dir` module globals, and raw
  `tempfile.mkdtemp + set_config_dir` fixtures would race between
  threads. Do not enable thread-based parallelism.
- Keep tests isolated: use `tmp_path` + `monkeypatch.chdir` (not raw
  `os.chdir`), prefer `monkeypatch.setenv` over `os.environ[...]`,
  never write to fixed shared paths or ports, and reset module
  globals (config dir, registries) in fixtures so files stay
  order-independent. When adding a new process-global, extend the
  conftest snapshot.
