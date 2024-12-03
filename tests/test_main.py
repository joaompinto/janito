from typer.testing import CliRunner
from pathlib import Path
from janito.__main__ import main
from unittest.mock import patch
import json

runner = CliRunner()

def test_hello(tmp_path: Path):
    result = runner.invoke(main, [str(tmp_path), "add a new function"])
    assert result.exit_code == 0

def test_raw_output(tmp_path: Path):
    result = runner.invoke(main, [str(tmp_path), "add a new function", "--raw"])
    assert result.exit_code == 0
    assert "Request Analysis" not in result.stdout

def test_option_selection(tmp_path: Path):
    with patch('builtins.input', return_value='1'):
        result = runner.invoke(main, [str(tmp_path), "add a new function"])
        assert result.exit_code == 0
        assert "Detailed implementation" in result.stdout

def test_invalid_option_selection(tmp_path: Path):
    with patch('builtins.input', return_value='999'):
        result = runner.invoke(main, [str(tmp_path), "add a new function"])
        assert result.exit_code == 0
        assert "Error: Option 999 not found" in result.stdout

def test_play_option(tmp_path: Path):
    # Create a test prompt file
    prompt_file = tmp_path / "test_prompt.txt"
    prompt_file.write_text("Test prompt content")
    
    result = runner.invoke(main, [".", "dummy", "--play", str(prompt_file)])
    assert result.exit_code == 0

def test_response_file_replay(tmp_path: Path):
    # Create a test response file
    response = {
        "filename": "test.py",
        "content": "print('hello world')"
    }
    response_file = tmp_path / "response_test.txt"
    response_file.write_text(json.dumps(response))
    
    result = runner.invoke(main, [str(tmp_path), "dummy", "--play", str(response_file)])
    assert result.exit_code == 0
    assert (tmp_path / "test.py").exists()
    assert (tmp_path / "test.py").read_text() == "print('hello world')"

