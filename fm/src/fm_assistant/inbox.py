"""Inbox (F1). The op returns items newest first, already cut at `since`; nothing is advised here."""

RECENT_MAX = 5


def recent(res: dict, n: int = RECENT_MAX) -> list[dict]:
    return [{"date": i["date"], "title": i["title"]} for i in (res.get("items") or [])[:n]]


def text(res: dict, since: str | None = None) -> str:
    """Header with the unread count, then one line per item: date time, '*' unread, '!' important, title."""
    items = res.get("items") or []
    head = f"Inbox: {res.get('unread', 0)} unread"
    if not items:
        return head + (f"\nno messages since {since}" if since else "\nno messages")
    rows = [f"{i['date']} {i.get('time') or '--:--'} {'*' if not i.get('read') else ' '}"
            f"{'!' if i.get('important') else ' '} {i['title']}" for i in items]
    return head + "\n" + "\n".join(rows)
