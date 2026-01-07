import random

import discord
from discord.ext import commands

from utils.constants import (
    EXP_TUNING,
    FISHING_MIN_LEVEL,
    fish_pool,
    fish_rarity_weights,
    regions,
)
from utils.database import (
    _exp_required_for_level,
    add_account_exp,
    add_chest_with_type,
    add_fish_caught,
    add_fish_pet,
    add_user_item,
    award_achievement,
    get_account_level,
    get_fish_count_by_rarity,
    get_rod_catch_bonus,
    get_rod_level,
    get_total_fish_caught,
    get_user_data,
    get_user_fish_pets,
    get_user_item_count,
    get_user_pulls,
    level_up_fish_pet,
    update_user_data,
    upgrade_rod,
    require_enrollment,
)
from utils.embed import send_embed


class Fishing(commands.Cog):
    """Fishing mini-game. Locked until a minimum account level (default 5).

    Usage: `!fish <character> <region>` (character name can have spaces)
    The command mirrors `!dispatch` argument order: character first, then region.
    If a character is provided and is from the same region, the user receives a same-region bonus.
    """

    def __init__(self, bot):
        self.bot = bot
        # Track fishing cooldowns per user: {user_id: {'last_fish': datetime, 'cooldown_seconds': int}}
        self._fish_cooldowns = {}

    @commands.command(name="fish")
    async def fish(self, ctx, *args):
        if not await require_enrollment(ctx):
            return
        from datetime import datetime

        # Check for cooldown clear command (owner only)
        if args and args[0].lower() == "ccd":
            from config import OWNER_ID

            if ctx.author.id != OWNER_ID:
                await ctx.send(
                    "<a:X_:1437951830393884788> You don't have permission to use this command."
                )
                return

            # Reset cooldown for the user
            if ctx.author.id in self._fish_cooldowns:
                del self._fish_cooldowns[ctx.author.id]
            await ctx.send("Fishing cooldown has been reset!")
            return

        # Check account level first (get_account_level returns (level, exp, needed))
        lvl, exp, needed = await get_account_level(ctx.author.id)

        # If no args provided, show usage instructions as an embed
        if not args:
            embed = discord.Embed(title="Fishing Guide", color=0x1ABC9C)

            # Show level requirement if not met
            if lvl < FISHING_MIN_LEVEL:
                embed.color = 0xE74C3C
                embed.title = "🔒 Fishing Locked"
                embed.description = f"Fishing is unlocked after reaching **level {FISHING_MIN_LEVEL}**.\nYour current level: **{lvl}**"
                try:
                    remaining_exp = max(0, (await _exp_required_for_level(lvl)) - exp)
                    total_exp = remaining_exp
                    for level in range(lvl + 1, FISHING_MIN_LEVEL):
                        total_exp += await _exp_required_for_level(level)
                    embed.add_field(
                        name="EXP Needed",
                        value=f"{total_exp:,} EXP to reach level {FISHING_MIN_LEVEL}",
                        inline=False,
                    )
                except Exception:
                    pass
                embed.set_footer(
                    text="Gain EXP by wishing, opening chests, and completing dispatches!"
                )
            else:
                embed.add_field(
                    name="Usage", value="`!fish <character> <region>`", inline=False
                )
                embed.add_field(
                    name="Examples",
                    value="`!fish Artoria fuyuki`\n`!fish Gilgamesh camelot`",
                    inline=False,
                )

            await send_embed(ctx, embed)
            return

        # Parse args: last token is the region, the rest (joined) is the character name
        character = " ".join(args[:-1]).strip() if len(args) > 1 else None
        region = args[-1].strip() if args else None

        if region is None:
            await ctx.send(
                "Usage: `!fish <servant> <singularity>`\nExample: `!fish Artoria fuyuki`"
            )
            return

        region_key = (region or "").strip().lower()
        if region_key not in regions:
            await ctx.send(f"Unknown region `{region}`. Use `!map` to view regions.")
            return

        region_info = regions[region_key]
        region_level = int(region_info.get("level", 0))

        # Calculate cooldown based on region level (base 5 minutes + 10 minutes per region level)
        # Level 0 = 5 min, Level 1 = 15 min, Level 2 = 25 min, etc.
        cooldown_seconds = 300 + (region_level * 600)

        # Check cooldown
        if ctx.author.id in self._fish_cooldowns:
            last_fish_data = self._fish_cooldowns[ctx.author.id]
            last_fish_time = last_fish_data["last_fish"]
            last_cooldown = last_fish_data["cooldown_seconds"]

            time_since = (datetime.utcnow() - last_fish_time).total_seconds()

            if time_since < last_cooldown:
                time_left = last_cooldown - time_since
                from utils.embed import create_progress_bar, format_time_remaining

                # Calculate progress (time elapsed vs total cooldown)
                time_elapsed = time_since
                progress_bar = create_progress_bar(
                    time_elapsed, last_cooldown, segments=15
                )
                time_msg = format_time_remaining(time_left)

                await ctx.send(
                    f"🎣 Fishing Cooldown\n`{progress_bar}`\n{time_msg} remaining"
                )
                return

        # check account level - show nice embed if locked
        if lvl < FISHING_MIN_LEVEL:
            embed = discord.Embed(title="🔒 Fishing Locked", color=0xE74C3C)
            embed.description = f"Fishing is unlocked after reaching **level {FISHING_MIN_LEVEL}**.\nYour current level: **{lvl}**"
            try:
                remaining_exp = max(0, (await _exp_required_for_level(lvl)) - exp)
                total_exp = remaining_exp
                for level in range(lvl + 1, FISHING_MIN_LEVEL):
                    total_exp += await _exp_required_for_level(level)
                embed.add_field(
                    name="EXP Needed",
                    value=f"{total_exp:,} EXP to reach level {FISHING_MIN_LEVEL}",
                    inline=False,
                )
            except Exception:
                pass
            embed.set_footer(
                text="Gain EXP by wishing, opening chests, and completing dispatches!"
            )
            await send_embed(ctx, embed)
            return

        # enforce per-region unlock level
        if lvl < region_level:
            # compute approximate EXP remaining to reach that region level (sum per-level requirements)
            try:
                # remaining to next level
                remaining_to_next = max(0, (await _exp_required_for_level(lvl)) - exp)
                total_needed = remaining_to_next
                # add full level requirements for intervening levels
                for level in range(lvl + 1, region_level):
                    total_needed += await _exp_required_for_level(level)
            except Exception:
                total_needed = None

            title = f"🔒 Region Locked: {region_info.get('name')}"
            desc = f"This region requires account level {region_level} to fish. Your level: {lvl}."
            if total_needed is not None:
                desc += f"\nEstimated EXP needed to unlock: {total_needed:,}."
            embed = discord.Embed(title=title, color=0xE67E22)
            embed.description = desc
            embed.set_footer(
                text="Gain EXP by completing wishes and activities to unlock new regions."
            )
            await send_embed(ctx, embed)
            return

        # optional character same-region bonus (character may be None)
        same_region_bonus = False
        found = None
        character_display_name = None
        if character:
            pulls = await get_user_pulls(ctx.author.id)
            for p in pulls:
                name = (p[0] or "").strip().lower()
                if name == character.strip().lower():
                    found = p
                    # Store the proper case name from the database for display
                    character_display_name = p[0].strip()
                    break
            if not found:
                await ctx.send(
                    "You don't own that character to use for a fishing bonus."
                )
                return
            # determine card's region via city_lookup in constants if present, else assume no bonus
            try:
                from utils.constants import city_lookup

                card_region = city_lookup.get(found[0], "").strip().lower()
                if card_region and card_region == region_info["name"].strip().lower():
                    same_region_bonus = True
            except Exception:
                same_region_bonus = False

        # compute base rewards
        base_mora = max(50, 150 * max(1, region_level))
        mora_variance = random.uniform(0.85, 1.25)
        mora_reward = int(base_mora * mora_variance)

        # Check if user has fish bait active
        bait_count = await get_user_item_count(ctx.author.id, "fish_bait")
        using_bait = bait_count > 0

        # Get rod level and bonuses
        rod_level = await get_rod_level(ctx.author.id)
        rod_bonuses = get_rod_catch_bonus(rod_level)

        # Fish catch chance: 15% base, 25% with 5★ same-region bonus, + rod catch rate bonus
        base_catch = (
            0.25 if (same_region_bonus and found and found[1] == "5★") else 0.15
        )
        fish_catch_chance = min(
            0.95, base_catch + rod_bonuses["catch_rate_bonus"]
        )  # Cap at 95%

        # Fish bait gives guaranteed catch
        if using_bait:
            fish_catch_chance = 1.0  # 100% catch rate with bait

        # Try to catch a fish
        caught_fish = None
        if random.random() < fish_catch_chance:
            # Determine rarity based on weights with rod bonuses and bait
            # Apply bonuses by adjusting weights temporarily
            adjusted_weights = fish_rarity_weights.copy()
            adjusted_weights["Rare"] = min(
                0.40, adjusted_weights["Rare"] + rod_bonuses["rare_chance_bonus"]
            )
            adjusted_weights["Mythic"] = min(
                0.15, adjusted_weights["Mythic"] + rod_bonuses["mythic_chance_bonus"]
            )

            # Fish bait increases rare/mythic chances significantly
            if using_bait:
                adjusted_weights["Rare"] = min(
                    0.50, adjusted_weights["Rare"] + 0.15
                )  # +15% rare
                adjusted_weights["Mythic"] = min(
                    0.20, adjusted_weights["Mythic"] + 0.08
                )  # +8% mythic

            # Recalculate Common to maintain total = 1.0
            adjusted_weights["Common"] = (
                1.0 - adjusted_weights["Rare"] - adjusted_weights["Mythic"]
            )

            rand = random.random()
            cumulative = 0.0
            selected_rarity = None
            for rarity, weight in adjusted_weights.items():
                cumulative += weight
                if rand < cumulative:
                    selected_rarity = rarity
                    break

            # Select random fish of that rarity
            if selected_rarity:
                rarity_pool = [f for f in fish_pool if f["rarity"] == selected_rarity]
                if rarity_pool:
                    caught_fish = random.choice(rarity_pool)
                    # Track the caught fish
                    try:
                        await add_fish_caught(ctx.author.id, caught_fish["name"], 1)
                        # Add fish as a pet
                        await add_fish_pet(ctx.author.id, caught_fish["name"])
                    except Exception:
                        pass

        # Consume fish bait if used
        if using_bait:
            try:
                await add_user_item(ctx.author.id, "fish_bait", -1)
            except Exception:
                pass

        # Award Hydro Essence if fishing in Fontaine (20% chance)
        awarded_hydro_essence = 0
        if region_info["name"].strip().lower() == "fontaine":
            hydro_chance = 0.20
            if random.random() < hydro_chance:
                essence_amount = random.randint(1, 3)  # Award 1-3 hydro essence
                try:
                    await add_user_item(ctx.author.id, "hydro_essence", essence_amount)
                    awarded_hydro_essence = essence_amount
                except Exception:
                    awarded_hydro_essence = 0

        # Common chest chances: 50% base, 75% with bonus character
        common_chest_chance = 0.75 if same_region_bonus else 0.50

        # EXP bottle chances: 5% base, 8% with bonus character
        exp_bottle_chance = 0.08 if same_region_bonus else 0.05

        # Fate chances (keep existing logic)
        fate_chance = min(0.10, 0.01 * region_level)
        if same_region_bonus:
            fate_chance = min(0.25, fate_chance * 2.0)

        # Award common chest
        awarded_chest = 0
        if random.random() < common_chest_chance:
            try:
                await add_chest_with_type(ctx.author.id, "common", 1)
                awarded_chest = 1
            except Exception:
                awarded_chest = 0

        # Award EXP bottle
        awarded_exp_bottles = 0
        if random.random() < exp_bottle_chance:
            try:
                from utils.database import add_user_item as award_item

                await award_item(ctx.author.id, "exp_bottle", 1)
                awarded_exp_bottles = 1
            except Exception:
                awarded_exp_bottles = 0

        awarded_fate = 0
        if random.random() < fate_chance:
            # award 1 fate
            data = await get_user_data(ctx.author.id)
            await update_user_data(ctx.author.id, fates=data.get("fates", 0) + 1)
            awarded_fate = 1

        # award mora
        data = await get_user_data(ctx.author.id)
        await update_user_data(ctx.author.id, mora=data.get("mora", 0) + mora_reward)

        # award account EXP for fishing (region-based)
        fishing_exp = 0
        try:
            fishing_exp = int(
                EXP_TUNING.get("dispatch_per_region_level", 10) * max(1, region_level)
            )
            if fishing_exp > 0:
                await add_account_exp(ctx.author.id, fishing_exp, source="fishing")
        except Exception:
            # non-fatal; proceed without blocking the fishing result
            fishing_exp = 0

        # build result embed with stacked reward lines
        # Set color based on fish rarity if caught
        if caught_fish:
            if caught_fish["rarity"] == "Mythic":
                embed_color = 0xFFD700  # Gold for Mythic
            elif caught_fish["rarity"] == "Rare":
                embed_color = 0x9B59B6  # Purple for Rare
            else:
                embed_color = 0x95A5A6  # Gray for Common
        else:
            embed_color = 0x1ABC9C  # Default teal

        # Build the title
        if character_display_name:
            embed_title = f"{character_display_name} caught:"
        else:
            embed_title = "You caught:"

        embed = discord.Embed(title=embed_title, color=embed_color)

        # Build rewards description
        rewards_lines = []
        rewards_lines.append(f"<:mora:1437958309255577681> {mora_reward:,} Mora")

        # Show caught fish first if any
        if caught_fish:
            rarity_text = f"**{caught_fish['rarity']}**"
            rewards_lines.append(
                f"{caught_fish['icon']} {caught_fish['name']} ({rarity_text})"
            )

        if awarded_chest > 0:
            chest_text = (
                f"{awarded_chest} **Common** Chest"
                if awarded_chest == 1
                else f"{awarded_chest} **Common** Chests"
            )
            rewards_lines.append(
                f"<:cajitadelexplorador:1437473147833286676> {chest_text}"
            )
        if awarded_exp_bottles > 0:
            rewards_lines.append("EXP Bottle")
        if awarded_fate:
            rewards_lines.append("Intertwined Fate")
        if awarded_hydro_essence > 0:
            rewards_lines.append(
                f"<:essence:1437463601479942385> {awarded_hydro_essence} Hydro Essence"
            )

        embed.description = "\n".join(rewards_lines)

        # Add region info in footer
        embed.set_footer(text=f"Fished in {region_info['name']}")

        # Combine bonus info: same-region, EXP, rod level, and bait as a field
        bonus_parts = []
        if same_region_bonus:
            bonus_parts.append("Same-region bonus applied")
        if rod_level > 1:
            bonus_parts.append(
                f"<:rod:1442164146287411291> Rod Level {rod_level} (+{int(rod_bonuses['catch_rate_bonus'] * 100)}% catch, +{int(rod_bonuses['rare_chance_bonus'] * 100)}% rare, +{int(rod_bonuses['mythic_chance_bonus'] * 100)}% mythic)"
            )
        if using_bait:
            bonus_parts.append("🪱 Fish Bait (100% catch, +15% rare, +8% mythic)")
        if fishing_exp and fishing_exp > 0:
            bonus_parts.append(f"+{fishing_exp:,} EXP")
        if bonus_parts:
            embed.add_field(name="Bonus", value="\n".join(bonus_parts), inline=False)

        # Check and award fishing achievements
        try:
            # First fish ever
            await award_achievement(
                ctx.author.id,
                "first_fish",
                "First Cast",
                "You fished for the first time.",
            )

            # Check if caught first fish (not just fished)
            if caught_fish:
                total_fish = await get_total_fish_caught(ctx.author.id)
                if total_fish == 1:
                    await award_achievement(
                        ctx.author.id,
                        "first_fish_caught",
                        "Angler",
                        "You caught your first fish!",
                    )

                # Check collection achievements
                common_count = await get_fish_count_by_rarity(ctx.author.id, "Common")
                rare_count = await get_fish_count_by_rarity(ctx.author.id, "Rare")
                mythic_count = await get_fish_count_by_rarity(ctx.author.id, "Mythic")

                if common_count >= 10:
                    await award_achievement(
                        ctx.author.id,
                        "all_common_fish",
                        "Common Collector",
                        "Caught all common fish!",
                    )
                if rare_count >= 12:
                    await award_achievement(
                        ctx.author.id,
                        "all_rare_fish",
                        "Rare Hunter",
                        "Caught all rare fish!",
                    )
                if mythic_count >= 8:
                    await award_achievement(
                        ctx.author.id,
                        "all_mythic_fish",
                        "Mythic Master",
                        "Caught all mythic fish!",
                    )

                # Complete encyclopedia achievement
                if common_count >= 10 and rare_count >= 12 and mythic_count >= 8:
                    await award_achievement(
                        ctx.author.id,
                        "fish_master",
                        "Fish Encyclopedia",
                        "Caught every single fish in Teyvat!",
                    )

                # Milestone achievements
                if total_fish >= 10:
                    await award_achievement(
                        ctx.author.id,
                        "fish_10",
                        "Novice Angler",
                        "Caught 10 fish total.",
                    )
                if total_fish >= 50:
                    await award_achievement(
                        ctx.author.id,
                        "fish_50",
                        "Experienced Angler",
                        "Caught 50 fish total.",
                    )
                if total_fish >= 100:
                    await award_achievement(
                        ctx.author.id,
                        "fish_100",
                        "Master Angler",
                        "Caught 100 fish total.",
                    )

                # Special achievement for mythic fish
                if caught_fish["rarity"] == "Mythic":
                    await award_achievement(
                        ctx.author.id,
                        "first_mythic",
                        "Mythic Catch",
                        "You caught your first mythic fish!",
                    )
        except Exception:
            pass

        # Set the cooldown for this user after successful fishing
        self._fish_cooldowns[ctx.author.id] = {
            "last_fish": datetime.utcnow(),
            "cooldown_seconds": cooldown_seconds,
        }
        
        # Update quest progress if a fish was caught
        if caught_fish:
            try:
                quests_cog = self.bot.get_cog('Quests')
                if quests_cog:
                    await quests_cog.update_quest_progress(ctx.author.id, 'fish', 1)
            except:
                pass

        await send_embed(ctx, embed)

    @commands.command(name="fishbook", aliases=["fishcollection", "fb", "pets"])
    async def fishbook(self, ctx):
        """View your fish pets and their levels."""
        if not await require_enrollment(ctx):
            return
        # Get all user's fish pets
        pets = await get_user_fish_pets(ctx.author.id)

        if not pets:
            embed = discord.Embed(title="🐟 No Fish Pets", color=0xE74C3C)
            embed.description = "You haven't caught any fish yet! Use `!fish <character> <region>` to start fishing."
            embed.set_footer(
                text="Fish in Fontaine to get Hydro Essence for leveling pets!"
            )
            await send_embed(ctx, embed)
            return

        # Group pets by rarity
        common_pets = []
        rare_pets = []
        mythic_pets = []

        for pet in pets:
            fish_info = None
            for f in fish_pool:
                if f["name"] == pet["fish_name"]:
                    fish_info = f
                    break

            if fish_info:
                pet_display = {
                    "id": pet["id"],
                    "name": pet["fish_name"],
                    "level": pet["level"],
                    "icon": fish_info["icon"],
                    "rarity": fish_info["rarity"],
                }

                if fish_info["rarity"] == "Common":
                    common_pets.append(pet_display)
                elif fish_info["rarity"] == "Rare":
                    rare_pets.append(pet_display)
                elif fish_info["rarity"] == "Mythic":
                    mythic_pets.append(pet_display)

        embed = discord.Embed(
            title=f"🐟 {ctx.author.display_name}'s Fish Pets", color=0x3498DB
        )
        embed.set_thumbnail(url=getattr(ctx.author, "display_avatar", ctx.author).url)

        # Summary
        total_pets = len(pets)
        total_levels = sum(p["level"] for p in pets)
        embed.add_field(
            name="Overview",
            value=f"**Total Pets:** {total_pets}\n**Total Levels:** {total_levels}\n**Common:** {len(common_pets)} | **Rare:** {len(rare_pets)} | **Mythic:** {len(mythic_pets)}",
            inline=False,
        )

        # Show common pets
        if common_pets:
            common_lines = []
            for pet in common_pets[:10]:  # Limit to 10 to avoid embed length issues
                common_lines.append(
                    f"{pet['icon']} **{pet['name']}** - Lv.{pet['level']}"
                )
            if len(common_pets) > 10:
                common_lines.append(f"... and {len(common_pets) - 10} more")
            embed.add_field(
                name="⭐ Common Pets", value="\n".join(common_lines), inline=False
            )

        # Show rare pets
        if rare_pets:
            rare_lines = []
            for pet in rare_pets[:10]:
                rare_lines.append(
                    f"{pet['icon']} **{pet['name']}** - Lv.{pet['level']}"
                )
            if len(rare_pets) > 10:
                rare_lines.append(f"... and {len(rare_pets) - 10} more")
            embed.add_field(
                name="⭐⭐ Rare Pets", value="\n".join(rare_lines), inline=False
            )

        # Show mythic pets
        if mythic_pets:
            mythic_lines = []
            for pet in mythic_pets:
                mythic_lines.append(
                    f"{pet['icon']} **{pet['name']}** - Lv.{pet['level']}"
                )
            embed.add_field(
                name="⭐⭐⭐ Mythic Pets", value="\n".join(mythic_lines), inline=False
            )

        # Show crafting materials
        try:
            essence_count = await get_user_item_count(ctx.author.id, "hydro_essence")
            crystal_count = await get_user_item_count(ctx.author.id, "hydro_crystal")
            embed.add_field(
                name="Materials",
                value=f"<:essence:1437463601479942385> Hydro Essence: {essence_count}\n<:crystal:1437458982989205624> Hydro Crystals: {crystal_count}",
                inline=False,
            )
        except Exception:
            pass

        embed.set_footer(
            text="Use !levelpet <name> to level up a pet - Use !mp <name> to view a pet - Fish in Fontaine for Hydro Essence!"
        )
        await send_embed(ctx, embed)

    @commands.command(name="mp", aliases=["mypet", "petinfo"])
    async def my_pet(self, ctx, *, pet_name: str | None = None):
        """View detailed information about a specific pet.
        Usage: !mp <pet_name>
        Example: !mp Medaka
        """
        if not pet_name:
            await ctx.send(
                "Please specify a pet name. Example: `!mp Medaka`\nUse `!fishbook` to see all your pets."
            )
            return

        # Get user's pets
        pets = await get_user_fish_pets(ctx.author.id)

        if not pets:
            await ctx.send(
                "<a:X_:1437951830393884788> You don't have any pets yet! Use `!fish` to catch fish."
            )
            return

        # Find all pets matching the name (case-insensitive)
        matching_pets = [p for p in pets if p["fish_name"].lower() == pet_name.lower()]

        if not matching_pets:
            await ctx.send(
                f"You don't have a pet named **{pet_name}**. Use `!fishbook` to see your pets."
            )
            return

        # Get fish info
        fish_name = matching_pets[0]["fish_name"]
        fish_info = None
        for f in fish_pool:
            if f["name"] == fish_name:
                fish_info = f
                break

        if not fish_info:
            await ctx.send("Error: Could not find fish information.")
            return

        # Count total pets of this type
        total_count = len(matching_pets)

        # Calculate total levels and average level
        total_levels = sum(p["level"] for p in matching_pets)
        avg_level = total_levels / total_count if total_count > 0 else 0

        # Find highest level
        max_level_pet = max(matching_pets, key=lambda p: p["level"])

        # Crystal cost for next level
        rarity = fish_info["rarity"]
        if rarity == "Common":
            crystals_needed = 1
        elif rarity == "Rare":
            crystals_needed = 2
        elif rarity == "Mythic":
            crystals_needed = 3
        else:
            crystals_needed = 1

        # Build embed
        embed = discord.Embed(title=f"{fish_info['icon']} {fish_name}", color=0x3498DB)
        embed.set_thumbnail(url=getattr(ctx.author, "display_avatar", ctx.author).url)

        # Stats
        embed.add_field(name="Rarity", value=rarity, inline=True)
        embed.add_field(name="Region", value=fish_info["region"], inline=True)
        embed.add_field(name="Owned", value=f"{total_count}x", inline=True)

        embed.add_field(name="Total Levels", value=f"{total_levels}", inline=True)
        embed.add_field(name="Average Level", value=f"{avg_level:.1f}", inline=True)
        embed.add_field(
            name="Highest Level", value=f"Lv.{max_level_pet['level']}", inline=True
        )

        # Level up cost
        embed.add_field(
            name="Level Up Cost",
            value=f"{crystals_needed} <:crystal:1437458982989205624> Hydro Crystal",
            inline=False,
        )

        # Show individual pets if there are multiple
        if total_count > 1:
            pet_lines = []
            for i, pet in enumerate(
                sorted(matching_pets, key=lambda p: p["level"], reverse=True)[:5], 1
            ):
                caught_date = pet.get("caught_at", "Unknown")
                if caught_date and caught_date != "Unknown":
                    try:
                        from datetime import datetime

                        dt = datetime.fromisoformat(caught_date)
                        caught_str = dt.strftime("%b %d, %Y")
                    except Exception:
                        caught_str = "Unknown"
                else:
                    caught_str = "Unknown"
                pet_lines.append(f"**#{i}** - Lv.{pet['level']} (Caught: {caught_str})")

            if total_count > 5:
                pet_lines.append(f"... and {total_count - 5} more")

            embed.add_field(name="Your Pets", value="\n".join(pet_lines), inline=False)
        else:
            # Single pet - show caught date
            caught_date = max_level_pet.get("caught_at", "Unknown")
            if caught_date and caught_date != "Unknown":
                try:
                    from datetime import datetime

                    dt = datetime.fromisoformat(caught_date)
                    caught_str = dt.strftime("%B %d, %Y at %I:%M %p")
                except Exception:
                    caught_str = caught_date
            else:
                caught_str = "Unknown"
            embed.add_field(name="Caught On", value=caught_str, inline=False)

        await send_embed(ctx, embed)

    @commands.command(name="craft")
    async def craft(self, ctx, item: str | None = None, amount: int = 1):
        """Craft Hydro Crystals from Hydro Essence.
        Usage: !craft hydro_crystal <amount>
        Cost: 5 Hydro Essence per 1 Hydro Crystal
        """
        if not item or item.lower() not in ["hydro_crystal", "crystal"]:
            embed = discord.Embed(title="💎 Crafting", color=0x3498DB)
            embed.description = "Craft **Hydro Crystals** to level up your fish pets!"
            embed.add_field(
                name="Recipe",
                value="5 <:essence:1437463601479942385> Hydro Essence → 1 <:crystal:1437458982989205624> Hydro Crystal",
                inline=False,
            )
            embed.add_field(
                name="Usage", value="`!craft hydro_crystal <amount>`", inline=False
            )
            embed.set_footer(
                text="Hydro Essence can be obtained from fishing or dispatches in Fontaine!"
            )
            await send_embed(ctx, embed)
            return

        if amount < 1:
            await ctx.send("Amount must be at least 1.")
            return

        # Check if user has enough essence
        from utils.database import get_user_item_count

        essence_count = await get_user_item_count(ctx.author.id, "hydro_essence")
        essence_needed = amount * 5

        if essence_count < essence_needed:
            await ctx.send(
                f"<a:X_:1437951830393884788> You don't have enough Hydro Essence. You need {essence_needed} but only have {essence_count}."
            )
            return

        # Craft the crystals
        try:
            await add_user_item(ctx.author.id, "hydro_essence", -essence_needed)
            await add_user_item(ctx.author.id, "hydro_crystal", amount)

            embed = discord.Embed(title="Crafting Successful", color=0x2ECC71)
            embed.description = f"You crafted **{amount}** <:crystal:1437458982989205624> Hydro Crystal{'s' if amount > 1 else ''}!"
            embed.add_field(
                name="Materials Used",
                value=f"-{essence_needed} <:essence:1437463601479942385> Hydro Essence",
                inline=False,
            )
            crystal_count = await get_user_item_count(ctx.author.id, "hydro_crystal")
            embed.set_footer(text=f"You now have {crystal_count} Hydro Crystal(s)")
            await send_embed(ctx, embed)
        except Exception as e:
            await ctx.send(f"Failed to craft: {e}")

    @commands.command(name="upgraderod", aliases=["rodupgrade", "uprod"])
    async def upgrade_rod_cmd(self, ctx):
        """Upgrade your fishing rod using Rod Shards.

        Better rods increase catch rates and improve chances of catching rare/mythic fish.
        Cost: 5 Rod Shards × current rod level

        Rod Shards can be obtained from chests and the shop.
        """
        # Get current rod level
        rod_level = await get_rod_level(ctx.author.id)

        # Calculate cost for next level
        cost = 5 * rod_level

        # Check current shard count
        shard_count = await get_user_item_count(ctx.author.id, "rod_shard")

        if shard_count < cost:
            embed = discord.Embed(
                title="<:rod:1442164146287411291> Fishing Rod Upgrade", color=0xE74C3C
            )
            embed.description = "Not enough Rod Shards to upgrade!"
            embed.add_field(
                name="Current Rod Level",
                value=f"<a:Trophy:1438199339586424925> Level {rod_level}",
                inline=False,
            )
            embed.add_field(
                name="Upgrade Cost", value=f"🔧 {cost} Rod Shards", inline=True
            )
            embed.add_field(
                name="Your Shards", value=f"🔧 {shard_count} Rod Shards", inline=True
            )
            embed.add_field(
                name="Need", value=f"🔧 {cost - shard_count} more shards", inline=True
            )
            await send_embed(ctx, embed)
            return

        # Perform upgrade
        result = await upgrade_rod(ctx.author.id)

        if result["success"]:
            new_level = result["new_level"]
            bonuses = get_rod_catch_bonus(new_level)

            embed = discord.Embed(title="Rod Upgraded", color=0x2ECC71)
            embed.description = (
                "<:rod:1442164146287411291> Your fishing rod has been upgraded!"
            )
            embed.add_field(
                name="Level", value=f"{result['old_level']} → {new_level}", inline=True
            )
            embed.add_field(name="Cost", value=f"🔧 -{cost} Rod Shards", inline=True)
            embed.add_field(
                name="Remaining Shards", value=f"🔧 {shard_count - cost}", inline=True
            )

            # Show new bonuses
            bonuses_text = (
                f"**Catch Rate:** +{int(bonuses['catch_rate_bonus'] * 100)}%\n"
                f"**Rare Chance:** +{int(bonuses['rare_chance_bonus'] * 100)}%\n"
                f"**Mythic Chance:** +{int(bonuses['mythic_chance_bonus'] * 100)}%"
            )
            embed.add_field(name="New Bonuses", value=bonuses_text, inline=False)

            # Calculate next upgrade cost
            next_cost = 5 * new_level
            embed.set_footer(
                text=f"Next upgrade: {next_cost} Rod Shards (Level {new_level} → {new_level + 1})"
            )
            await send_embed(ctx, embed)
        else:
            await ctx.send("Failed to upgrade rod. Please try again.")

    @commands.command(name="rod", aliases=["rodinfo", "myrod"])
    async def rod_info(self, ctx):
        """View your current fishing rod level and bonuses."""
        rod_level = await get_rod_level(ctx.author.id)
        bonuses = get_rod_catch_bonus(rod_level)
        shard_count = await get_user_item_count(ctx.author.id, "rod_shard")

        embed = discord.Embed(
            title="<:rod:1442164146287411291> Your Fishing Rod", color=0x3498DB
        )
        embed.add_field(
            name="Level",
            value=f"<a:Trophy:1438199339586424925> {rod_level}",
            inline=False,
        )

        # Show current bonuses
        bonuses_text = (
            f"**Catch Rate:** +{int(bonuses['catch_rate_bonus'] * 100)}%\n"
            f"**Rare Chance:** +{int(bonuses['rare_chance_bonus'] * 100)}%\n"
            f"**Mythic Chance:** +{int(bonuses['mythic_chance_bonus'] * 100)}%"
        )
        embed.add_field(name="Current Bonuses", value=bonuses_text, inline=False)

        # Show upgrade info
        upgrade_cost = 5 * rod_level
        embed.add_field(
            name="Upgrade Cost", value=f"🔧 {upgrade_cost} Rod Shards", inline=True
        )
        embed.add_field(name="Your Shards", value=f"🔧 {shard_count}", inline=True)

        can_upgrade = (
            "✅ Ready to upgrade!"
            if shard_count >= upgrade_cost
            else f"❌ Need {upgrade_cost - shard_count} more"
        )
        embed.add_field(name="Status", value=can_upgrade, inline=False)

        await send_embed(ctx, embed)

    @commands.command(name="levelpet", aliases=["feedpet", "levelfish"])
    async def level_pet(self, ctx, *, pet_name: str | None = None):
        """Level up a fish pet using Hydro Crystals.
        Usage: !levelpet <pet_name>

        Crystal cost based on rarity:
        - Common: 1 crystal
        - Rare: 2 crystals
        - Mythic: 3 crystals

        Use !fishbook to see your pets and their names.
        """
        if pet_name is None:
            embed = discord.Embed(title="🐟 Level Up Fish Pet", color=0x3498DB)
            embed.description = "Level up your fish pets using Hydro Crystals!"
            embed.add_field(
                name="Crystal Cost",
                value="Common: 1 <:crystal:1437458982989205624>\nRare: 2 <:crystal:1437458982989205624>\nMythic: 3 <:crystal:1437458982989205624>",
                inline=False,
            )
            embed.add_field(
                name="Usage",
                value="`!levelpet <pet_name>`\nExample: `!levelpet Medaka`",
                inline=False,
            )
            await send_embed(ctx, embed)
            return

        # Get user's pets
        pets = await get_user_fish_pets(ctx.author.id)

        # Find the specified pet by name (case-insensitive)
        target_pet = None
        for pet in pets:
            if pet["fish_name"].lower() == pet_name.lower():
                target_pet = pet
                break

        if not target_pet:
            await ctx.send(
                f"You don't have a pet named **{pet_name}**. Use `!fishbook` to see your pets."
            )
            return

        # Determine crystal cost based on rarity
        fish_name = target_pet["fish_name"]
        fish_info = None
        for f in fish_pool:
            if f["name"] == fish_name:
                fish_info = f
                break

        if not fish_info:
            await ctx.send("Error: Could not find fish information.")
            return

        rarity = fish_info["rarity"]
        if rarity == "Common":
            crystals_needed = 1
        elif rarity == "Rare":
            crystals_needed = 2
        elif rarity == "Mythic":
            crystals_needed = 3
        else:
            crystals_needed = 1

        # Check if user has enough crystals
        crystal_count = await get_user_item_count(ctx.author.id, "hydro_crystal")
        if crystal_count < crystals_needed:
            await ctx.send(
                f"<a:X_:1437951830393884788> You don't have enough Hydro Crystals. You need {crystals_needed} but only have {crystal_count}."
            )
            return

        # Level up the pet (using pet ID from the matched pet)
        pet_id = target_pet["id"]
        success = await level_up_fish_pet(ctx.author.id, pet_id, crystals_needed)

        if success:
            new_level = target_pet["level"] + 1
            embed = discord.Embed(title="Pet Leveled Up", color=0x2ECC71)
            embed.description = f"{fish_info['icon']} **{fish_name}** leveled up!"
            embed.add_field(
                name="Level", value=f"{target_pet['level']} → {new_level}", inline=True
            )
            embed.add_field(name="Rarity", value=rarity, inline=True)
            embed.add_field(
                name="Crystals Used",
                value=f"-{crystals_needed} <:crystal:1437458982989205624>",
                inline=False,
            )
            remaining_crystals = crystal_count - crystals_needed
            embed.set_footer(
                text=f"You have {remaining_crystals} Hydro Crystal(s) remaining"
            )
            await send_embed(ctx, embed)
        else:
            await ctx.send("Failed to level up pet. Please try again.")


async def setup(bot):
    if bot.get_cog("Fishing") is None:
        await bot.add_cog(Fishing(bot))
    else:
        print("Fishing cog already loaded; skipping add_cog")
