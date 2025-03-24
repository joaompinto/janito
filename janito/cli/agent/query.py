"""
Query handling functionality for Janito CLI.
"""
import sys
import traceback
from typing import Optional
from rich.console import Console
import anthropic

from janito.token_report import generate_token_report
from janito.tools import print_usage_stats
from janito.cli.agent.initialization import initialize_agent
from janito.cli.agent.conversation import load_messages, save_messages

console = Console()

def handle_query(query: str, temperature: float, verbose: bool, show_tokens: bool, continue_conversation: Optional[str] = None, system_instructions: Optional[str] = None) -> None:
    """
    Handle a query by initializing the agent and sending the query.
    
    Args:
        query: The query to send to the agent
        temperature: Temperature value for model generation
        verbose: Whether to enable verbose mode
        show_tokens: Whether to show detailed token usage
        continue_conversation: Optional message ID to continue a specific conversation
        system_instructions: Optional custom system instructions to use instead of loading from file
    """
    # Initialize the agent
    agent = initialize_agent(temperature, verbose, system_instructions)
    
    # Load previous messages if continuing conversation
    if continue_conversation is not None:
        # If continue_conversation is an empty string (from flag with no value), use default behavior
        message_id = None if continue_conversation == "" else continue_conversation
        messages = load_messages(message_id)
        if messages:
            agent.set_messages(messages)
            if message_id:
                console.print(f"[bold blue]🔄 Continuing conversation with ID: {message_id}[/bold blue]")
            else:
                console.print("[bold blue]🔄 Continuing most recent conversation[/bold blue]")
                
            # Provide information about the conversation being continued
            if verbose and len(messages) > 0:
                # Get the number of messages
                num_messages = len(messages)
                # Get the last user message if available
                last_user_message = next((msg.get("content", "") for msg in reversed(messages) 
                                         if msg.get("role") == "user"), "")
                if last_user_message:
                    console.print(f"[dim]📝 Last query: \"{last_user_message[:60]}{'...' if len(last_user_message) > 60 else ''}\"[/dim]")
        else:
            console.print("[bold yellow]⚠️ No previous conversation found to continue[/bold yellow]")
    
    # Send the query to the agent
    try:
        agent.query(query)
        
        # Save messages after successful query and get the message ID
        message_id = save_messages(agent)
        
        # Print token usage report
        if show_tokens:
            generate_token_report(agent, verbose=True, interrupted=False)
        else:
            # Show basic token usage
            generate_token_report(agent, verbose=False, interrupted=False)
        
        # Print tool usage statistics
        print_usage_stats()
        

            
    except KeyboardInterrupt:
        # Handle Ctrl+C by printing token and tool usage information
        console.print("\n[bold yellow]⚠️ Query interrupted by user (Ctrl+C)[/bold yellow]")
        
        # Save messages even if interrupted
        message_id = save_messages(agent)
        
        # Print token usage report (even if interrupted)
        try:
            if show_tokens:
                generate_token_report(agent, verbose=True, interrupted=True)
            else:
                # Show basic token usage
                generate_token_report(agent, verbose=False, interrupted=True)
            
            # Print tool usage statistics
            print_usage_stats()
            

        except Exception as e:
            console.print(f"[bold red]❌ Error generating usage report:[/bold red] {str(e)}")
            if verbose:
                console.print(traceback.format_exc())
        
        # Exit with non-zero status to indicate interruption
        sys.exit(130)  # 130 is the standard exit code for SIGINT
            
    except anthropic.APIError as e:
        console.print(f"[bold red]❌ Anthropic API Error:[/bold red] {str(e)}")
        
    except Exception as e:
        console.print(f"[bold red]❌ Error:[/bold red] {str(e)}")
        if verbose:
            console.print(traceback.format_exc())