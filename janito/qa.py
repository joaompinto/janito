from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from janito.common import progress_send_message
from janito.workspace import workset
from pathlib import Path

QA_PROMPT = """Please provide a clear and concise answer to the following question about the workset provided later.

Question: {question}

Focus on providing factual information and explanations. Do not suggest code changes.
Format your response using markdown with appropriate headers and code blocks.

workset content:
{workset}
"""

def ask_question(question: str, file_filter: list[Path] = None) -> str:
    """Process a question about the codebase and return the answer

    Args:
        question: The question to ask about the codebase
        file_filter: list of paths to files to include in the workset

    Returns:
        str: The answer from the AI agent, or an error message if interrupted
    """
    workset.refresh()

    prompt = QA_PROMPT.format(
        question=question,
        workset=workset.content
    )
    answer = progress_send_message(prompt)
    
    if answer is None:
        return "Sorry, the response was interrupted. Please try asking your question again."
    
    return answer


def display_answer(answer: str, raw: bool = False) -> None:
    """Display the answer as markdown"""
    if answer is None:
        Console().print("\n[red]Error: No answer received - the response was interrupted[/red]\n")
        return
        
    console = Console()

    if raw:
        console.print(answer)
        return

    # Display markdown answer directly
    console.print(Markdown(answer))