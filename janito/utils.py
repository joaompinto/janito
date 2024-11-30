from pathlib import Path
from typing import List, Dict
import ast
import re

def generate_file_structure(base_path: Path, pattern: str = "*.py", exclude_patterns: List[str] = None) -> Dict:
    """
    Generate a tree structure of files in the given directory.
    
    Args:
        base_path: Base directory to start from
        pattern: File pattern to match (default: "*.py")
        exclude_patterns: List of patterns to exclude (default: [".janito"])
        
    Returns:
        Dict representing the directory tree structure
    """
    exclude_patterns = exclude_patterns or [".janito"]
    tree = {}
    
    try:
        for file in sorted(base_path.rglob(pattern)):
            # Skip excluded patterns
            if any(pat in file.parts for pat in exclude_patterns):
                continue
                
            # Only include files under base_path
            if base_path not in file.parents:
                continue
                
            # Get relative path and build tree
            rel_path = file.relative_to(base_path)
            current = tree
            
            # Build tree structure
            for part in rel_path.parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[rel_path.parts[-1]] = None
            
    except Exception as e:
        print(f"Error generating file structure: {e}")
        return {}
        
    return tree

def get_files_content(base_path: Path, exclude_patterns: List[str] = None) -> str:
    """Get content of all Python, text, and markdown files in given directory"""
    content = []
    try:
        exclude_patterns = exclude_patterns or [".janito"]
        tree = generate_file_structure(base_path)
        
        # Walk through directory tree
        for file in sorted(base_path.rglob("*.py")) + sorted(base_path.rglob("*.txt")) + sorted(base_path.rglob("*.md")):
            try:
                # Skip excluded patterns and files outside workspace
                if any(pat in file.parts for pat in exclude_patterns) or base_path not in file.parents:
                    continue
                rel_path = file.relative_to(base_path)
                content.append(f"### {rel_path} ###\n{file.read_text()}\n")
            except Exception:
                continue
        return "\n".join(content)
    except Exception as e:
        return f"Error reading files: {e}"

def format_tree(tree: Dict, prefix: str = "", is_last: bool = True) -> List[str]:
    """
    Format a tree dictionary into a list of strings showing the structure.
    
    Args:
        tree: Dictionary representing the tree
        prefix: Current line prefix for formatting
        is_last: Whether current node is last in its level
        
    Returns:
        List of formatted strings representing the tree
    """
    lines = []
    
    if not tree:
        return lines
        
    for i, (name, subtree) in enumerate(tree.items()):
        is_last_item = i == len(tree) - 1
        connector = "└── " if is_last_item else "├── "
        
        if subtree is None:  # File
            lines.append(f"{prefix}{connector}{name}")
        else:  # Directory
            lines.append(f"{prefix}{connector}{name}/")
            next_prefix = prefix + ("    " if is_last_item else "│   ")
            lines.extend(format_tree(subtree, next_prefix))
            
    return lines

def build_context_prompt(files_content: str, workspace_status: str, request: str, prompt_type: str = "info") -> str:
    """
    Build a context prompt for Claude with consistent formatting.
    
    Args:
        files_content: Content of all files in workspace
        workspace_status: Current workspace structure
        request: User's request
        prompt_type: Type of prompt ("info", "change", "general")
        
    Returns:
        Formatted prompt string
    """
    base_prompt = f"""Current workspace status:
{workspace_status}

Current files content:
{files_content}

"""
    
    if prompt_type == "info":
        return base_prompt + f"""
Information request: {request}

Please analyze the current project context and provide information.
Focus on explaining and understanding without suggesting any file modifications.
Format your response using markdown for better readability.
Use code blocks with language identifiers when showing code.
Use headings, lists, and emphasis to organize information.
"""
    elif prompt_type == "change":
        return base_prompt + f"""
Change request: {request}

Please provide file changes in the following format:

<fileChanges>
<change path="example.py" operation="modify">
<block description="Update database connection function">
<oldContent>
def connect_db():
    return sqlite3.connect('database.db')
</oldContent>
<newContent>
def connect_db():
    try:
        return sqlite3.connect('database.db')
    except sqlite3.Error as error:
        print('Failed to connect:', str(error))
        raise
</newContent>
</block>
</change>
</fileChanges>

Requirements:
1. Use <block> tags with descriptive comments
2. Provide both <oldContent> and <newContent>
3. If appending to the end of a file <oldContent> content must be empty
4. When not appending <oldContent> MUST be present in the files
5. Include enough context in <oldContent> to uniquely identify the section
6. For new files, use operation="create" and only provide complete content
"""
    else:  # general
        return base_prompt + f"""
User request: {request}

Please analyze the context and respond accordingly.
"""