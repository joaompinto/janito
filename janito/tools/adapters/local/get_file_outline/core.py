from janito.tools.adapters.local.adapter import register_local_tool
from .python_outline import parse_python_outline
from .markdown_outline import parse_markdown_outline
from janito.formatting import OutlineFormatter
import os
from janito.tools.tool_base import ToolBase
from janito.report_events import ReportAction
from janito.tools.tool_utils import display_path, pluralize
from janito.i18n import tr

from janito.tools.adapters.local.adapter import register_local_tool as register_tool


@register_tool
class GetFileOutlineTool(ToolBase):
    """
    Get an outline of a file's structure. Supports Python and Markdown files.

    Args:
        file_path (str): Path to the file to outline.
    """

    tool_name = "get_file_outline"

    def run(self, file_path: str) -> str:
        try:
            self.report_action(
                tr(
                    "📄 Outline file '{disp_path}' ...",
                    disp_path=display_path(file_path),
                ),
                ReportAction.READ,
            )
            ext = os.path.splitext(file_path)[1].lower()
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            if ext == ".py":
                outline_items = parse_python_outline(lines)
                outline_type = "python"
                table = OutlineFormatter.format_outline_table(outline_items)
                self.report_success(
                    tr(
                        "✅ Outlined {count} {item_word}",
                        count=len(outline_items),
                        item_word=pluralize("item", len(outline_items)),
                    ),
                    ReportAction.READ,
                )
                return (
                    tr(
                        "Outline: {count} items ({outline_type})\n",
                        count=len(outline_items),
                        outline_type=outline_type,
                    )
                    + table
                )
            elif ext == ".md":
                outline_items = parse_markdown_outline(lines)
                outline_type = "markdown"
                table = OutlineFormatter.format_markdown_outline_table(outline_items)
                self.report_success(
                    tr(
                        "✅ Outlined {count} {item_word}",
                        count=len(outline_items),
                        item_word=pluralize("item", len(outline_items)),
                    ),
                    ReportAction.READ,
                )
                return (
                    tr(
                        "Outline: {count} items ({outline_type})\n",
                        count=len(outline_items),
                        outline_type=outline_type,
                    )
                    + table
                )
            else:
                outline_type = "default"
                self.report_success(
                    tr("✅ Outlined {count} items", count=len(lines)),
                    ReportAction.READ,
                )
                return tr(
                    "Outline: {count} lines ({outline_type})\nFile has {count} lines.",
                    count=len(lines),
                    outline_type=outline_type,
                )
        except Exception as e:
            self.report_error(
                tr("❌ Error reading file: {error}", error=e),
                ReportAction.READ,
            )
            return tr("Error reading file: {error}", error=e)

            if ext == ".py":
                outline_items = parse_python_outline(lines)
                outline_type = "python"
                table = OutlineFormatter.format_outline_table(outline_items)
                self.report_success(
                    tr(
                        "✅ Outlined {count} {item_word}",
                        count=len(outline_items),
                        item_word=pluralize("item", len(outline_items)),
                    ),
                    ReportAction.READ,
                )
                return (
                    tr(
                        "Outline: {count} items ({outline_type})\n",
                        count=len(outline_items),
                        outline_type=outline_type,
                    )
                    + table
                )
            elif ext == ".md":
                outline_items = parse_markdown_outline(lines)
                outline_type = "markdown"
                table = OutlineFormatter.format_markdown_outline_table(outline_items)
                self.report_success(
                    tr(
                        "✅ Outlined {count} {item_word}",
                        count=len(outline_items),
                        item_word=pluralize("item", len(outline_items)),
                    ),
                    ReportAction.READ,
                )
                return (
                    tr(
                        "Outline: {count} items ({outline_type})\n",
                        count=len(outline_items),
                        outline_type=outline_type,
                    )
                    + table
                )
            else:
                outline_type = "default"
                self.report_success(
                    tr("✅ Outlined {count} items", count=len(lines)),
                    ReportAction.READ,
                )
                return tr(
                    "Outline: {count} lines ({outline_type})\nFile has {count} lines.",
                    count=len(lines),
                    outline_type=outline_type,
                )
        except Exception as e:
            self.report_error(
                tr("❌ Error reading file: {error}", error=e),
                ReportAction.READ,
            )
            return tr("Error reading file: {error}", error=e)
