"""Generate formatted markdown reports from structured inventory data."""

from typing import Optional


def generate_inventory_report(
    items: list[dict],
    title: str = "Inventory Report",
    summary_fields: Optional[list[str]] = None,
    all_fields: Optional[list[str]] = None,
) -> str:
    """Generate a markdown inventory report from extracted item dicts.

    Args:
        items: List of dicts, each representing one extracted item.
        title: Report title.
        summary_fields: Fields to include in the overview table.
        all_fields: All fields to show in per-item detail sections.

    Returns:
        Formatted markdown string.
    """
    if summary_fields is None:
        summary_fields = ["title", "year", "mileage", "fuel", "price"]
    if all_fields is None:
        all_fields = [
            "title", "price", "year", "mileage", "fuel", "engine", "power",
            "transmission", "drive", "body_type", "color", "doors", "seats",
            "condition", "description", "equipment",
        ]

    lines = [
        f"# {title}",
        "",
        f"*Generated inventory report with {len(items)} items*",
        "",
        "---",
        "",
    ]

    if not items:
        lines.append("No items found.")
        return "\n".join(lines)

    # Summary table
    lines.extend(_build_summary_table(items, summary_fields))
    lines.extend(["", "---", ""])

    # Per-item detail sections
    for i, item in enumerate(items, 1):
        lines.extend(_build_item_section(item, i, all_fields))

    return "\n".join(lines)


def _build_summary_table(items: list[dict], summary_fields: list[str]) -> list[str]:
    """Build a markdown overview table."""
    headers = [_field_label(f) for f in summary_fields]
    lines = [
        "## Quick Overview",
        "",
        "| # | " + " | ".join(headers) + " |",
        "|---" + "|-------" * len(headers) + "|",
    ]

    for i, item in enumerate(items, 1):
        values = [str(item.get(f, "")) for f in summary_fields]
        lines.append(f"| {i} | " + " | ".join(values) + " |")

    return lines


def _build_item_section(item: dict, index: int, all_fields: list[str]) -> list[str]:
    """Build a detailed section for a single item."""
    item_title = item.get("title", f"Item {index}")
    price = item.get("price", "")

    lines = [
        f"## {index}. {item_title}",
        "",
    ]

    if price:
        lines.extend([f"**Price:** {price}", ""])

    # Specs table (exclude title, price, description, equipment, url — they get special treatment)
    special_fields = {"title", "price", "description", "equipment", "url"}
    spec_fields = [f for f in all_fields if f not in special_fields]
    has_specs = any(item.get(f) for f in spec_fields)

    if has_specs:
        lines.extend(["### Specifications", "", "| Spec | Value |", "|------|-------|"])
        for field in spec_fields:
            value = item.get(field, "")
            if value:
                lines.append(f"| {_field_label(field)} | {value} |")
        lines.append("")

    # Description
    description = item.get("description", "")
    if description:
        lines.extend(["### Description", "", str(description), ""])

    # Equipment list
    equipment = item.get("equipment", [])
    if equipment:
        if isinstance(equipment, str):
            equipment = [e.strip() for e in equipment.split(",") if e.strip()]
        if isinstance(equipment, list) and equipment:
            lines.extend(["### Equipment", ""])
            for eq in equipment:
                lines.append(f"- {eq}")
            lines.append("")

    # Source link
    url = item.get("url", "")
    if url:
        lines.extend([f"[View listing]({url})", ""])

    lines.extend(["---", ""])
    return lines


def _field_label(field_name: str) -> str:
    """Convert a snake_case field name to a human-readable label."""
    return field_name.replace("_", " ").title()
