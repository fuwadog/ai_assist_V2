"""Entry point for AI Assistant CLI V2."""

from __future__ import annotations

import click
from rich.console import Console

from core.dispatcher import Dispatcher
from utils.logger import setup_logging

console = Console()


@click.group(invoke_without_command=True)
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.version_option(version="0.2.0")
@click.pass_context
def cli(ctx: click.Context, debug: bool) -> None:
    """AI Assistant CLI V2 - Intelligent codebase analysis."""
    if debug:
        setup_logging("DEBUG")
    else:
        # Relies on LOG_LEVEL env var in utils/logger.py
        setup_logging()

    if ctx.invoked_subcommand is None:
        # Start interactive REPL
        repl()


def repl() -> None:
    """Interactive REPL loop."""
    console.print("\n[bold blue]🧠 AI Assistant CLI V2[/bold blue]")
    console.print("Type [cyan]/help[/cyan] for commands, [cyan]/exit[/cyan] to quit\n")

    # The dispatcher handles initialization of context/storage/llm
    dispatcher = Dispatcher(console)

    while True:
        try:
            # Use standard input for clean line reading, colored via Rich later
            user_input = console.input("[bold green]>[/bold green] ")
            dispatcher.dispatch(user_input)

        except KeyboardInterrupt:
            # Handle Ctrl+C cleanly
            console.print("\n[dim]Use /exit to quit[/dim]")
            continue
        except EOFError:
            # Handle Ctrl+D cleanly
            console.print("\nGoodbye! 👋")
            dispatcher.storage.close()
            break
        except Exception as e:
            console.print(f"[bold red]Unexpected Error:[/bold red] {e}")


if __name__ == "__main__":
    cli()
