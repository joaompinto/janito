from rich.console import Console
from pprint import pprint
from janito.common import progress_send_message, _get_system_prompt
from janito.workspace import workset, workspace
from janito.config import config
from pathlib import Path
import tempfile
from janito.change.applier import ChangeApplier
from janito.change.validator import Validator
from janito.change.instructions_parser import EditType, InstructionsParser, CodeChange
from typing import List, Dict, Optional
import shutil
from rich.markdown import Markdown
import importlib.resources
from .view.viewer import ChangeViewer
        
def _get_change_prompt() -> str:
    """Get the change prompt from the package data or local file."""
    try:
        # First try to read from package data
        with importlib.resources.files('janito.data').joinpath('change_prompt.txt').open('r') as f:
            return f.read()
    except Exception:
        # Fallback to local file for development
        local_path = Path(__file__).parent.parent / 'data' / 'change_prompt.txt'
        if local_path.exists():
            return local_path.read_text()
        raise FileNotFoundError("Could not find change_prompt.txt")

def request_change(request: str) -> str:
    """Process a change request for the codebase and return the response."""

    change_prompt = _get_change_prompt()
    
    prompt = change_prompt.format(
        request=request,
        workset=workset.content
    )
    response = progress_send_message(prompt)

    if response is None:
        return "Sorry, the response was interrupted. Please try your request again."


    # Store response in workspace directory
    response_file = (config.workspace_dir or Path(".")) / '.janito_last_response.txt'
    response_file.parent.mkdir(parents=True, exist_ok=True)
    response_file.write_text(response, encoding='utf-8')
    if config.debug:
        print(f"Response saved to {response_file}")
    handler = ResponseHandler(response)
    handler.process()

class ResponseHandler:

    def __init__(self, response: str):
        self.response = response
        self.console = Console()

    def process(self):
        inst_parser = InstructionsParser()
        instructions = inst_parser.parse(self.response)
        
        # Setup preview directory and applier
        preview_dir = workspace.setup_preview_directory()
        applier = ChangeApplier(preview_dir)
        
        # Build the change plan
        for instruction in instructions:
            if isinstance(instruction, CodeChange):
                applier.add_edit(instruction)

        # Apply the changes to the preview directory
        applied_blocks = applier.apply()
        viewer = ChangeViewer()
        viewer.show(instructions, applied_blocks)
        
        # Add horizontal ruler to separate changes from validation
        self.console.rule("[bold]Validation", style="dim")

        # Collect files that need validation (excluding deleted files)
        files_to_validate = {block.filename for block in applied_blocks 
                           if block.edit_type != EditType.DELETE}

        # Validate changes and run tests
        validator = Validator(preview_dir)
        validator.validate_files(files_to_validate)
        validator.run_tests()

        # Collect the list of created/modified/deleted/moved files
        created_files = [block.filename for block in applied_blocks if block.edit_type == EditType.CREATE]
        modified_files = set(block.filename for block in applied_blocks 
                           if block.edit_type in (EditType.EDIT, EditType.CLEAN))
        deleted_files = set(block.filename for block in applied_blocks if block.edit_type == EditType.DELETE)
        moved_files = [(block.filename, block.new_filename) for block in applied_blocks 
                      if block.edit_type == EditType.MOVE]

        # prompt the user if we want to apply the changes
        if config.auto_apply:
            apply_changes = True
        else:  
            self.console.print("\nApply changes to the workspace? [y/N] ", end="")
            response = input().lower()
            apply_changes = response.startswith('y')
            if not apply_changes:
                self.console.print("[yellow]Changes were not applied. Exiting...[/yellow]")
                return

        # Apply changes to workspace
        workspace.apply_changes(preview_dir, created_files, modified_files, deleted_files, moved_files)

def replay_saved_response():
    response_file = (config.workspace_dir or Path(".")) / '.janito_last_response.txt'
    print(response_file)
    if not response_file.exists():
        print("No saved response found")
        return
    
    with open(response_file, 'r', encoding="utf-8") as file:
        response = file.read()
        
    handler = ResponseHandler(response)
    handler.process()