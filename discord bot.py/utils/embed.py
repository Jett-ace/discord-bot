"""Helper to send embeds with the command author's avatar thumbnail attached by default.

Usage: from utils.embed import send_embed
       await send_embed(ctx, embed, view=view)

The helper will skip adding the thumbnail for the `my_card_info` command (alias `mci`).
"""
from typing import Any


def create_progress_bar(current: float, total: float, segments: int = 15) -> str:
    """Create a visual progress bar using filled (▰) and empty (▱) segments.
    
    Args:
        current: Current progress value
        total: Total/max value
        segments: Number of segments in the bar (default 15)
        
    Returns:
        Progress bar string like "▰▰▰▰▰▰▰▰▰▰▱▱▱▱▱"
    """
    if total <= 0:
        return '▱' * segments
    
    progress = min(1.0, max(0.0, float(current) / float(total)))
    filled = int(round(progress * segments))
    filled = max(0, min(segments, filled))
    
    bar_filled = '▰' * filled
    bar_empty = '▱' * (segments - filled)
    
    return f"{bar_filled}{bar_empty}"


def format_time_remaining(seconds: float) -> str:
    """Format seconds into natural language time remaining.
    
    Args:
        seconds: Number of seconds remaining
        
    Returns:
        Human-readable string like "2h 15m" or "45s"
    """
    if seconds <= 0:
        return "Ready!"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 and hours == 0:  # Only show seconds if less than an hour
        parts.append(f"{secs}s")
    
    return " ".join(parts) if parts else "Ready!"


async def send_embed(ctx: Any, embed: Any = None, **kwargs):
    """Send an embed while attaching the command author's avatar as the thumbnail.

    Skips thumbnailing for the `my_card_info` command.
    All kwargs are forwarded to ctx.send.
    Returns whatever ctx.send returns.
    """
    # If no embed provided, just forward
    if embed is None:
        return await ctx.send(**kwargs)

    # determine command name if available
    cmd_name = None
    try:
        cmd = getattr(ctx, 'command', None)
        cmd_name = getattr(cmd, 'name', None) if cmd else None
    except Exception:
        cmd_name = None

    # Do not override existing thumbnail
    try:
        has_thumb = bool(getattr(embed, 'thumbnail', None) and getattr(embed.thumbnail, 'url', None))
    except Exception:
        has_thumb = False

    # Skip thumbnail for my_card_info (mci) and mycards commands per user preference
    if not has_thumb and cmd_name not in ('mci', 'my_card_info', 'mycards', 'mc', 'servants'):
        try:
            avatar = getattr(ctx.author, 'display_avatar', None)
            if avatar:
                embed.set_thumbnail(url=avatar.url)
        except Exception:
            pass

    return await ctx.send(embed=embed, **kwargs)
