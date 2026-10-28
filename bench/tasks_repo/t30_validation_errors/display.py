"""Presentation helpers used by the sample application's status view."""
def status_label(name, count):
    return f"{name.replace('_', ' ').title()}: {count}"

def compact_lines(lines, limit=4):
    rows = list(lines)
    visible = rows[:limit]
    if len(rows) > limit:
        visible.append(f"... {len(rows) - limit} more")
    return "\n".join(visible)
