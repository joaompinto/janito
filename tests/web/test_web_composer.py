"""Run the composer's dependency-free JavaScript behavior suite from pytest."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed for frontend behavior tests")
def test_composer_behaviors():
    result = subprocess.run(
        [shutil.which("node"), "--test", str(Path(__file__).with_name("composer.test.cjs"))],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
