from pathlib import Path
from typing import Optional
from rich.console import Console
from janito.config import config
from janito.qa import ask_question, display_answer
from janito.scan import collect_files_content
from janito.tui import TuiApp
from ..base import BaseCLIHandler

class AskHandler(BaseCLIHandler):
    def handle(self, question: str):
        """Process a question about the codebase"""
        if question == ".":
            from janito.cli.input import read_stdin
            question = read_stdin()

        paths_to_scan = [config.workdir] if not config.include else config.include
        files_content = collect_files_content(paths_to_scan)

        if config.tui:
            answer = ask_question(question, files_content)
            app = TuiApp(answer)
            app.run()
        else:
            answer = ask_question(question, files_content)
            display_answer(answer)