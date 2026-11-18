"""
/costs command handler - displays overall-use statistics per day.

Reads the per-turn usage rows persisted by :mod:`janito.tooling.accounting`
in the ``accounting.db`` SQLite database, aggregates them by calendar day and
renders the last 10 days as a `rich <https://github.com/Textualize/rich>`_
table, followed by a second table breaking the same period down by
day/provider/model (issue #75).
"""

from __future__ import annotations

from janito.providers.costing import format_cost

from .base import CmdHandler
from .registry import register_command


class CostsCmdHandler(CmdHandler):
    """Command handler for the /costs command."""

    @property
    def name(self) -> str:
        return "/costs"

    @property
    def description(self) -> str:
        return "Show overall-use statistics grouped by day (last 10 days)"

    def handle(self, shell, user_input: str) -> bool:
        """Handle the /costs command."""
        if user_input.strip().lower() == self.name.lower():
            self._print_stats()
            return True
        return False

    @staticmethod
    def _format_cached_tokens(cached_tokens: int, input_tokens: int) -> str:
        """Format a cached-token count with the share of total input it represents.

        ``input_tokens`` is the day's *total* input, which already includes
        the cached (cache-read) tokens -- the API reports ``prompt_tokens``
        / ``input_tokens`` with ``cached_tokens`` counted inside it, and the
        provider cost modules bill ``input - cached`` at the miss rate.  The
        percentage is therefore ``cached / input * 100``, rounded to a whole
        number.  When there is no input at all the plain count is returned
        without a percentage.

        Args:
            cached_tokens: Day-total cached (cache-read) input tokens.
            input_tokens: Day-total input tokens, cached included.

        Returns:
            str: e.g. ``"600 (25%)"`` or ``"0"`` when nothing was input.
        """
        if input_tokens > 0:
            pct = cached_tokens / input_tokens * 100
            return f"{cached_tokens:,} ({pct:.0f}%)"
        return f"{cached_tokens:,}"

    def _build_table(self, stats: list[dict]):
        """Build a rich ``Table`` with the daily usage statistics.

        Args:
            stats: Per-day usage aggregates as returned by
                ``accounting.get_daily_stats()`` (newest day first).

        Returns:
            rich.table.Table: A table with one row per day: the date, the
                summed input/cached/output tokens and the estimated cost
                (rendered with the same adaptive, magnitude-aware format the
                end-of-turn ``Cost:`` summary uses, ``N/A`` when unknown).
        """
        from rich.table import Table

        table = Table(
            title="Usage Statistics (last 10 days)",
            title_style="bold",
            header_style="bold cyan",
            show_lines=False,
        )
        table.add_column("Day", style="green", no_wrap=True)
        table.add_column("Input tokens", justify="right")
        table.add_column("Cached tokens", justify="right")
        table.add_column("Output tokens", justify="right")
        table.add_column("Cost", justify="right")

        for row in stats:
            cost = row["cost"]
            cost_text = format_cost(cost) if cost is not None else "N/A"
            table.add_row(
                row["day"],
                f"{row['input_tokens']:,}",
                self._format_cached_tokens(row["cached_tokens"], row["input_tokens"]),
                f"{row['output_tokens']:,}",
                cost_text,
            )

        return table

    def _build_model_table(self, stats: list[dict]):
        """Build a rich ``Table`` with per-day/per-provider/per-model stats.

        Args:
            stats: Per-day/per-provider/per-model aggregates as returned by
                ``accounting.get_per_model_stats()`` (newest day first, then
                provider, then model).

        Returns:
            rich.table.Table: A table with one row per day/provider/model
                group: the date, provider, model, the summed input/cached/
                output tokens and the estimated cost (rendered with the same
                adaptive, magnitude-aware format the end-of-turn ``Cost:``
                summary uses, ``N/A`` when unknown). Unknown provider/model
                values are rendered as ``unknown``.
        """
        from rich.table import Table

        table = Table(
            title="Per Model Statistics (last 10 days)",
            title_style="bold",
            header_style="bold cyan",
            show_lines=False,
        )
        table.add_column("Day", style="green", no_wrap=True)
        table.add_column("Provider", style="magenta", no_wrap=True)
        table.add_column("Model", style="cyan", no_wrap=True)
        table.add_column("Input tokens", justify="right")
        table.add_column("Cached tokens", justify="right")
        table.add_column("Output tokens", justify="right")
        table.add_column("Cost", justify="right")

        for row in stats:
            cost = row["cost"]
            cost_text = format_cost(cost) if cost is not None else "N/A"
            table.add_row(
                row["day"],
                row["provider"] or "unknown",
                row["model"] or "unknown",
                f"{row['input_tokens']:,}",
                self._format_cached_tokens(row["cached_tokens"], row["input_tokens"]),
                f"{row['output_tokens']:,}",
                cost_text,
            )

        return table

    def _print_stats(self) -> None:
        """Print the daily and per-model usage statistics tables."""
        from rich.console import Console

        from janito.tooling.accounting import (
            get_daily_stats,
            get_db_path,
            get_per_model_stats,
        )

        console = Console()
        stats = get_daily_stats()

        if not stats:
            console.print("No usage recorded yet.")
            console.print(f"[dim](database: {get_db_path()})[/dim]")
            return

        table = self._build_table(stats)
        table.caption = f"Database: {get_db_path()}"
        table.caption_justify = "left"
        console.print(table)

        model_stats = get_per_model_stats()
        if model_stats:
            model_table = self._build_model_table(model_stats)
            console.print()
            console.print(model_table)


# Register this handler
_handler = CostsCmdHandler()
register_command(_handler)
