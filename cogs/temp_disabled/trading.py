import aiosqlite
import discord
from discord.ext import commands

from config import DB_PATH
from utils.database import (
    add_user_item,
    change_chest_type_count,
    ensure_user_db,
    get_chest_inventory,
    get_user_data,
    get_user_item_count,
    require_enrollment,
)
from utils.embed import send_embed


class Trading(commands.Cog):
    """Trading system for exchanging items between players."""

    def __init__(self, bot):
        self.bot = bot
        self.pending_trades = {}

    @commands.command(name="trade")
    async def trade(
        self, ctx, target: discord.Member = None, *, trade_details: str = None
    ):
        """Send a trade offer to another user.

        Usage: gtrade @user (my_items) (their_items)

        Format for items:
        - Chests: common_5, exquisite_2, precious_1, luxurious_1
        - Items: exp_bottle_10, essence_5, crystal_3
        - Mora: mora_10000
        - Tide Coins: tidecoins_500

        Example: gtrade @user (common_5, mora_10000) (precious_2, tidecoins_5000)
        Limit: 5 different item types per side
        """
        if not await require_enrollment(ctx):
            return
        if target is None or trade_details is None:
            embed = discord.Embed(title="Trading", color=0x3498DB)
            embed.description = "`gtrade @user (myitems_amount) (theiritems_amount)`"
            await send_embed(ctx, embed)
            return

        if target.bot:
            await ctx.send("<a:X_:1437951830393884788> You cannot trade with bots.")
            return

        if target.id == ctx.author.id:
            await ctx.send("<a:X_:1437951830393884788> You cannot trade with yourself.")
            return

        # Parse trade details
        try:
            # Extract the two offers from parentheses
            import re

            matches = re.findall(r"\(([^)]+)\)", trade_details)
            if len(matches) != 2:
                embed = discord.Embed(title="Trading", color=0x3498DB)
                embed.description = "`gtrade @user (myitems_amount) (youritems_amount)`"
                await send_embed(ctx, embed)
                return

            my_items_str = matches[0].strip()
            their_items_str = matches[1].strip()

            # Parse both offers
            my_offer = await self.parse_offer(
                ctx.author.id, my_items_str, ctx.author.display_name
            )
            their_offer = await self.parse_offer(
                target.id, their_items_str, target.display_name, validate=False
            )

            if my_offer is None or their_offer is None:
                return  # Error already sent

            # Check 5 item limit
            if self.count_items(my_offer) > 5:
                await ctx.send("You can only offer up to 5 different item types.")
                return
            if self.count_items(their_offer) > 5:
                await ctx.send("They can only receive up to 5 different item types.")
                return

            # Create trade offer
            trade_id = f"{ctx.author.id}_{target.id}_{ctx.message.id}"
            self.pending_trades[trade_id] = {
                "from": ctx.author,
                "to": target,
                "from_offer": my_offer,
                "to_offer": their_offer,
                "channel": ctx.channel,
            }

            # Create embed
            embed = discord.Embed(
                title=f"Trade Offer from {ctx.author.display_name}", color=0xE67E22
            )

            embed.add_field(
                name=f"{ctx.author.display_name} offers:",
                value=self.format_offer(my_offer),
                inline=False,
            )

            embed.add_field(
                name=f"{target.display_name} will give:",
                value=self.format_offer(their_offer),
                inline=False,
            )

            embed.set_footer(text=f"{target.display_name}, click Accept or Decline")

            # Create view with accept/decline buttons
            view = TradeOfferView(self, trade_id, target)
            await send_embed(ctx, embed, view=view)

        except Exception as e:
            print(f"Trade parsing error: {e}")
            embed = discord.Embed(title="Trading", color=0x3498DB)
            embed.description = "`!trade @user (myitems_amount) (youritems_amount)`"
            await send_embed(ctx, embed)

    async def parse_offer(self, user_id, items_str, username, validate=True):
        """Parse offer string into structured data."""
        offer = {"chests": {}, "items": {}, "mora": 0, "dust": 0}

        items_list = [item.strip() for item in items_str.split(",")]

        for item in items_list:
            if not item:
                continue

            # Split by underscore to get item and amount
            parts = item.rsplit("_", 1)
            item_name = parts[0].strip()
            amount = 1

            if len(parts) == 2:
                try:
                    amount = int(parts[1])
                except Exception:
                    amount = 1

            item_lower = item_name.lower()

            # Check for currency
            if item_lower == "mora":
                offer["mora"] += amount
                if validate:
                    data = await get_user_data(user_id)
                    if data["mora"] < offer["mora"]:
                        await self.bot.get_channel(
                            self.bot.guilds[0].text_channels[0].id
                        ).send(f"{username} doesn't have {offer['mora']:,} Mora.")
                        return None

            elif item_lower in [
                "tidecoins",
                "tidecoin",
                "tide_coins",
                "tide_coin",
                "coins",
                "coin",
            ]:
                offer["dust"] += amount
                if validate:
                    data = await get_user_data(user_id)
                    if data["dust"] < offer["dust"]:
                        await self.bot.get_channel(
                            self.bot.guilds[0].text_channels[0].id
                        ).send(f"{username} doesn't have {offer['dust']:,} Tide Coins.")
                        return None

            # Check for chests
            elif item_lower in ["common", "exquisite", "precious", "luxurious"]:
                chest_type = item_lower
                offer["chests"][chest_type] = (
                    offer["chests"].get(chest_type, 0) + amount
                )
                if validate:
                    inv = await get_chest_inventory(user_id)
                    if inv.get(chest_type, 0) < offer["chests"][chest_type]:
                        await self.bot.get_channel(
                            self.bot.guilds[0].text_channels[0].id
                        ).send(
                            f"{username} doesn't have {offer['chests'][chest_type]}x {chest_type} chests."
                        )
                        return None

            # Check for items
            elif item_lower in ["exp_bottle", "expbottle", "bottle"]:
                offer["items"]["exp_bottle"] = (
                    offer["items"].get("exp_bottle", 0) + amount
                )
                if validate:
                    have = await get_user_item_count(user_id, "exp_bottle")
                    if have < offer["items"]["exp_bottle"]:
                        await self.bot.get_channel(
                            self.bot.guilds[0].text_channels[0].id
                        ).send(
                            f"{username} doesn't have {offer['items']['exp_bottle']}x EXP Bottles."
                        )
                        return None

            elif item_lower in ["hydro_essence", "hydroessence", "essence", "essences"]:
                offer["items"]["hydro_essence"] = (
                    offer["items"].get("hydro_essence", 0) + amount
                )
                if validate:
                    have = await get_user_item_count(user_id, "hydro_essence")
                    if have < offer["items"]["hydro_essence"]:
                        await self.bot.get_channel(
                            self.bot.guilds[0].text_channels[0].id
                        ).send(
                            f"{username} doesn't have {offer['items']['hydro_essence']}x Hydro Essence."
                        )
                        return None

            elif item_lower in ["hydro_crystal", "hydrocrystal", "crystal", "crystals"]:
                offer["items"]["hydro_crystal"] = (
                    offer["items"].get("hydro_crystal", 0) + amount
                )
                if validate:
                    have = await get_user_item_count(user_id, "hydro_crystal")
                    if have < offer["items"]["hydro_crystal"]:
                        await self.bot.get_channel(
                            self.bot.guilds[0].text_channels[0].id
                        ).send(
                            f"{username} doesn't have {offer['items']['hydro_crystal']}x Hydro Crystals."
                        )
                        return None

            elif item_lower in ["rod_shard", "rodshard", "shard", "shards"]:
                offer["items"]["rod_shard"] = (
                    offer["items"].get("rod_shard", 0) + amount
                )
                if validate:
                    have = await get_user_item_count(user_id, "rod_shard")
                    if have < offer["items"]["rod_shard"]:
                        await self.bot.get_channel(
                            self.bot.guilds[0].text_channels[0].id
                        ).send(
                            f"{username} doesn't have {offer['items']['rod_shard']}x Rod Shards."
                        )
                        return None

            elif item_lower in ["fish_bait", "fishbait", "bait"]:
                offer["items"]["fish_bait"] = (
                    offer["items"].get("fish_bait", 0) + amount
                )
                if validate:
                    have = await get_user_item_count(user_id, "fish_bait")
                    if have < offer["items"]["fish_bait"]:
                        await self.bot.get_channel(
                            self.bot.guilds[0].text_channels[0].id
                        ).send(
                            f"{username} doesn't have {offer['items']['fish_bait']}x Fish Bait."
                        )
                        return None

        return offer

    def count_items(self, offer):
        """Count number of different item types."""
        count = 0
        if offer["mora"] > 0:
            count += 1
        if offer["dust"] > 0:
            count += 1
        count += sum(1 for v in offer["chests"].values() if v > 0)
        count += sum(1 for v in offer["items"].values() if v > 0)
        return count

    def format_offer(self, offer):
        """Format offer for display."""
        lines = []

        if offer["mora"] > 0:
            lines.append(f"<:mora:1437958309255577681> {offer['mora']:,} Mora")

        if offer["dust"] > 0:
            lines.append(f"<:mora:1437480155952975943> {offer['dust']:,} Tide Coins")

        chest_icons = {
            "common": "<:cajitadelexplorador:1437473147833286676>",
            "exquisite": "<:cajitaplatino:1437473086571286699>",
            "precious": "<:cajitapremium:1437473125095837779>",
            "luxurious": "<:cajitadiamante:1437473169475764406>",
        }
        for chest_type, amount in offer["chests"].items():
            if amount > 0:
                icon = chest_icons.get(chest_type, "📦")
                lines.append(f"{icon} {amount}x {chest_type.capitalize()} Chest")

        item_icons = {
            "exp_bottle": "<:exp:1437553839359397928>",
            "hydro_essence": "<:essence:1437463601479942385>",
            "hydro_crystal": "<:crystal:1437458982989205624>",
            "rod_shard": "🔧",
            "fish_bait": "🪱",
        }
        item_names = {
            "exp_bottle": "EXP Bottle",
            "hydro_essence": "Hydro Essence",
            "hydro_crystal": "Hydro Crystal",
            "rod_shard": "Rod Shard",
            "fish_bait": "Fish Bait",
        }
        for item_key, amount in offer["items"].items():
            if amount > 0:
                icon = item_icons.get(item_key, "📦")
                name = item_names.get(item_key, item_key)
                lines.append(f"{icon} {amount}x {name}")

        return "\n".join(lines) if lines else "*Nothing*"

    async def execute_trade(self, trade_data):
        """Execute the trade."""
        try:
            from_user = trade_data["from"]
            to_user = trade_data["to"]
            from_offer = trade_data["from_offer"]
            to_offer = trade_data["to_offer"]

            await ensure_user_db(from_user.id)
            await ensure_user_db(to_user.id)

            # Re-validate that sender still has everything
            valid_from = await self.parse_offer(
                from_user.id,
                self.offer_to_string(from_offer),
                from_user.display_name,
                validate=True,
            )
            valid_to = await self.parse_offer(
                to_user.id,
                self.offer_to_string(to_offer),
                to_user.display_name,
                validate=True,
            )

            if valid_from is None or valid_to is None:
                return False, "One of the traders no longer has the required items."

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("BEGIN")

                # Transfer currency
                from_data = await get_user_data(from_user.id)
                to_data = await get_user_data(to_user.id)

                new_from_mora = (
                    from_data["mora"] - from_offer["mora"] + to_offer["mora"]
                )
                new_from_dust = (
                    from_data["dust"] - from_offer["dust"] + to_offer["dust"]
                )
                new_to_mora = to_data["mora"] - to_offer["mora"] + from_offer["mora"]
                new_to_dust = to_data["dust"] - to_offer["dust"] + from_offer["dust"]

                await db.execute(
                    "UPDATE users SET mora=?, dust=? WHERE user_id=?",
                    (new_from_mora, new_from_dust, from_user.id),
                )
                await db.execute(
                    "UPDATE users SET mora=?, dust=? WHERE user_id=?",
                    (new_to_mora, new_to_dust, to_user.id),
                )

                await db.commit()

            # Transfer chests
            for chest_type, amount in from_offer["chests"].items():
                if amount > 0:
                    await change_chest_type_count(from_user.id, chest_type, -amount)
                    await change_chest_type_count(to_user.id, chest_type, amount)

            for chest_type, amount in to_offer["chests"].items():
                if amount > 0:
                    await change_chest_type_count(to_user.id, chest_type, -amount)
                    await change_chest_type_count(from_user.id, chest_type, amount)

            # Transfer items
            for item_key, amount in from_offer["items"].items():
                if amount > 0:
                    await add_user_item(from_user.id, item_key, -amount)
                    await add_user_item(to_user.id, item_key, amount)

            for item_key, amount in to_offer["items"].items():
                if amount > 0:
                    await add_user_item(to_user.id, item_key, -amount)
                    await add_user_item(from_user.id, item_key, amount)

            return True, "Trade completed successfully!"

        except Exception as e:
            print(f"Trade execution error: {e}")
            return False, f"Trade failed: {str(e)}"

    def offer_to_string(self, offer):
        """Convert offer dict back to string for re-validation."""
        parts = []
        if offer["mora"] > 0:
            parts.append(f"mora_{offer['mora']}")
        if offer["dust"] > 0:
            parts.append(f"tidecoins_{offer['dust']}")
        for chest_type, amount in offer["chests"].items():
            parts.append(f"{chest_type}_{amount}")
        for item_key, amount in offer["items"].items():
            if item_key == "hydro_essence":
                parts.append(f"essence_{amount}")
            elif item_key == "hydro_crystal":
                parts.append(f"crystal_{amount}")
            else:
                parts.append(f"{item_key}_{amount}")
        return ", ".join(parts)


class TradeOfferView(discord.ui.View):
    def __init__(self, cog, trade_id, target_user):
        super().__init__(timeout=300)
        self.cog = cog
        self.trade_id = trade_id
        self.target_user = target_user

    async def on_timeout(self):
        if self.trade_id in self.cog.pending_trades:
            del self.cog.pending_trades[self.trade_id]

    @discord.ui.button(
        label="Accept",
        style=discord.ButtonStyle.success,
        emoji="<a:Check:1437951818452832318>",
    )
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            await interaction.response.send_message(
                "This trade is not for you.", ephemeral=True
            )
            return

        if self.trade_id not in self.cog.pending_trades:
            await interaction.response.send_message(
                "This trade has expired.", ephemeral=True
            )
            return

        trade_data = self.cog.pending_trades[self.trade_id]
        success, message = await self.cog.execute_trade(trade_data)

        del self.cog.pending_trades[self.trade_id]

        if success:
            embed = discord.Embed(
                title="<a:Check:1437951818452832318> Trade Completed!",
                description=message,
                color=0x2ECC71,
            )
            embed.add_field(
                name=f"{trade_data['from'].display_name} received:",
                value=self.cog.format_offer(trade_data["to_offer"]),
                inline=False,
            )
            embed.add_field(
                name=f"{trade_data['to'].display_name} received:",
                value=self.cog.format_offer(trade_data["from_offer"]),
                inline=False,
            )
        else:
            embed = discord.Embed(
                title="<a:X_:1437951830393884788> Trade Failed",
                description=message,
                color=0xE74C3C,
            )

        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(
        label="Decline",
        style=discord.ButtonStyle.danger,
        emoji="<a:X_:1437951830393884788>",
    )
    async def decline(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.target_user.id:
            await interaction.response.send_message(
                "This trade is not for you.", ephemeral=True
            )
            return

        if self.trade_id in self.cog.pending_trades:
            del self.cog.pending_trades[self.trade_id]

        embed = discord.Embed(
            title="Trade Declined",
            description=f"{interaction.user.display_name} declined the trade.",
            color=0xE74C3C,
        )
        await interaction.response.edit_message(embed=embed, view=None)


async def setup(bot):
    await bot.add_cog(Trading(bot))
