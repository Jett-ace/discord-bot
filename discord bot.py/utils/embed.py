"""Helper to send embeds with the command author's avatar thumbnail attached by default.

Usage: from utils.embed import send_embed
       await send_embed(ctx, embed, view=view)

The helper will skip adding the thumbnail for the `my_card_info` command (alias `mci`).
"""
from typing import Any


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

    # Skip thumbnail for my_card_info (mci) per user preference
    if not has_thumb and cmd_name not in ('mci', 'my_card_info'):
        try:
            avatar = getattr(ctx.author, 'display_avatar', None)
            if avatar:
                embed.set_thumbnail(url=avatar.url)
        except Exception:
            pass

    return await ctx.send(embed=embed, **kwargs)
