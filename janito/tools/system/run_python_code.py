#!/usr/bin/env python3
"""
Run Python Code Tool - A class-based tool for executing Python code and scripts.

This tool demonstrates how to use the base tool class with progress reporting
for system command execution.

Note: This tool requires the progress reporting system from the tooling package.
For direct execution, use: python -m janito.tools.system.run_python_code [args]
For AI function calling, use through the tool registry (tooling.tools_registry).

WARNING: This tool executes system commands and should be used with caution.
Only execute trusted code and be aware of security implications.
"""

import json
import os
import subprocess
import sys
from typing import Any

from ...tooling import BaseTool, format_duration_ms, norm_path
from ...tooling.decorator import tool
from ._streaming import lines_to_text, preview_lines, stream_execute


@tool(permissions="x")
class RunPythonCode(BaseTool):
    """
    Tool for executing Python code and scripts.

    This tool runs Python code and returns the output, errors, and exit code.
    It supports both single commands and multi-line scripts.

    Security Notes:
    - Only execute trusted Python code
    - Be cautious with scripts that modify system state
    - Consider the security implications of arbitrary code execution
    """

    system_prompt_hint = (
        "Prefer Python libraries over manual parsing when reading binary "
        "documents: python-docx for .docx, openpyxl or pandas.read_excel for "
        ".xlsx/.xlsm, xlrd for legacy .xls, pdfplumber or pypdf for PDFs. "
        "Check a library is installed before importing it "
        "(importlib.util.find_spec('openpyxl')) and report which one is "
        "missing instead of failing silently."
    )

    def run(
        self,
        code: str,
        working_directory: str | None = None,
        timeout: int | None = 60,
        capture_output: bool = True,
        capture_errors: bool = True,
        python_executable: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute Python code and return results.

        Args:
            code (str): Python code to execute (can be single statement or multi-line script)
            working_directory (Optional[str]): Working directory for execution (default: current directory)
            timeout (Optional[int]): Maximum execution time in seconds (default: 60, None for no limit)
            capture_output (bool): Whether to capture standard output (default: True)
            capture_errors (bool): Whether to capture standard error (default: True)
            python_executable (Optional[str]): Path to Python executable (default: current Python interpreter)

        Returns:
            Dict[str, Any]: A dictionary containing:
                - 'success': bool indicating if execution succeeded (exit code 0)
                - 'exit_code': integer exit code from Python
                - 'stdout': captured standard output (if capture_output=True)
                - 'stderr': captured standard error (if capture_errors=True)
                - 'command': the Python command that was executed
                - 'working_directory': the working directory used
                - 'execution_time_ms': execution time in milliseconds
                - 'error': error message if execution failed (only present if success=False)

        Example:
            >>> tool = RunPythonCode()
            >>> result = tool.run(code="print('Hello, World!')\\nimport sys\\nprint(f'Python version: {sys.version}')")
            >>> print(result['stdout'])
        """
        import time

        start_time = time.time()

        try:
            abs_working_dir = self._resolve_working_dir(working_directory)
            if abs_working_dir is None:
                return {
                    "success": False,
                    "error": (f"Working directory does not exist: {os.path.abspath(working_directory)}"),
                    "exit_code": -1,
                    "working_directory": working_directory,
                }

            python_executable = python_executable or sys.executable
            norm_working_dir = norm_path(abs_working_dir)
            self._report_exec_start(code, norm_working_dir)
            python_command = self._build_command(python_executable, code)

            exit_code, stdout_lines, stderr_lines, execution_time_ms = stream_execute(
                python_command,
                abs_working_dir,
                capture_output,
                capture_errors,
                timeout,
                start_time,
                self.report_output,
                popen_kwargs={
                    "encoding": "utf-8",
                    "env": {**os.environ, "PYTHONIOENCODING": "utf-8"},
                },
            )

            return self._build_result(
                exit_code,
                code,
                working_directory,
                abs_working_dir,
                stdout_lines,
                stderr_lines,
                capture_output,
                capture_errors,
                execution_time_ms,
            )
        except subprocess.TimeoutExpired:
            execution_time_ms = int((time.time() - start_time) * 1000)
            self.report_error(f"Timeout after {timeout}s")
            return {
                "success": False,
                "error": f"Python execution timed out after {timeout} seconds",
                "exit_code": -1,
                "command": code,
                "working_directory": working_directory or os.getcwd(),
                "execution_time_ms": execution_time_ms,
            }
        except FileNotFoundError:
            self.report_error("Python executable not found")
            return {
                "success": False,
                "error": f"Python executable not found: {python_executable}",
                "exit_code": -1,
                "command": code,
                "working_directory": working_directory or os.getcwd(),
                "execution_time_ms": int((time.time() - start_time) * 1000),
            }
        except Exception as e:  # noqa: BLE001 - intentional boundary, log/convert and continue
            execution_time_ms = int((time.time() - start_time) * 1000)
            self.report_error(f"Execution error: {e!s}")
            return {
                "success": False,
                "error": f"Failed to execute Python: {e!s}",
                "exit_code": -1,
                "command": code,
                "working_directory": working_directory or os.getcwd(),
                "execution_time_ms": execution_time_ms,
            }

    def _resolve_working_dir(self, working_directory: str | None) -> str | None:
        """Return the absolute working dir, or None when it does not exist."""
        if working_directory:
            abs_working_dir = os.path.abspath(working_directory)
            if not os.path.exists(abs_working_dir):
                return None
            return abs_working_dir
        return os.getcwd()

    def _build_command(self, python_executable: str, code: str) -> list[str]:
        """Build the python argv; use -c to execute code from the command line."""
        return [python_executable, "-c", code]

    def _report_exec_start(self, code: str, norm_working_dir: str) -> None:
        """Report the code to be executed."""
        code_preview = code
        if len(code) > 200:
            code_preview = code[:200] + "..."
        self.report_start(f"🐍 Executing Python code in {norm_working_dir}:\n{code_preview}")

    def _build_result(
        self,
        exit_code: int,
        code: str,
        working_directory: str | None,
        abs_working_dir: str,
        stdout_lines: list[str],
        stderr_lines: list[str],
        capture_output: bool,
        capture_errors: bool,
        execution_time_ms: int,
    ) -> dict[str, Any]:
        """Assemble the result dict and report the outcome.

        stdout/stderr carry the full captured output inline.
        """
        success = exit_code == 0
        stdout_text = lines_to_text(stdout_lines) if capture_output else ""
        stderr_text = lines_to_text(stderr_lines) if capture_errors else ""
        output_result = {
            "success": success,
            "exit_code": exit_code,
            "command": code,
            "working_directory": working_directory or abs_working_dir,
            "execution_time_ms": execution_time_ms,
        }
        if capture_output:
            output_result["stdout"] = stdout_text
        if capture_errors:
            output_result["stderr"] = stderr_text
        if success:
            self._report_success(execution_time_ms, capture_output, stdout_lines, stderr_lines)
        else:
            self._report_failure(exit_code, capture_errors, stderr_lines, stdout_lines)
            output_result["error"] = f"Python execution failed with exit code {exit_code}"
        return output_result

    def _report_success(
        self,
        execution_time_ms: int,
        capture_output: bool,
        stdout_lines: list[str],
        stderr_lines: list[str],
    ) -> None:
        """Report a successful execution summary."""
        output_summary = f"Completed in {format_duration_ms(execution_time_ms)}"
        if capture_output and stdout_lines:
            output_summary += f" ({len(stdout_lines)} lines output)"
        self.report_result(output_summary)

    def _report_failure(
        self,
        exit_code: int,
        capture_errors: bool,
        stderr_lines: list[str],
        stdout_lines: list[str],
    ) -> None:
        """Report a failed execution, truncating long stderr previews."""
        error_msg = f"Exit code {exit_code}"
        if capture_errors and stderr_lines:
            stderr_preview = preview_lines(stderr_lines, 100)
            error_msg += f": {stderr_preview}"
        self.report_error(error_msg)


# CLI interface for testing
def main():
    """Command line interface for testing the RunPythonCode tool."""
    parser = _build_parser()
    args = parser.parse_args()
    code = _read_code(args, parser)
    if code is None:
        return 1

    tool_instance = RunPythonCode()
    result = tool_instance.run(
        code=code,
        working_directory=args.directory,
        timeout=args.timeout,
        capture_output=not args.no_capture_output,
        capture_errors=not args.no_capture_errors,
        python_executable=args.python,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_result(result, args)
    return 0 if result["success"] else 1


def _build_parser():
    """Build the CLI argument parser."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Execute Python code for AI function calling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -c "print('Hello, World!')"
  %(prog)s -c "import os; print(os.listdir('.'))" -d "C:\\Users"
  %(prog)s -c "for i in range(5): print(f'Count: {i}'); import time; time.sleep(0.5)" --json
  %(prog)s -f script.py
        """,
    )

    parser.add_argument("-c", "--code", help="Python code to execute")
    parser.add_argument("-f", "--file", help="File containing Python code")
    parser.add_argument("-d", "--directory", help="Working directory for execution")
    parser.add_argument("-p", "--python", help="Python executable to use (default: current interpreter)")
    parser.add_argument("-t", "--timeout", type=int, default=60, help="Timeout in seconds (default: 60)")
    parser.add_argument("--no-capture-output", action="store_true", help="Don't capture standard output")
    parser.add_argument("--no-capture-errors", action="store_true", help="Don't capture standard error")
    parser.add_argument("--json", "-j", action="store_true", help="Output in JSON format")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show verbose output")
    return parser


def _read_code(args, parser) -> str | None:
    """Resolve the code from --code/--file; return None on file errors."""
    if not args.code and not args.file:
        parser.error("Either --code or --file must be specified")

    if args.code and args.file:
        parser.error("Cannot specify both --code and --file")

    code = args.code
    if args.file:
        if not os.path.exists(args.file):
            print(f"Error: File not found: {args.file}")
            return None
        try:
            with open(args.file, encoding="utf-8") as f:
                code = f.read()
        except Exception as e:  # noqa: BLE001 - intentional boundary, log/convert and continue
            print(f"Error reading file: {e}")
            return None
    return code


def _print_result(result: dict[str, Any], args) -> None:
    """Pretty-print the tool result."""
    if result["success"]:
        print(f"? Python execution successful (exit code {result['exit_code']})")
        print(f"  Working directory: {norm_path(result['working_directory'])}")
        print(f"  Execution time: {format_duration_ms(result['execution_time_ms'])}")

        if args.verbose:
            print("\nCommand:")
            print(f"  {result['command']}")

        if result.get("stdout"):
            print("\nOutput:")
            print(result["stdout"])

        if result.get("stderr"):
            print("\nStderr:")
            print(result["stderr"])

    else:
        print("? Python execution failed")
        print(f"  Error: {result.get('error', 'Unknown error')}")
        print(f"  Exit code: {result['exit_code']}")

        if args.verbose:
            print("\nCommand:")
            print(f"  {result['command']}")

        if result.get("stdout"):
            print("\nOutput:")
            print(result["stdout"])

        if result.get("stderr"):
            print("\nStderr:")
            print(result["stderr"])


if __name__ == "__main__":
    exit(main())
