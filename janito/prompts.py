import re

# Core system prompt focused on role and purpose
SYSTEM_PROMPT = """You are Janito, an AI assistant for software development tasks. Be concise.
"""

EMPTY_DIR_PROMPT = """
This is an empty directory. What files should be created and what should they contain? (one line description)
Allways provide options using a  header label "=== **Option 1** : ...", "=== **Option 2**: ...", etc.

Request:
{request}
"""

NON_EMPTY_DIR_PROMPT = """
Current files:
<files>
{files_content}
</files>

Always provide options using a header label "=== **Option 1** : ...", "=== **Option 2**: ...", etc.
Provide the header with a short description followed by the file changes on the next line
What files should be modified and what should they contain? (one line description)

Request:
{request}
"""

SELECTED_OPTION_PROMPT = """
Original request: {request}

Please provide detailed implementation using the following option as a guide:

{option_text}

Original request: {request}

Please provide implementation details following these guidelines:
- The instructions should be clear and concise
- Provide only the changes, no additional information
- The supported operations are: insert_after_content, insert_before_content, replace_content, delete_content, create_file
- Use the following format for each change:
    ## <uuid> filename:operation ##
    ## <uuid> original ##
    original content block
    ## <uuid> new  ##
    new content block
    ## <uuid> end  ##
"""


def build_selected_option_prompt(option_number: int, request: str, initial_response: str) -> str:
    """Build prompt for selected option details"""
    options = parse_options(initial_response)
    if option_number not in options:
        raise ValueError(f"Option {option_number} not found in response")
    
    return SELECTED_OPTION_PROMPT.format(
        option_text=options[option_number],
        request=request
    )

def parse_options(response: str) -> dict[int, str]:
    """Parse options from the response text"""
    options = {}
    pattern = r"===\s*\*\*Option (\d+)\*\*\s*:\s*(.+?)(?====\s*\*\*Option|\Z)"
    matches = re.finditer(pattern, response, re.DOTALL)
    
    for match in matches:
        option_num = int(match.group(1))
        option_text = match.group(2).strip()
        options[option_num] = option_text
        
    return options

def build_request_analisys_prompt(files_content: str, request: str) -> str:
    """Build prompt for information requests"""
    if not files_content.strip():
        return EMPTY_DIR_PROMPT.format(request=request)
    return NON_EMPTY_DIR_PROMPT.format(
        files_content=files_content,
        request=request
    )
