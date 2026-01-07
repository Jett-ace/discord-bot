import random
import datetime
import discord
from discord.ext import commands
from utils import constants
from utils.database import (
    get_user_pulls, insert_dispatch, get_user_active_dispatches,
    get_user_ready_dispatches, mark_dispatch_claimed, get_dispatch_by_id,
    get_user_data, update_user_data, add_chest_with_type, require_enrollment
)
from utils.database import add_account_exp
from utils.database import get_account_level, _exp_required_for_level
from utils.chest_config import EXPLORE as CHEST_EXPLORE_CONFIG
from utils.embed import send_embed


def _compute_chest_awards(region_name: str, rarity: str, base_chest_flag: int):
    """Given a dispatch's region and rarity and whether a chest was rolled (base_chest_flag),
    compute which chest types and amounts to award and how many guaranteed extra fates.

    Returns: (dict[chest_type]->amount, extra_fates:int)
    """
    if not base_chest_flag:
        return {}, 0

    region = (region_name or "").strip().lower()
    awards = {"common": 0, "exquisite": 0, "precious": 0, "luxurious": 0}
    extra_fates = 0

    # Helper to maybe double amounts for high-level regions
    def maybe_double(vals):
        if random.random() < CHEST_EXPLORE_CONFIG.get("maybe_double_chance", 0.20):
            return {k: v * 2 for k, v in vals.items()}
        return vals

    if region == 'fuyuki':
        awards['common'] = 1

    elif region == 'orleans':
        # mostly common, small chance exquisite
        if random.random() < CHEST_EXPLORE_CONFIG.get("orleans_exquisite_chance", 0.20):
            awards['exquisite'] = 1
        else:
            awards['common'] = 1

    elif region in ('septem', 'okeanos', 'london'):
    # mid-tier singularities probabilities
        r = random.random()
        if r < CHEST_EXPLORE_CONFIG.get("mid_lux_threshold", 0.10):
            awards['luxurious'] = 1
        elif r < CHEST_EXPLORE_CONFIG.get("mid_precious_threshold", 0.40):
            awards['precious'] = 1
        elif r < CHEST_EXPLORE_CONFIG.get("mid_exquisite_threshold", 0.70):
            awards['exquisite'] = 1
        else:
            awards['common'] = 1
        # maybe double chest drops in mid-level singularities
        awards = maybe_double(awards)

    else:
        # Camelot/Babylonia (and any other high-tier) - best rewards
        # Guarantee precious + 1 common + 1 exquisite
        awards['precious'] += 1
        awards['common'] += 1
        awards['exquisite'] += 1
    # chance to additionally grant a luxurious chest
        if random.random() < CHEST_EXPLORE_CONFIG.get("high_lux_chance", 0.40):
            awards['luxurious'] += 1
        # maybe double all drops
        if random.random() < CHEST_EXPLORE_CONFIG.get("high_double_chance", 0.20):
            awards = maybe_double(awards)

    # Extra fate rules: precious & luxurious each guarantee 1 fate per chest
    extra_fates += awards.get('precious', 0)
    extra_fates += awards.get('luxurious', 0)
    # Each luxurious chest has an additional chance to grant +1 fate
    lux_extra = CHEST_EXPLORE_CONFIG.get("lux_extra_fate_chance", 0.20)
    for _ in range(awards.get('luxurious', 0)):
        if random.random() < lux_extra:
            extra_fates += 1
    
    # Award progression items based on chest rarity
    # Rod Shards: 5% common, 10% exquisite, 15% precious, 25% luxurious
    # Fish Bait: 10% common, 15% exquisite, 20% precious, 30% luxurious
    items = {}
    
    # Calculate rod shard drops
    rod_shard_chance = 0.05 * awards.get('common', 0) + 0.10 * awards.get('exquisite', 0) + \
                       0.15 * awards.get('precious', 0) + 0.25 * awards.get('luxurious', 0)
    if random.random() < rod_shard_chance:
        # Award 1-3 shards based on rarity
        if awards.get('luxurious', 0) > 0:
            items['rod_shard'] = random.randint(2, 4)
        elif awards.get('precious', 0) > 0:
            items['rod_shard'] = random.randint(1, 3)
        else:
            items['rod_shard'] = 1
    
    # Calculate fish bait drops
    bait_chance = 0.10 * awards.get('common', 0) + 0.15 * awards.get('exquisite', 0) + \
                  0.20 * awards.get('precious', 0) + 0.30 * awards.get('luxurious', 0)
    if random.random() < bait_chance:
        # Award 1-5 bait based on rarity
        if awards.get('luxurious', 0) > 0:
            items['fish_bait'] = random.randint(3, 5)
        elif awards.get('precious', 0) > 0:
            items['fish_bait'] = random.randint(2, 4)
        else:
            items['fish_bait'] = random.randint(1, 2)

    return awards, extra_fates, items


class Explore(commands.Cog):
    """Exploration / dispatch system.

    Commands:
    - !map : show available regions and their level
    - !dispatch <character> <region> : send a character to a region on a commission
    - !claim : claim any finished dispatches and receive rewards
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="map")
    async def _map(self, ctx):
        """Show available regions and their level."""
        try:
            embed = discord.Embed(title="🗺️ Teyvat Map", color=0x2ecc71)
            lines = []
            # attempt to fetch caller's account level so we can annotate locked regions
            try:
                acct_lvl, acct_exp, acct_needed = await get_account_level(ctx.author.id)
            except Exception:
                acct_lvl = 0

            for key, info in constants.regions.items():
                name = info.get('name')
                lvl = int(info.get('level', 0))
                if acct_lvl < lvl:
                    lines.append(f"**{name}** - Level {lvl} 🔒 (locked)")
                else:
                    lines.append(f"**{name}** - Level {lvl}")

            embed.description = "\n".join(lines)

            await send_embed(ctx, embed)
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @commands.group(name="dispatch", invoke_without_command=True)
    async def dispatch(self, ctx, *args):
        """Dispatch a Servant on a commission. Example: `!dispatch Artoria fuyuki`.

        Use `!dispatch status` to list your active dispatches.
        """
        if not await require_enrollment(ctx):
            return
        # If called without args, show usage
        if not args:
            await ctx.send("Usage: `gdispatch <character> <region>` or `gdispatch status`\nExample: `gdispatch Artoria fuyuki`")
            return

        # Parse arguments: last token is the region, the rest (joined) is the character name
        character = " ".join(args[:-1]).strip() if len(args) > 1 else None
        region = args[-1].strip() if args else None

    # If only one argument was provided, it's ambiguous - show usage
        if character is None or region is None:
            await ctx.send("Usage: `!dispatch <character> <region>`\nExample: `!dispatch Artoria fuyuki`")
            return
        try:
            # normalize inputs (case-insensitive)
            region_key = region.strip().lower()
            # accept region keys (lower-case) - constants.regions uses lower-case keys
            if region_key not in constants.regions:
                await ctx.send(f"Unknown region `{region}`. Use `!map` to see available regions.")
                return

            # check user owns the character (case-insensitive match)
            pulls = await get_user_pulls(ctx.author.id)
            # pulls rows: (character_name, rarity, count, relics, region, hp, atk)
            found = None
            for row in pulls:
                name = row[0]
                if (name or "").strip().lower() == character.strip().lower():
                    found = row
                    break

            if not found:
                await ctx.send("You don't own that character.")
                return

            # Enforce per-user active dispatch limit (max 5)
            active = await get_user_active_dispatches(ctx.author.id)
            try:
                active_count = len(active)
            except Exception:
                active_count = 0
            if active_count >= 5:
                await ctx.send("Max 5 dispatches active. Claim or cancel one first.")
                return

            # Prevent sending the same character if they already have an active dispatch
            # active rows: id, character_name, region, rarity, start, end, ...
            char_lower = (found[0] or "").strip().lower()
            for a in active:
                a_name = (a[1] or "").strip().lower()
                if a_name == char_lower:
                    await ctx.send(f"{found[0]} is already on an active dispatch and cannot be sent again until they return.")
                    return

            rarity = found[1] or "R"
            region_info = constants.regions[region_key]
            region_level = region_info['level']

            # enforce per-region unlock level based on account progression
            try:
                acct_lvl, acct_exp, _ = await get_account_level(ctx.author.id)
            except Exception:
                acct_lvl, acct_exp = 0, 0
            if acct_lvl < int(region_level):
                # compute estimated EXP required to reach region_level
                try:
                    remaining_to_next = max(0, (await _exp_required_for_level(acct_lvl)) - acct_exp)
                    total_needed = remaining_to_next
                    for level in range(acct_lvl + 1, int(region_level)):
                        total_needed += await _exp_required_for_level(level)
                except Exception:
                    total_needed = None

                title = f"🔒 Region Locked: {region_info.get('name')}"
                desc = f"This region requires account level {region_level} to dispatch. Your level: {acct_lvl}."
                if total_needed is not None:
                    desc += f"\nEstimated EXP needed to unlock: {total_needed:,}."
                embed = discord.Embed(title=title, description=desc, color=0xe67e22)
                await send_embed(ctx, embed)
                return

            # duration: region_level * 2.5 minutes (convert to seconds), minimum 2 minutes
            duration_seconds = max(120, int(region_level * 2.5 * 60))

            # same-region bonuses: if the character originates from this region, apply a duration reduction
            # and slightly increase chest probability. Use city_lookup from constants if available.
            same_region_bonus = False
            try:
                card_city = (found[0] or '').strip()
                card_region_name = constants.city_lookup.get(card_city, '').strip().lower()
                if card_region_name and card_region_name == region_info['name'].strip().lower():
                    same_region_bonus = True
            except Exception:
                same_region_bonus = False

            if same_region_bonus:
                # reduce duration by 25%
                duration_seconds = max(30, int(duration_seconds * 0.75))
            start = datetime.datetime.now()
            end = start + datetime.timedelta(seconds=duration_seconds)

            # rarity multiplier
            if rarity == 'SSR':
                rmul = 2.0
            elif rarity == 'SR':
                rmul = 1.5
            else:
                rmul = 1.0

            # Base rewards scale with region level
            base_mora = 300 * region_level
            base_dust = 8 * region_level

            # Apply rarity multiplier and small random variance
            mora_reward = int(base_mora * rmul * random.uniform(0.9, 1.2))
            dust_reward = int(base_dust * rmul * random.uniform(0.9, 1.3))

            # Intertwined Fate chance (small); reward 1 fate on success
            fate_chance = 0.02 * region_level * rmul
            fates_reward = 1 if random.random() < fate_chance else 0

            # Chest chance: base 70% plus small bonuses
            chest_base = 0.70
            chest_bonus = 0.03 * region_level + (0.05 if rmul > 1 else 0)
            if same_region_bonus:
                chest_bonus += 0.10
            chest_prob = min(0.98, chest_base + chest_bonus)
            chest_award = 1 if random.random() < chest_prob else 0

            # insert dispatch record with precomputed rewards
            await insert_dispatch(
                ctx.author.id,
                found[0],
                region_info['name'],
                rarity,
                start.isoformat(),
                end.isoformat(),
                mora_reward,
                dust_reward,
                fates_reward,
                chest_award,
            )

            # Award a small chunk of EXP immediately for starting the dispatch so users make
            # progression while their character is away. This complements the EXP awarded
            # when claiming the dispatch. Capture the awarded amount to display in the embed.
            start_exp = 0
            try:
                per_level = int(constants.EXP_TUNING.get('dispatch_per_region_level', 10))
                # give half of the per-region-level tuning immediately (rounded)
                start_exp = int(max(0, per_level * int(region_level) * 0.5))
                if start_exp > 0:
                    await add_account_exp(ctx.author.id, start_exp, source='dispatch_start')
            except Exception:
                # non-fatal; continue without blocking dispatch start
                start_exp = 0

            # Build a nice embed showing the dispatch details and initial time remaining
            # Compute remaining relative to now (initially equals total duration)
            now = datetime.datetime.now()
            remaining_seconds = max(0, int((end - now).total_seconds()))
            rem_minutes = remaining_seconds // 60
            rem_secs = remaining_seconds % 60
            rem_str = f"{rem_minutes}m {rem_secs}s"

            embed = discord.Embed(title="Dispatch Started", color=0x2ecc71)
            embed.add_field(name="Character", value=f"{found[0]}", inline=True)
            embed.add_field(name="Region", value=f"{region_info['name']}", inline=True)
            embed.add_field(name="Time Remaining", value=rem_str, inline=False)
            # Show immediate EXP awarded for starting this dispatch (if any)
            if start_exp and start_exp > 0:
                embed.add_field(name="Progress", value=f"+{start_exp:,} EXP (start)", inline=False)

            await send_embed(ctx, embed)
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Explore")
            logger.error(f"Error in dispatch command: {e}", exc_info=True)
            await ctx.send("❌ Could not start dispatch. Please try again.")

    @commands.command(name="claim")
    async def claim(self, ctx, dispatch_number: int = None):
        """Claim a finished dispatch and receive rewards.

        Usage:
        - `!claim` claims the oldest finished dispatch for the user (one at a time).
        - `!claim <number>` claims a specific finished dispatch by number from !dispatch status (e.g., !claim 2).
        """
        try:
            # Get all ready and active dispatches to create numbered list
            ready = await get_user_ready_dispatches(ctx.author.id)
            active = await get_user_active_dispatches(ctx.author.id)
            
            now = datetime.datetime.now()
            combined = []
            for r in ready:
                combined.append((r, True))
            for r in active:
                combined.append((r, False))

            # Sort by end time to match status display
            try:
                combined_sorted = sorted(combined, key=lambda t: datetime.datetime.fromisoformat(t[0][5]))
            except Exception:
                combined_sorted = combined
            
            # If a number was provided, use that
            if dispatch_number is not None:
                if dispatch_number < 1 or dispatch_number > len(combined_sorted):
                    await ctx.send("Invalid dispatch number. Use !dispatch status to see your dispatches.")
                    return
                
                row, is_ready = combined_sorted[dispatch_number - 1]  # Convert to 0-indexed
                dispatch_id = row[0]
                row = await get_dispatch_by_id(dispatch_id)
                if not row:
                    await ctx.send(f"No dispatch found with id {dispatch_id}.")
                    return
                # row: id, user_id, character_name, region, rarity, start, end, mora_reward, dust_reward, fates_reward, chest_award, claimed
                did = row[0]
                owner_id = row[1]
                if owner_id != ctx.author.id:
                    await ctx.send("You can only claim your own dispatches.")
                    return
                claimed = row[11]
                if claimed:
                    await ctx.send("That dispatch has already been claimed or cancelled.")
                    return
                end_iso = row[6]
                try:
                    end_dt = datetime.datetime.fromisoformat(end_iso)
                except Exception:
                    end_dt = None
                now = datetime.datetime.now()
                if end_dt and end_dt > now:
                    await ctx.send("That dispatch is not yet finished.")
                    return

                # extract rewards
                char_name = row[2]
                region_name = row[3]
                rarity = row[4] if len(row) > 4 else None
                mora_reward = row[7] or 0
                dust_reward = row[8] or 0
                chest_award = row[10] or 0

                # mark claimed then apply rewards
                # re-check the dispatch row just before claiming to avoid race conditions
                latest = await get_dispatch_by_id(did)
                if not latest or latest[11]:
                    await ctx.send("That dispatch has already been claimed or cancelled.")
                    return
                try:
                    end_dt = datetime.datetime.fromisoformat(latest[6])
                except Exception:
                    end_dt = None
                if end_dt and end_dt > datetime.datetime.now():
                    await ctx.send("That dispatch is not yet finished.")
                    return

                await mark_dispatch_claimed(did)
                data = await get_user_data(ctx.author.id)
                new_mora = data.get('mora', 0) + mora_reward
                new_dust = data.get('dust', 0) + dust_reward
                # compute chest-type awards and extra fates based on region
                chest_awards, extra_fates, chest_items = _compute_chest_awards(region_name, rarity, chest_award)
                # fates are only awarded from chests now (extra_fates); ignore direct fates_reward
                total_fates = data.get('fates', 0) + extra_fates
                await update_user_data(ctx.author.id, mora=new_mora, dust=new_dust, fates=total_fates)
                # award chests by type
                for ctype, amt in chest_awards.items():
                    if amt and amt > 0:
                        try:
                            await add_chest_with_type(ctx.author.id, ctype, amt)
                        except Exception:
                            print(f"Failed to award {amt}x {ctype} chest(s) to user {ctx.author.id}")
                
                # award progression items from chests
                for item_key, amt in chest_items.items():
                    if amt and amt > 0:
                        try:
                            from utils.database import add_user_item
                            await add_user_item(ctx.author.id, item_key, amt)
                        except Exception:
                            print(f"Failed to award {amt}x {item_key} to user {ctx.author.id}")

                # award account EXP for completing the dispatch (region-based)
                dispatch_exp = 0
                try:
                    # find region level from constants.regions by matching name
                    region_level = None
                    for k, info in constants.regions.items():
                        try:
                            if (info.get('name') or '').strip().lower() == (region_name or '').strip().lower() or k == (region_name or '').strip().lower():
                                region_level = int(info.get('level', 0))
                                break
                        except Exception:
                            continue
                    if region_level is None:
                        region_level = 0
                    dispatch_exp = int(region_level * 10)
                    if dispatch_exp > 0:
                        await add_account_exp(ctx.author.id, dispatch_exp, source='dispatch')
                except Exception:
                    pass

                # Update quest progress
                try:
                    quests_cog = self.bot.get_cog('Quests')
                    if quests_cog:
                        await quests_cog.update_quest_progress(ctx.author.id, 'dispatch', 1)
                except:
                    pass
                
                # Award Hydro Essence if dispatch is in Fontaine (30% chance, 2-4 essence)
                awarded_hydro_essence = 0
                if region_name and region_name.strip().lower() == 'fontaine':
                    hydro_chance = 0.30
                    if random.random() < hydro_chance:
                        essence_amount = random.randint(2, 4)
                        try:
                            from utils.database import add_user_item
                            await add_user_item(ctx.author.id, 'hydro_essence', essence_amount)
                            awarded_hydro_essence = essence_amount
                        except Exception:
                            awarded_hydro_essence = 0

                # Chest icons
                chest_icons = {
                    'common': '<:cajitadelexplorador:1437473147833286676>',
                    'exquisite': '<:cajitaplatino:1437473086571286699>',
                    'precious': '<:cajitapremium:1437473125095837779>',
                    'luxurious': '<:cajitadiamante:1437473169475764406>'
                }
                
                embed = discord.Embed(title=f"Dispatch Claimed! {char_name} returned from {region_name}", color=0x9b59b6)
                rewards_parts = []
                
                # Show progression items first if awarded
                if chest_items.get('rod_shard', 0) > 0:
                    rewards_parts.append(f"🔧 {chest_items['rod_shard']} Rod Shard(s)")
                if chest_items.get('fish_bait', 0) > 0:
                    rewards_parts.append(f"🪱 {chest_items['fish_bait']} Fish Bait")
                if mora_reward:
                    rewards_parts.append(f"<:mora:1437958309255577681> {mora_reward:,}")
                if dust_reward:
                    rewards_parts.append(f"<:mora:1437480155952975943> {dust_reward} Tide Coins")
                # build chest parts like '2x precious chests'
                chest_parts = []
                for k in ('common', 'exquisite', 'precious', 'luxurious'):
                    amt = chest_awards.get(k, 0)
                    if amt:
                        chest_word = 'chests' if amt != 1 else 'chest'
                        icon = chest_icons.get(k, '')
                        chest_parts.append(f"{icon} {amt}x {k} {chest_word}")
                if chest_parts:
                    for cp in chest_parts:
                        rewards_parts.append(cp)

                rewards_line = "\n".join(rewards_parts) if rewards_parts else "No rewards"
                embed.description = rewards_line
                # show EXP gained from completing the dispatch
                if dispatch_exp and dispatch_exp > 0:
                    embed.add_field(name="EXP", value=f"+{dispatch_exp:,} EXP", inline=False)
                # show if any fates were added via chests
                if extra_fates:
                    embed.add_field(name="Extra Fates", value=f"+{extra_fates} Intertwined Fate(s)", inline=False)
                # show hydro essence if awarded
                if awarded_hydro_essence > 0:
                    embed.add_field(name="<:essence:1437463601479942385> Hydro Essence", value=f"+{awarded_hydro_essence} Hydro Essence", inline=False)
                await send_embed(ctx, embed)
                return

            # No id provided: claim the oldest finished dispatch
            ready = await get_user_ready_dispatches(ctx.author.id)
            if not ready:
                await ctx.send("You have no finished dispatches to claim.")
                return

            # Sort ready dispatches by end time (oldest finished first)
            try:
                ready_sorted = sorted(ready, key=lambda r: datetime.datetime.fromisoformat(r[5]))
            except Exception:
                ready_sorted = ready

            # Only claim one finished dispatch at a time (the oldest finished)
            row = ready_sorted[0]
            # row: id, character_name, region, rarity, start, end, mora_reward, dust_reward, fates_reward, chest_award
            dispatch_id = row[0]
            char_name = row[1]
            region_name = row[2]
            rarity = row[3] if len(row) > 3 else None
            mora_reward = row[6] or 0
            dust_reward = row[7] or 0
            chest_award = row[9] or 0

            # re-check dispatch is still unclaimed and finished, then mark claimed
            latest = await get_dispatch_by_id(dispatch_id)
            if not latest or latest[11]:
                await ctx.send("That dispatch has already been claimed or cancelled.")
                return
            try:
                end_dt = datetime.datetime.fromisoformat(latest[6])
            except Exception:
                end_dt = None
            if end_dt and end_dt > datetime.datetime.now():
                await ctx.send("That dispatch is not yet finished.")
                return

            # re-check dispatch is still unclaimed and finished, then mark claimed
            await mark_dispatch_claimed(dispatch_id)

            # apply rewards to user and handle chest-type awards
            data = await get_user_data(ctx.author.id)
            new_mora = data.get('mora', 0) + mora_reward
            new_dust = data.get('dust', 0) + dust_reward
            chest_awards, extra_fates, chest_items = _compute_chest_awards(region_name, rarity, chest_award)
            # fates are only awarded from chests (extra_fates)
            total_fates = data.get('fates', 0) + extra_fates
            await update_user_data(ctx.author.id, mora=new_mora, dust=new_dust, fates=total_fates)
            for ctype, amt in chest_awards.items():
                if amt and amt > 0:
                    try:
                        await add_chest_with_type(ctx.author.id, ctype, amt)
                    except Exception:
                        print(f"Failed to award {amt}x {ctype} chest(s) to user {ctx.author.id}")
            
            # award progression items from chests
            for item_key, amt in chest_items.items():
                if amt and amt > 0:
                    try:
                        from utils.database import add_user_item
                        await add_user_item(ctx.author.id, item_key, amt)
                    except Exception:
                        print(f"Failed to award {amt}x {item_key} to user {ctx.author.id}")

            # award account EXP for completing the dispatch (region-based)
            dispatch_exp = 0
            try:
                # find region level from constants.regions by matching name
                region_level = None
                for k, info in constants.regions.items():
                    try:
                        if (info.get('name') or '').strip().lower() == (region_name or '').strip().lower() or k == (region_name or '').strip().lower():
                            region_level = int(info.get('level', 0))
                            break
                    except Exception:
                        continue
                if region_level is None:
                    region_level = 0
                dispatch_exp = int(region_level * 10)
                if dispatch_exp > 0:
                    await add_account_exp(ctx.author.id, dispatch_exp, source='dispatch')
            except Exception:
                pass

            # Award Hydro Essence if dispatch is in Fontaine (30% chance, 2-4 essence)
            awarded_hydro_essence = 0
            if region_name and region_name.strip().lower() == 'fontaine':
                hydro_chance = 0.30
                if random.random() < hydro_chance:
                    essence_amount = random.randint(2, 4)
                    try:
                        from utils.database import add_user_item
                        await add_user_item(ctx.author.id, 'hydro_essence', essence_amount)
                        awarded_hydro_essence = essence_amount
                    except Exception:
                        awarded_hydro_essence = 0

            # Chest icons
            chest_icons = {
                'common': '<:cajitadelexplorador:1437473147833286676>',
                'exquisite': '<:cajitaplatino:1437473086571286699>',
                'precious': '<:cajitapremium:1437473125095837779>',
                'luxurious': '<:cajitadiamante:1437473169475764406>'
            }
            
            # Build embed per requested format
            embed = discord.Embed(title=f"Dispatch Claimed! {char_name} returned from {region_name}", color=0x9b59b6)
            rewards_parts = []
            
            # Add progression items first
            if chest_items.get('rod_shard', 0) > 0:
                rewards_parts.append(f"🔧 {chest_items['rod_shard']} Rod Shard(s)")
            if chest_items.get('fish_bait', 0) > 0:
                rewards_parts.append(f"🪱 {chest_items['fish_bait']} Fish Bait")
            
            if mora_reward:
                rewards_parts.append(f"<:mora:1437958309255577681> {mora_reward:,}")
            if dust_reward:
                rewards_parts.append(f"<:mora:1437480155952975943> {dust_reward} Tide Coins")

            # build chest parts like '2x precious chests'
            chest_parts = []
            for k in ('common', 'exquisite', 'precious', 'luxurious'):
                amt = chest_awards.get(k, 0)
                if amt:
                    chest_word = 'chests' if amt != 1 else 'chest'
                    icon = chest_icons.get(k, '')
                    chest_parts.append(f"{icon} {amt}x {k} {chest_word}")
            if chest_parts:
                for cp in chest_parts:
                    rewards_parts.append(cp)

            rewards_line = "\n".join(rewards_parts) if rewards_parts else "No rewards"
            # Put rewards in description and details in a field
            embed.description = rewards_line
            # show EXP gained from completing the dispatch
            if dispatch_exp and dispatch_exp > 0:
                embed.add_field(name="EXP", value=f"+{dispatch_exp:,} EXP", inline=False)
            if extra_fates:
                embed.add_field(name="Extra Fates", value=f"+{extra_fates} Intertwined Fate(s)", inline=False)
            # show hydro essence if awarded
            if awarded_hydro_essence > 0:
                embed.add_field(name="<:essence:1437463601479942385> Hydro Essence", value=f"+{awarded_hydro_essence} Hydro Essence", inline=False)

            await send_embed(ctx, embed)

        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Explore")
            logger.error(f"Error in claim command: {e}", exc_info=True)
            await ctx.send("❌ Could not claim your dispatches right now. Please try again.")

    @dispatch.command(name="status")
    async def dispatch_status(self, ctx):
        """Show your active (in-progress) dispatches and remaining time."""
        try:
            # Fetch both ready (finished & unclaimed) and active (in-progress & unclaimed)
            ready = await get_user_ready_dispatches(ctx.author.id)
            active = await get_user_active_dispatches(ctx.author.id)

            if not ready and not active:
                await ctx.send("You have no active or ready dispatches.")
                return

            now = datetime.datetime.now()
            combined = []
            # normalize rows to a common structure and include a flag for ready
            # ready rows: id, character_name, region, rarity, start, end, mora_reward, dust_reward, fates_reward, chest_award
            for r in ready:
                combined.append((r, True))
            for r in active:
                combined.append((r, False))

            # sort by end time
            try:
                combined_sorted = sorted(combined, key=lambda t: datetime.datetime.fromisoformat(t[0][5]))
            except Exception:
                combined_sorted = combined

            lines = []
            for idx, (row, is_ready) in enumerate(combined_sorted, 1):
                char_name = row[1]
                region_name = row[2]
                start_iso = row[4]
                end_iso = row[5]
                # parse times
                try:
                    from utils.embed import create_progress_bar, format_time_remaining
                    
                    start_dt = datetime.datetime.fromisoformat(start_iso)
                    end_dt = datetime.datetime.fromisoformat(end_iso)
                    total = end_dt - start_dt
                    remaining = end_dt - now
                    
                    if remaining.total_seconds() < 0:
                        rem_str = "almost ready"
                        progress_bar = create_progress_bar(1.0, 1.0, segments=15)
                    else:
                        elapsed = (now - start_dt).total_seconds()
                        total_time = total.total_seconds()
                        progress_bar = create_progress_bar(elapsed, total_time, segments=15)
                        rem_str = format_time_remaining(remaining.total_seconds())
                except Exception:
                    rem_str = "unknown"
                    progress_bar = "▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱"

                if is_ready or (end_dt and end_dt <= now):
                    # ready to claim
                    lines.append(f"**{idx}.** {char_name} in {region_name}\n`{progress_bar}`\n<a:Check:1437951818452832318> Ready to claim!")
                else:
                    lines.append(f"**{idx}.** {char_name} in {region_name}\n`{progress_bar}`\n⏳ {rem_str}")

            embed = discord.Embed(title="Dispatches", description="\n".join(lines), color=0x3498db)
            await send_embed(ctx, embed)
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Explore")
            logger.error(f"Error in dispatch status: {e}", exc_info=True)
            await ctx.send("❌ Could not fetch your dispatch status. Please try again.")

    @dispatch.command(name="cancel")
    async def dispatch_cancel(self, ctx, dispatch_id: int):
        """Cancel an active dispatch. Refunds 50% of the Mora and Tide Coin rewards (no fate/chest refunds)."""
        try:
            row = await get_dispatch_by_id(dispatch_id)
            if not row:
                await ctx.send(f"No dispatch found with id {dispatch_id}.")
                return

            # row: id, user_id, character_name, region, rarity, start, end, mora_reward, dust_reward, fates_reward, chest_award, claimed
            did = row[0]
            owner_id = row[1]
            if owner_id != ctx.author.id:
                await ctx.send("You can only cancel your own dispatches.")
                return

            claimed = row[11]
            if claimed:
                await ctx.send("That dispatch is already claimed or cancelled.")
                return

            end_iso = row[6]
            try:
                end_dt = datetime.datetime.fromisoformat(end_iso)
            except Exception:
                end_dt = None

            now = datetime.datetime.now()
            # only allow cancelling active (not finished) dispatches
            if end_dt and end_dt <= now:
                await ctx.send("This dispatch has already finished and cannot be cancelled. Claim it with `!claim`.")
                return

            mora_reward = row[7] or 0
            dust_reward = row[8] or 0

            # refund 50%
            refund_mora = int(mora_reward * 0.5)
            refund_dust = int(dust_reward * 0.5)

            # apply refund
            user_data = await get_user_data(ctx.author.id)
            new_mora = user_data.get('mora', 0) + refund_mora
            new_dust = user_data.get('dust', 0) + refund_dust
            await update_user_data(ctx.author.id, mora=new_mora, dust=new_dust)

            # mark dispatch as claimed/cancelled so it can't be claimed later
            await mark_dispatch_claimed(did)

            await ctx.send(f"Dispatch {did} cancelled. Refunded {refund_mora:,} <:mora:1437958309255577681> and {refund_dust} <:mora:1437480155952975943> Tide Coins.")
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Explore")
            logger.error(f"Error cancelling dispatch: {e}", exc_info=True)
            await ctx.send("❌ Could not cancel the dispatch. Please try again.")


async def setup(bot):
    if bot.get_cog("Explore") is None:
        await bot.add_cog(Explore(bot))
    else:
        print("Explore cog already loaded; skipping add_cog")