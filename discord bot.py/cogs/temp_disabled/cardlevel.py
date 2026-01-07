"""Card Leveling System - Level up your cards with EXP bottles"""
import discord
from discord.ext import commands
from utils.constants import rarity_emojis
from utils.database import (
    get_card_info, level_up_card, get_user_item_count,
    require_enrollment, calculate_card_stats, get_card_exp_required
)
from utils.embed import send_embed


class CardLevel(commands.Cog):
    """Level up cards using EXP bottles"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name="levelcard", aliases=["lc"])
    async def level_card(self, ctx, character_name: str = None, bottles: int = None):
        """Level up a card using EXP bottles.
        
        Usage: !levelcard <character_name> <bottles>
        Example: !levelcard Jean 5
        
        Each bottle gives 200 EXP to your card.
        Cards gain stats based on rarity:
        - R: +5% stats per level
        - SR: +7% stats per level
        - SSR: +10% stats per level
        """
        if not await require_enrollment(ctx):
            return
        
        # If no args, show card info command
        if not character_name:
            return await ctx.send("Usage: `!levelcard <name> <bottles>`\nExample: `!levelcard Artoria 5`")
        
        # If just character name, show card info
        if bottles is None:
            card = await get_card_info(ctx.author.id, character_name)
            if not card:
                return await ctx.send(f"You don't own **{character_name}**")
            
            # Get full character data from constants
            from utils.constants import characters
            char_data = next((c for c in characters if c['name'].lower() == card['name'].lower()), None)
            
            # Get user's EXP bottles
            bottle_count = await get_user_item_count(ctx.author.id, 'exp_bottle')
            
            # Build rich card info embed
            rarity_emoji = rarity_emojis.get(card['rarity'], card['rarity'])
            
            # Choose color by rarity
            if card['rarity'] == 'SSR':
                color = 0xFFD700  # Gold
            elif card['rarity'] == 'SR':
                color = 0x9B59B6  # Purple
            else:
                color = 0x2ECC71  # Green
            
            embed = discord.Embed(
                title=card['name'],
                description=char_data['description'] if char_data else "A legendary Servant.",
                color=color
            )
            embed.set_thumbnail(url=f"https://cdn.discordapp.com/emojis/{rarity_emoji.split(':')[2].rstrip('>')}")
            
            # Statistics section
            stats = (
                f"**Power:** {card['power_level']:,}\n"
                f"**Health:** {card['current_hp']:,}\n"
                f"**Attack:** {card['current_atk']:,}\n"
                f"**Level:** {card['level']} ({card['exp']:,}/{card['exp_needed']:,})"
            )
            embed.add_field(name="Statistics:", value=stats, inline=False)
            
            # Class section
            class_info = f"**Class:** {card.get('class', 'Unknown')}"
            embed.add_field(name="", value=class_info, inline=False)
            
            # Set character image at bottom
            if char_data and char_data.get('image'):
                embed.set_image(url=char_data['image'])
            
            embed.set_footer(text=f"This card belongs to {ctx.author.name}")
            
            return await send_embed(ctx, embed)
        
        # Validate bottles
        if bottles < 1:
            return await ctx.send("You must use at least 1 EXP bottle.")
        
        if bottles > 100:
            return await ctx.send("Maximum 100 bottles per use.")
        
        # Attempt to level up card
        result = await level_up_card(ctx.author.id, character_name, bottles)
        
        if not result['success']:
            return await ctx.send(f"{result['error']}")
        
        # Build success embed
        if result['level_ups'] == 0:
            # No level up, just gained EXP
            embed = discord.Embed(
                title=f"EXP Added to {result['name']}",
                description=f"Used {result['bottles_used']} EXP bottles (+{result['exp_used']} EXP)",
                color=0x3498DB
            )
            
            exp_progress = f"{result['new_exp']:,} / {result['exp_needed']:,}"
            progress_percent = int((result['new_exp'] / result['exp_needed']) * 100) if result['exp_needed'] > 0 else 100
            progress_bar = "█" * (progress_percent // 10) + "░" * (10 - (progress_percent // 10))
            
            embed.add_field(
                name="Progress to Next Level",
                value=f"`{progress_bar}` {progress_percent}%\n{exp_progress}",
                inline=False
            )
        else:
            # Leveled up!
            rarity_emoji = rarity_emojis.get(result.get('rarity', 'R'), '')
            embed = discord.Embed(
                title=f"{rarity_emoji} {result['name']} Leveled Up!",
                description=f"**Level {result['old_level']} → {result['new_level']}** (+{result['level_ups']} level{'s' if result['level_ups'] > 1 else ''})",
                color=0x2ECC71
            )
            
            # Stats comparison
            hp_gain = result['new_hp'] - result['old_hp']
            atk_gain = result['new_atk'] - result['old_atk']
            power_gain = result['new_power'] - result['old_power']
            
            stats_before = (
                f"**HP:** {result['old_hp']:,}\n"
                f"**ATK:** {result['old_atk']:,}\n"
                f"**Power:** {result['old_power']:,}"
            )
            stats_after = (
                f"**HP:** {result['new_hp']:,} (+{hp_gain:,})\n"
                f"**ATK:** {result['new_atk']:,} (+{atk_gain:,})\n"
                f"**Power:** {result['new_power']:,} (+{power_gain:,})"
            )
            
            embed.add_field(name="Before", value=stats_before, inline=True)
            embed.add_field(name="After", value=stats_after, inline=True)
            
            # Show remaining EXP
            exp_progress = f"{result['new_exp']:,} / {result['exp_needed']:,}"
            embed.add_field(
                name="Progress to Next Level",
                value=exp_progress,
                inline=False
            )
            
            embed.set_footer(text=f"Used {result['bottles_used']} EXP bottles")
        
        await send_embed(ctx, embed)
    
    @commands.command(name="cardinfo", aliases=["ci", "card"])
    async def card_info(self, ctx, *, character_name: str = None):
        """View info about ANY Servant (whether you own it or not).
        
        Usage: !cardinfo <character_name>
        Example: !cardinfo Gilgamesh
        """
        if not character_name:
            return await ctx.send("Usage: `!ci <name>`\nExample: `!ci Gilgamesh`")
        
        from utils.constants import characters, rarity_emojis
        from utils.embed import send_embed
        
        # Find character in constants
        char_data = next((c for c in characters if c['name'].lower() == character_name.lower()), None)
        
        if not char_data:
            return await ctx.send(f"Servant **{character_name}** not found in the database.")
        
        # Choose color by rarity
        if char_data['rarity'] == 'SSR':
            color = 0xFFD700  # Gold
        elif char_data['rarity'] == 'SR':
            color = 0x9B59B6  # Purple
        else:
            color = 0x2ECC71  # Green
        
        # Get rarity emoji
        rarity_emoji = rarity_emojis.get(char_data['rarity'], char_data['rarity'])
        
        # Build embed
        embed = discord.Embed(
            title=char_data['name'],
            description=char_data['description'],
            color=color
        )
        embed.set_thumbnail(url=f"https://cdn.discordapp.com/emojis/{rarity_emoji.split(':')[2].rstrip('>')}")
        
        # Calculate base power level (using same formula as database)
        base_power = 100 if char_data['rarity'] == 'R' else (300 if char_data['rarity'] == 'SR' else 800)
        total_stats = char_data['hp'] + char_data['atk']
        base_power_level = base_power + (total_stats // 10)
        
        # Statistics section
        stats = (
            f"**Power:** {base_power_level:,}\n"
            f"**Health:** {char_data['hp']:,}\n"
            f"**Attack:** {char_data['atk']:,}"
        )
        embed.add_field(name="Statistics:", value=stats, inline=False)
        
        # Class section
        class_info = f"**Class:** {char_data['class']}"
        embed.add_field(name="", value=class_info, inline=False)
        
        # Set character image at bottom
        if char_data.get('image'):
            embed.set_image(url=char_data['image'])
        
        embed.set_footer(text="Use !wish to summon this Servant | Use !mci to see your owned card")
        await send_embed(ctx, embed)


async def setup(bot):
    await bot.add_cog(CardLevel(bot))
