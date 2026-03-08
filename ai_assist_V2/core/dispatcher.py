"""Dispatcher sets up and routes CLI commands."""

from __future__ import annotations

import sys
from typing import Any

from rich.console import Console

from config import Config
from core.context_manager import ContextManager
from core.llm_provider import LLMProvider
from core.storage import Storage
from utils.logger import logger
from utils.token_counter import get_counter
from workers.research_worker import ResearchWorker


class Dispatcher:
    """Initializes sub-components and routes REPL commands."""

    def __init__(self, console: Console) -> None:
        self.console = console
        self.config = Config()
        try:
            self.config.validate()
        except ValueError as e:
            self.console.print(f"[bold red]Configuration Error:[/bold red] {e}")
            sys.exit(1)

        self.storage = Storage(self.config.db_path)
        self.token_counter = get_counter()

        self.llm = LLMProvider(self.config, self.token_counter)
        self.context = ContextManager(
            self.storage, self.token_counter, self.config.max_context_tokens
        )
        self.worker = ResearchWorker(self.context, self.llm, self.storage, self.config)

    def dispatch(self, user_input: str) -> None:
        """Parse and route user input from the REPL."""
        user_input = user_input.strip()
        if not user_input:
            return

        if user_input.startswith("/"):
            self._handle_command(user_input)
        else:
            self._handle_query(user_input)

    def _handle_command(self, cmd_line: str) -> None:
        """Route slash commands."""
        parts = cmd_line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        try:
            if cmd == "/load":
                self._cmd_load(args)
            elif cmd == "/unload":
                self._cmd_unload(args)
            elif cmd in ("/list", "/ls"):
                self._cmd_list()
            elif cmd in ("/context", "/ctx"):
                self._cmd_context()
            elif cmd == "/clear":
                self._cmd_clear(args)
            elif cmd == "/stats":
                self._cmd_stats()
            elif cmd == "/help":
                self._cmd_help()
            elif cmd in ("/exit", "/quit"):
                self.console.print("Goodbye! 👋")
                # Clean up DB connection
                self.storage.close()
                sys.exit(0)
            else:
                self.console.print(f"[yellow]Unknown command: {cmd}[/yellow]. Type /help for a list of commands.")
        except Exception as e:
            self.console.print(f"[bold red]Error:[/bold red] {e}")
            logger.exception("Command error")

    def _handle_query(self, query: str) -> None:
        """Route natural language queries to the Research Worker."""
        try:
            with self.console.status("[bold cyan]Thinking...[/bold cyan]", spinner="dots"):
                result = self.worker.answer(query)

            # Display result
            meta_str = f"Method: {result['method']} | Tokens: {result['tokens_used']:,}"
            self.console.print(f"\n[dim]{meta_str}[/dim]\n")
            self.console.print(result["answer"])
            self.console.print()

        except Exception as e:
            self.console.print(f"\n[bold red]Error answering query:[/bold red] {e}")
            logger.exception("Query error")

    # ── Command Handlers ────────────────────────────────────────────────────

    def _cmd_load(self, args: list[str]) -> None:
        if not args:
            self.console.print("[yellow]Usage: /load <filepath> [--full][/yellow]")
            return

        full_content = "--full" in args
        filepaths = [a for a in args if a != "--full"]

        for fp in filepaths:
            msg = f"Loading {fp}..."
            if full_content:
                msg += " (full text)"
            with self.console.status(msg):
                data = self.context.load_file(fp, full_content=full_content)
                ctype = "Summary" if data["is_summary"] else "Full Content"
                self.console.print(f"[green]✓ Loaded {fp}[/green] ({ctype}, {data['token_count']:,} tokens)")

    def _cmd_unload(self, args: list[str]) -> None:
        if not args:
            self.console.print("[yellow]Usage: /unload <filepath> | --all[/yellow]")
            return

        if "--all" in args:
            self._cmd_clear(["--all"])
            return

        for fp in args:
            if self.context.unload_file(fp):
                self.console.print(f"[green]✓ Unloaded {fp}[/green]")
            else:
                self.console.print(f"[yellow]File not loaded: {fp}[/yellow]")

    def _cmd_clear(self, args: list[str]) -> None:
        if "--all" in args:
            count = self.context.clear_all()
            self.console.print(f"[green]✓ Cleared all {count} files from context.[/green]")
        else:
            self.console.print("[yellow]Usage: /clear --all[/yellow]")

    def _cmd_list(self) -> None:
        ctx = self.context.get_context()
        files = self.context.loaded_files

        if not files:
            self.console.print("No files currently loaded. Use [cyan]/load <filepath>[/cyan].")
            return

        self.console.print(f"\n[bold]Loaded Files ({len(files)}):[/bold]")
        for path, data in files.items():
            ctype = "[S]" if data["is_summary"] else "[F]"
            self.console.print(f"  {ctype} {path} [dim]({data['token_count']:,} tokens)[/dim]")

        util_pct = int(ctx["utilization"] * 100)
        self.console.print(f"\nTotal: [bold]{ctx['total_tokens']:,}[/bold] / {ctx['max_tokens']:,} tokens ({util_pct}%)")
        self.console.print("[dim][S] = Summary, [F] = Full content[/dim]\n")

    def _cmd_context(self) -> None:
        ctx = self.context.get_context()
        util_pct = int(ctx["utilization"] * 100)

        self.console.print("\n[bold]Context Summary:[/bold]")
        self.console.print(f"  Files loaded:  {len(ctx['loaded_files'])}")
        self.console.print(f"  Total tokens:  {ctx['total_tokens']:,} / {ctx['max_tokens']:,} ({util_pct}%)")
        self.console.print()

    def _cmd_stats(self) -> None:
        stats = self.worker.get_session_stats()
        self.console.print("\n[bold]Session Statistics:[/bold]")
        self.console.print(f"  Queries answered: {stats['total_queries']}")
        for method, count in stats["by_method"].items():
            self.console.print(f"  - {method}: {count}")

        hit_rate = int(stats["cache_hit_rate"] * 100)
        self.console.print("\n  Cache performance:")
        self.console.print(f"  - Hits: {stats['cache_hits']} ({hit_rate}%)")
        self.console.print(f"  - Misses: {stats['total_queries'] - stats['cache_hits']}")

        self.console.print(f"\n  Total tokens used: {stats['total_tokens']:,}\n")

    def _cmd_help(self) -> None:
        self.console.print("""
[bold]Commands:[/bold]
  [cyan]/load <file> [--full][/cyan]  Load a file into context (defaults to AST summary)
  [cyan]/unload <file>[/cyan]        Remove a file from context
  [cyan]/list[/cyan]                 Show all loaded files
  [cyan]/clear --all[/cyan]          Remove all files from context
  [cyan]/context[/cyan]              Show current context size and utilization
  [cyan]/stats[/cyan]                Show session analytics (queries, cache hits, tokens)
  [cyan]/help[/cyan]                 Show this help message
  [cyan]/exit[/cyan] or [cyan]/quit[/cyan]       Exit AI Assistant
        """)
