import random
import discord
from discord.ext import commands
import aiosqlite
from config import DB_PATH
from utils.database import get_user_data, update_user_data, require_enrollment, track_game_stat, check_and_award_game_achievements, add_account_exp
from utils.embed import send_embed


BOMB = "💣"
MONEY = "💰"


class MinesGame:
    def __init__(
        self,
        user: discord.User,
        bet: int,
        bombs: int = 3,
        size: int = 4,
        settle_cb=None,
    ):
        self.user = user
        self.bet = int(bet)
        self.bombs = int(bombs)
        self.size = size
        self.total_cells = size * size
        bomb_positions = set(random.sample(range(self.total_cells), self.bombs))
        self.grid = [
            BOMB if i in bomb_positions else MONEY for i in range(self.total_cells)
        ]
        self.revealed = set()
        self.finished = False
        self.settle_cb = settle_cb

    @property
    def found_money_count(self):
        return sum(1 for i in self.revealed if self.grid[i] == MONEY)

    @property
    def potential_payout(self):
        # multiplier increases every 2 boxes: +0.2x per 2 boxes found
        # Perfect game (all 13 boxes) = 3x multiplier
        boxes_found = self.found_money_count
        max_boxes = self.total_cells - self.bombs  # 16 - 3 = 13
        if boxes_found == max_boxes:
            multiplier = 3.0  # Perfect game bonus
        else:
            multiplier = 1.0 + 0.2 * (boxes_found // 2)
        return int(self.bet * multiplier)

    def reveal_index(self, idx: int):
        if self.finished:
            return None, False
        if idx in self.revealed:
            return self.grid[idx], False
        self.revealed.add(idx)
        if self.grid[idx] == BOMB:
            self.finished = True
            return BOMB, True
        return MONEY, False

    def reveal_all_bombs(self):
        return [i for i, v in enumerate(self.grid) if v == BOMB]


class MinesButton(discord.ui.Button):
    def __init__(self, index: int, view: "MinesView", row: int):
        label = str(index + 1)
        super().__init__(label=label, style=discord.ButtonStyle.primary, row=row)
        self.index = index
        self.mines_view = view

    async def callback(self, interaction: discord.Interaction):
        view: MinesView = self.mines_view
        game = view.game

        if interaction.user.id != game.user.id:
            await interaction.response.send_message(
                "This is not your game.", ephemeral=True
            )
            return

        if game.finished:
            await interaction.response.send_message(
                "This game has finished.", ephemeral=True
            )
            return

        value, lost = game.reveal_index(self.index)

        self.disabled = True
        self.label = value

        # Red for bomb, green for money, gray for empty
        if value == BOMB:
            self.style = discord.ButtonStyle.danger  # Red
        elif value == MONEY:
            self.style = discord.ButtonStyle.success  # Green
        else:
            self.style = discord.ButtonStyle.secondary  # Gray

        if lost:
            # Reveal all boxes
            for item in view.children:
                if isinstance(item, MinesButton):
                    val = game.grid[item.index]
                    item.label = val
                    # Red for bombs, green for money
                    if val == BOMB:
                        item.style = discord.ButtonStyle.danger
                    elif val == MONEY:
                        item.style = discord.ButtonStyle.success
                    else:
                        item.style = discord.ButtonStyle.secondary
                    item.disabled = True
            game.finished = True
            
            # Apply golden card cashback (10%)
            bank_cog = interaction.client.get_cog('Bank')
            cashback = 0
            if bank_cog:
                cashback = await bank_cog.apply_golden_cashback(game.user.id, game.bet)
            
            title = "Boom! You hit a bomb 💥"
            if cashback > 0:
                title += f" +{cashback:,} cashback <a:gold:1457409675963138205>"

            embed = view.make_embed(title=title, finished=True)
            await interaction.response.edit_message(embed=embed, view=view)
            if game.settle_cb:
                try:
                    await game.settle_cb(game.user, 0, False)
                except Exception:
                    pass
            return

        embed = view.make_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class FinishButton(discord.ui.Button):
    def __init__(self, view: "MinesView", row: int):
        super().__init__(label="Finish", style=discord.ButtonStyle.secondary, row=row)
        self.mines_view = view

    async def callback(self, interaction: discord.Interaction):
        view: MinesView = self.mines_view
        game = view.game

        if interaction.user.id != game.user.id:
            await interaction.response.send_message(
                "This is not your game.", ephemeral=True
            )
            return

        if game.finished:
            await interaction.response.send_message(
                "This game has already ended.", ephemeral=True
            )
            return

        payout = game.potential_payout
        game.finished = True
        
        # Check for Double Down Card (must be activated first)
        from utils.database import has_active_item, consume_active_item, consume_inventory_item
        has_double = await has_active_item(game.user.id, "double_down")
        double_bonus = 0
        if has_double > 0:
            profit = payout - game.bet
            double_bonus = profit  # Double the profit
            payout += double_bonus
            await consume_active_item(game.user.id, "double_down")
            await consume_inventory_item(game.user.id, "double_down")
        
        # Check for perfect game (all boxes found)
        max_boxes = game.total_cells - game.bombs
        is_perfect = game.found_money_count == max_boxes

        # Track stats and award XP
        boxes_found = game.found_money_count
        try:
            if boxes_found > 0:
                await track_game_stat(game.user.id, "mines_wins")
            await track_game_stat(game.user.id, "mines_plays")
            await check_and_award_game_achievements(game.user.id, interaction.client, interaction)
            
            # Award XP based on boxes found (5 XP per box, bonus for perfect)
            exp_reward = boxes_found * 5
            if is_perfect:
                exp_reward = 100  # Bonus XP for perfect game
            
            if exp_reward > 0:
                leveled_up, new_level, old_level = await add_account_exp(game.user.id, exp_reward)
        except Exception as e:
            print(f"Error tracking mines stats: {e}")
            exp_reward = 0
            leveled_up = False

        # Reveal all boxes
        for item in view.children:
            if isinstance(item, MinesButton):
                val = game.grid[item.index]
                item.label = val
                # Red for bombs, green for money
                if val == BOMB:
                    item.style = discord.ButtonStyle.danger
                elif val == MONEY:
                    item.style = discord.ButtonStyle.success
                else:
                    item.style = discord.ButtonStyle.secondary
                item.disabled = True
            elif isinstance(item, FinishButton):
                item.disabled = True

        title = "Cashed out <a:Check:1437951818452832318>"
        if is_perfect:
            title = "🎉 PERFECT GAME! 🎉"
        if double_bonus > 0:
            title += " 💳 **DOUBLE DOWN!**"
        
        embed = view.make_embed(title=title, finished=True)
        
        # Add XP info
        if exp_reward > 0:
            embed.add_field(
                name="XP Gained",
                value=f"+{exp_reward} XP",
                inline=True
            )
        
        # Add level up message
        if leveled_up:
            embed.add_field(
                name="Level Up!",
                value=f"<a:arrow:1437968863026479258> You reached level {new_level}!",
                inline=False
            )
        
        await interaction.response.edit_message(embed=embed, view=view)

        if game.settle_cb:
            try:
                await game.settle_cb(game.user, payout, True)
            except Exception:
                pass


class MinesView(discord.ui.View):
    def __init__(self, game: MinesGame):
        super().__init__(timeout=None)
        self.game = game
        size = game.size

        for i in range(size):
            for j in range(size):
                idx = i * size + j
                if idx in game.revealed:
                    val = game.grid[idx]
                    style = (
                        discord.ButtonStyle.success
                        if val == MONEY
                        else discord.ButtonStyle.danger
                    )
                    btn = MinesButton(index=idx, view=self, row=i)
                    btn.label = val
                    btn.disabled = True
                    btn.style = style
                else:
                    btn = MinesButton(index=idx, view=self, row=i)
                self.add_item(btn)

        finish_row = size
        finish_btn = FinishButton(view=self, row=finish_row)
        self.add_item(finish_btn)

    def make_embed(self, title: str = None, finished: bool = False) -> discord.Embed:
        game = self.game
        title = title or "Mines - Avoid Bombs"
        embed = discord.Embed(title=title, color=0x2ECC71 if not finished else 0x3498DB)
        embed.set_author(
            name=game.user.display_name, icon_url=game.user.display_avatar.url
        )
        embed.add_field(name="Bet", value=f"{game.bet:,}", inline=True)
        # Calculate multiplier: +0.2x every 2 boxes, 3x for perfect game
        boxes_found = game.found_money_count
        max_boxes = game.total_cells - game.bombs
        if boxes_found == max_boxes:
            multiplier = 3.0
        else:
            multiplier = 1.0 + 0.2 * (boxes_found // 2)
        embed.add_field(name="Multiplier", value=f"{multiplier:.1f}x", inline=True)
        embed.add_field(
            name="Potential Payout", value=f"{game.potential_payout:,}", inline=True
        )
        if finished:
            if any(game.grid[i] == BOMB for i in game.revealed):
                embed.description = "You hit a bomb. Better luck next time!"
            else:
                embed.description = f"You cashed out {game.potential_payout:,} <:mora:1437958309255577681>."
        else:
            embed.description = "Click boxes to reveal. Cash out anytime using the Finish button. If you hit a bomb you lose everything."
        return embed


class Mines(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="mines")
    async def mines(self, ctx, bet: str):
        """Start a 4x4 mines game. Usage: `gmines <bet>` or `gmines all`
        Each non-bomb box is a money box (<:mora:1437958309255577681>). There are 3 bombs by default.
        Bet may be an integer (commas allowed) or the literal `all` to bet your full balance.
        Cash out anytime with the Finish button.
        Min bet: 1,000 | Max bet: 200,000
        """
        if not await require_enrollment(ctx):
            return
        try:
            # Check if user has unlimited betting
            from utils.database import has_unlimited_game
            unlimited = await has_unlimited_game(ctx.author.id, "mines")
            
            # validate bet
            MIN_BET = 1_000
            # Check premium status for higher bet limit
            premium_cog = self.bot.get_cog('Premium')
            is_premium = False
            if premium_cog:
                is_premium = await premium_cog.is_premium(ctx.author.id)
                print(f"[MINES] User {ctx.author.id} premium status: {is_premium}")
            
            # Premium: 1M, Normal: 200K, Unlimited: No limit
            MAX_BET = 1_000_000 if is_premium else 200_000
            print(f"[MINES] User {ctx.author.id} MAX_BET set to: {MAX_BET:,}")
            if unlimited:
                MAX_BET = float('inf')

            # parse bet: allow 'all' or integer strings (commas allowed)
            data = await get_user_data(ctx.author.id)
            mora = data.get("mora", 0)

            if isinstance(bet, str) and bet.lower() == "all":
                if unlimited:
                    bet_amount = mora  # No cap for unlimited users
                else:
                    bet_amount = min(mora, 200_000)  # Cap at max bet for normal users
                if bet_amount < MIN_BET:
                    await ctx.send(
                        f"You need at least {MIN_BET:,} <:mora:1437958309255577681> to play."
                    )
                    return
            else:
                try:
                    bet_amount = int(str(bet).replace(",", ""))
                except Exception:
                    await ctx.send(
                        "<a:X_:1437951830393884788> Please specify a valid integer bet or use `all` to bet your full balance."
                    )
                    return

            if bet_amount < MIN_BET:
                await ctx.send(
                    f"<a:X_:1437951830393884788> Minimum bet is {MIN_BET:,} <:mora:1437958309255577681>"
                )
                return
            if not unlimited and bet_amount > 200_000:
                await ctx.send(
                    f"<a:X_:1437951830393884788> Maximum bet is {200_000:,} <:mora:1437958309255577681>"
                )
                return
            if mora < bet_amount:
                await ctx.send(
                    "<a:X_:1437951830393884788> You don't have enough Mora to place that bet."
                )
                return

            # deduct bet up-front (escrow)
            await update_user_data(ctx.author.id, mora=mora - bet_amount)

            # settle callback: credit payout (amount) back to user if won cashout, or zero on loss
            async def settle_cb(user, amount: int, won: bool):
                try:
                    # credit amount to user's mora
                    if amount and amount > 0:
                        ud = await get_user_data(user.id)
                        await update_user_data(
                            user.id, mora=ud.get("mora", 0) + int(amount)
                        )
                    elif not won:
                        # Lost the game - add bet to bank
                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.execute(
                                "UPDATE global_bank SET balance = balance + ? WHERE id = 1",
                                (bet_amount,)
                            )
                            await db.commit()
                    # (no DM) result notification is intentionally suppressed to avoid sending users DMs
                except Exception as e:
                    print(f"Error in mines settle_cb: {e}")

            # create game and view
            game = MinesGame(
                ctx.author, bet_amount, bombs=3, size=4, settle_cb=settle_cb
            )
            view = MinesView(game)
            embed = view.make_embed()
            await send_embed(ctx, embed, view=view)
        except Exception as e:
            print(f"Error starting mines: {e}")
            await ctx.send(
                "<a:X_:1437951830393884788> Failed to start Mines. Please try again."
            )


async def setup(bot):
    await bot.add_cog(Mines(bot))
