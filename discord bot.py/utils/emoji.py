from discord.utils import get

def get_emoji(bot, name: str):
    """Return the string for a custom emoji the bot can access, or None.

    Example return: '<:mora:123456789012345678>' which can be inserted directly in messages or embeds.
    """
    if not name:
        return None
    emoji = get(bot.emojis, name=name)
    return str(emoji) if emoji else None
