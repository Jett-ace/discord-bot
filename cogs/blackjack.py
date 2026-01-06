import random
import discord
from discord.ext import commands
import aiosqlite
from config import DB_PATH
from utils.database import get_user_data, update_user_data, require_enrollment, track_game_stat, check_and_award_game_achievements, add_account_exp
from utils.embed import send_embed


RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["♠", "♥", "♦", "♣"]


def make_deck():
    return [f"{r}{s}" for r in RANKS for s in SUITS]


def hand_value(cards):
    # returns best value <=21 or minimal over 21
    total = 0
    aces = 0
    for c in cards:
        rank = c[:-1]
        if rank == "A":
            aces += 1
            total += 11
        elif rank in ("J", "Q", "K"):
            total += 10
        else:
            try:
                total += int(rank)
            except Exception:
                total += 0
    # downgrade aces from 11 to 1 as needed
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


class BlackjackView(discord.ui.View):
    def __init__(self, ctx, initial_bet, deck, player_cards, dealer_cards, reserved_total, cog, start_balance=None):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.initial_bet = int(initial_bet)
        self.deck = deck
        # hands: list of dicts {cards:[], stake:int, blackjack_eligible:bool, surrendered:bool}
        self.hands = [{"cards": player_cards, "stake": int(initial_bet), "eligible": True, "surrendered": False, "doubled": False}]
        self.dealer = dealer_cards
        self.current = 0
        self.finished = False
        # reserved_total is mutable and tracks how much stake is still reserved
        self.reserved_total = int(reserved_total)
        # keep original reserved amount for accurate net calculation in final message
        self._original_reserved = int(reserved_total)
        # track total already-awarded payouts (from instant-21 flow) so final net message can include them
        # NOTE: we will NOT credit these immediately to the DB here; instead we accumulate
        # and credit once at the end to avoid mid-game DB writes causing inconsistent net math.
        self._immediate_awarded = 0
        # starting user balance BEFORE the initial reservation (used to compute net change accurately)
        self._starting_balance = start_balance
        self.cog = cog

    def card_str(self, cards):
        return " ".join(f"`{c}`" for c in cards)

    def embed(self, reveal_dealer=False, note="", color: int = 0x1abc9c):
        dealer_display = self.card_str(self.dealer) if reveal_dealer else f"`{self.dealer[0]}` ??"
        e = discord.Embed(title="Blackjack", color=color)
        e.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.display_avatar.url)
        e.add_field(name="Dealer", value=f"{dealer_display}\nValue: {hand_value(self.dealer) if reveal_dealer else '??'}", inline=False)
        # show all player hands, highlight current
        for idx, h in enumerate(self.hands):
            val = hand_value(h["cards"]) if h["cards"] else 0
            # if only a single hand, show simply 'You' to avoid '1/1 (current)'
            if len(self.hands) == 1:
                title = "You"
            else:
                title = f"You {idx+1}/{len(self.hands)}"
            e.add_field(name=title, value=f"{self.card_str(h['cards'])}\nValue: {val}\nStake: {h['stake']:,}", inline=False)
        if note:
            e.set_footer(text=note)
        return e

    async def end_game(self, note, payouts, color: int = 0x1abc9c):
        # payouts is total amount to credit back to user (includes original stakes when applicable)
        if self.finished:
            return
        self.finished = True
        
        # Check for Golden Chip (adds +0.3x to winnings)
        from utils.database import has_inventory_item, consume_inventory_item
        has_chip = await has_inventory_item(self.ctx.author.id, "golden_chip")
        
        chip_bonus = 0
        if has_chip > 0 and payouts > self._original_reserved:
            # Only apply to wins (when payout exceeds original bet)
            profit = payouts - self._original_reserved
            chip_bonus = int(profit * 0.3)
            payouts += chip_bonus
            await consume_inventory_item(self.ctx.author.id, "golden_chip")
            note += f" <:goldenchip:1457964285207646264> Golden Chip: +{chip_bonus:,} Mora!"
        
        # credit payouts
        try:
            data = await get_user_data(self.ctx.author.id)
            data['mora'] += int(payouts)
            await update_user_data(self.ctx.author.id, mora=data['mora'])
        except Exception as e:
            print(f"Error crediting payout: {e}")

        # remove lock
        try:
            self.cog.active_games.discard(self.ctx.author.id)
        except Exception:
            pass

        try:
            # reveal dealer and include final note (concise result) in the embed footer
            await self.message.edit(embed=self.embed(reveal_dealer=True, note=note, color=color), view=None)
        except Exception:
            pass

    async def on_timeout(self):
        if not self.finished:
            # return reserved_total
            try:
                data = await get_user_data(self.ctx.author.id)
                data['mora'] += int(self.reserved_total)
                await update_user_data(self.ctx.author.id, mora=data['mora'])
            except Exception as e:
                print(f"Error returning bet on timeout: {e}")
                try:
                    self.cog.active_games.discard(self.ctx.author.id)
                    await self.message.edit(content="Game timed out - bet(s) returned.", view=None)
                except Exception:
                    pass

    def current_hand(self):
        return self.hands[self.current]

    async def _award_hand_immediately(self, h):
        """Award a single hand immediately when it reaches 21.
        Credits the payout for that hand and adjusts reserved_total so it won't be double-counted later.
        """
        try:
            stake = int(h['stake'])
            payout = int(stake * 2)
            # Do NOT credit the payout immediately. Instead, record it for end-of-game crediting.
            # reduce reserved_total by the original stake since we already handled this hand
            self.reserved_total -= stake
            # record that we'll pay this amount at settlement
            self._immediate_awarded += payout
            h['finished'] = True
            h['awarded'] = True
            return payout
        except Exception as e:
            print(f"Error awarding immediate 21 payout: {e}")
            return 0

    def all_hands_done(self):
        # done if all hands either busted, surrendered, or marked finished by flags
        for h in self.hands:
            if h.get('surrendered'):
                continue
            if hand_value(h['cards']) <= 21 and not h.get('finished'):
                return False
        return True

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This is not your game.", ephemeral=True)
        if self.finished:
            return await interaction.response.defer()
        h = self.current_hand()
        card = self.deck.pop()
        h['cards'].append(card)
        pv = hand_value(h['cards'])
        # immediate-21 shortcut: if player reaches 21, award this hand instantly
        if pv == 21:
            payout = await self._award_hand_immediately(h)
            note = f"Instant 21! Awarded {payout:,} Mora for this hand."
            if self.current < len(self.hands) - 1:
                if self.current < len(self.hands) - 1:
                    self.current += 1
                    await self.message.edit(embed=self.embed(note=note))
                    return await interaction.response.defer()
            else:
                # all hands done? trigger end flow which will skip awarded hands
                await self.finish_and_settle(interaction)
                return
    # if busted, mark finished for this hand and auto-advance
        if pv > 21:
            h['finished'] = True
            # auto-advance to next hand if exists
            if self.current < len(self.hands) - 1:
                self.current += 1
                await self.message.edit(embed=self.embed())
                return await interaction.response.defer()
            else:
                # all hands done -> dealer plays and settle
                await self.finish_and_settle(interaction)
                return
        await self.message.edit(embed=self.embed())
        await interaction.response.defer()

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.gray)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This is not your game.", ephemeral=True)
        if self.finished:
            return await interaction.response.defer()
        # mark current hand finished (stood) and advance or settle
        h = self.current_hand()
        h['finished'] = True
        h['stood'] = True
        if self.current < len(self.hands) - 1:
            self.current += 1
            await self.message.edit(embed=self.embed())
            return await interaction.response.defer()
        else:
            await self.finish_and_settle(interaction)

    @discord.ui.button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Double down: double stake, draw one card, then stand on this hand
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This is not your game.", ephemeral=True)
        if self.finished:
            return await interaction.response.defer()
        h = self.current_hand()
        # only allowed on first two cards
        if len(h['cards']) != 2:
            return await interaction.response.send_message("Double down is only allowed on your first two cards.", ephemeral=True)
        extra = int(h['stake'])
        # check balance
        data = await get_user_data(self.ctx.author.id)
        if data.get('mora', 0) < extra:
            return await interaction.response.send_message("Not enough Mora to double down.", ephemeral=True)
        # deduct extra
        data['mora'] -= extra
        await update_user_data(self.ctx.author.id, mora=data['mora'])
        h['stake'] += extra
        h['doubled'] = True
        self.reserved_total += extra
        # draw one card
        card = self.deck.pop()
        h['cards'].append(card)
        # if this draw hits 21, award this hand immediately
        pv = hand_value(h['cards'])
        if pv == 21:
            payout = await self._award_hand_immediately(h)
            note = f"Instant 21! Awarded {payout:,} Mora for this hand."
            if self.current < len(self.hands) - 1:
                self.current += 1
                await self.message.edit(embed=self.embed(note=note))
                return await interaction.response.defer()
            else:
                await self.finish_and_settle(interaction)
                return
        h['finished'] = True
        # advance or settle
        if self.current < len(self.hands) - 1:
            self.current += 1
            await self.message.edit(embed=self.embed())
            return await interaction.response.defer()
        else:
            await self.finish_and_settle(interaction)

    @discord.ui.button(label="Split", style=discord.ButtonStyle.secondary)
    async def split(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Split into two hands if first two cards same rank
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This is not your game.", ephemeral=True)
        if self.finished:
            return await interaction.response.defer()
        # only allowed when single hand with exactly 2 cards
        if len(self.hands) != 1:
            return await interaction.response.send_message("You can only split the initial hand.", ephemeral=True)
        h = self.hands[0]
        if len(h['cards']) != 2:
            return await interaction.response.send_message("Split is only allowed on your first two cards.", ephemeral=True)
        r1 = h['cards'][0][:-1]
        r2 = h['cards'][1][:-1]
        if r1 != r2:
            return await interaction.response.send_message("Cards must be same rank to split.", ephemeral=True)
        # check balance for extra stake
        data = await get_user_data(self.ctx.author.id)
        extra = int(h['stake'])
        if data.get('mora', 0) < extra:
            return await interaction.response.send_message("Not enough Mora to split.", ephemeral=True)
        # deduct extra
        data['mora'] -= extra
        await update_user_data(self.ctx.author.id, mora=data['mora'])
        self.reserved_total += extra
        # create two hands
        card1 = h['cards'][0]
        card2 = h['cards'][1]
        new1 = {"cards": [card1, self.deck.pop()], "stake": int(h['stake']), "eligible": False, "surrendered": False, "doubled": False}
        new2 = {"cards": [card2, self.deck.pop()], "stake": int(h['stake']), "eligible": False, "surrendered": False, "doubled": False}
        self.hands = [new1, new2]
        self.current = 0
        await self.message.edit(embed=self.embed())
        await interaction.response.defer()

    @discord.ui.button(label="Surrender", style=discord.ButtonStyle.red)
    async def surrender(self, interaction: discord.Interaction, button: discord.ui.Button):
        # surrender returns half stake, only allowed on first action of first hand and when only one hand
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This is not your game.", ephemeral=True)
        if self.finished:
            return await interaction.response.defer()
        if len(self.hands) != 1 or len(self.hands[0]['cards']) != 2:
            return await interaction.response.send_message("Surrender is only allowed as your first action on the initial hand.", ephemeral=True)
        h = self.hands[0]
        half = int(h['stake'] // 2)
        # credit half back immediately
        data = await get_user_data(self.ctx.author.id)
        data['mora'] += half
        await update_user_data(self.ctx.author.id, mora=data['mora'])
        # reduce reserved_total accordingly (we reserved full stake initially)
        self.reserved_total -= half
        h['surrendered'] = True
        await self.end_game(f"Surrendered - returned {half:,} Mora.", payouts=0, color=0xDC143C)
        try:
            await interaction.response.defer()
        except Exception:
            pass

    async def finish_and_settle(self, interaction=None):
        # Determine if there are any player hands that still require dealer resolution.
        # We treat a hand as requiring resolution if it's not surrendered, not awarded,
        # and either (a) not finished (player still to act) or (b) was finished by standing.
        active_non_awarded = False
        stood_values = []
        for h in self.hands:
            if h.get('surrendered'):
                continue
            if h.get('awarded'):
                continue
            pv = hand_value(h['cards'])
            if h.get('stood'):
                # standing hands require dealer resolution (compare values)
                active_non_awarded = True
                stood_values.append(pv)
            elif not h.get('finished') and pv <= 21:
                # still active hand awaiting player action
                active_non_awarded = True

        # Dealer only draws if there exists at least one non-awarded player hand to resolve.
        if active_non_awarded:
            # Standard blackjack dealer rules: dealer must draw to 17 and stand on all 17s
            while hand_value(self.dealer) < 17:
                self.dealer.append(self.deck.pop())

        dv = hand_value(self.dealer)
        total_payout = 0
        # determine outcome per hand and compute total payout
        for h in self.hands:
            stake = int(h['stake'])
            if h.get('surrendered') or h.get('awarded'):
                # surrendered hands were already handled earlier
                continue
            pv = hand_value(h['cards'])
            # determine outcome; blackjack only applies if eligible and initial 2-card 21
            is_player_blackjack = (h.get('eligible') and len(h['cards']) == 2 and pv == 21)
            is_dealer_blackjack = (len(self.dealer) == 2 and dv == 21)

            if is_player_blackjack and not is_dealer_blackjack:
                # Reduced payout: 2.2x instead of 2.5x
                payout = int(stake * 2.2)
            elif pv > 21:
                payout = 0
            elif dv > 21:
                payout = stake * 2
            elif pv > dv:
                payout = stake * 2
            elif pv == dv:
                payout = stake
            else:
                payout = 0

            total_payout += int(payout)
        # compute total to credit (immediate-awards + payouts for non-awarded hands)
        total_to_credit = int(self._immediate_awarded) + int(total_payout)

        # compute net change relative to the starting balance (before any reservation/deductions)
        # fetch current balance (this reflects any immediate deductions/returns that happened during play)
        try:
            cur = await get_user_data(self.ctx.author.id)
            current_balance = int(cur.get('mora', 0))
        except Exception:
            current_balance = 0

        # net after we credit total_to_credit
        net = (current_balance + total_to_credit) - int(self._starting_balance or 0)
        if net > 0:
            msg = f"You won! You gained {net:,} Mora."
        elif net < 0:
            msg = f"Loss {abs(net):,}. Better luck next time."
        else:
            msg = "Push - no net gain or loss."

        # Track stats and award XP for wins
        if net > 0:
            try:
                await track_game_stat(self.ctx.author.id, "blackjack_wins")
                await track_game_stat(self.ctx.author.id, "blackjack_plays")
                await check_and_award_game_achievements(self.ctx.author.id, self.cog.bot, self.ctx)
                
                # Award XP (80 XP for blackjack win)
                exp_reward = 80
                leveled_up, new_level, old_level = await add_account_exp(self.ctx.author.id, exp_reward)
                msg += f" (+{exp_reward} XP)"
                if leveled_up:
                    msg += f"\n**Level Up!** You reached level {new_level}!"
            except Exception as e:
                print(f"Error tracking blackjack stats: {e}")
        else:
            # Track play stat even on loss/push
            try:
                await track_game_stat(self.ctx.author.id, "blackjack_plays")
            except Exception:
                pass

        # If invoked from an interaction, acknowledge it so Discord doesn't complain
        if interaction:
            try:
                await interaction.response.defer()
            except Exception:
                pass

        # choose color: purple for net win, crimson for loss, default gray for push
        if net > 0:
            color = 0x9b59b6
        elif net < 0:
            color = 0xDC143C
        else:
            color = 0x95a5a6

        # Add loss to global bank and apply discounts
        if net < 0:
            try:
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "UPDATE global_bank SET balance = balance + ? WHERE id = 1",
                        (abs(net),)
                    )
                    await db.commit()
            except Exception as e:
                print(f"Error adding loss to bank: {e}")
            
            # Apply golden card cashback (10%)
            bank_cog = self.cog.bot.get_cog('Bank')
            if bank_cog:
                cashback = await bank_cog.apply_golden_cashback(self.ctx.author.id, abs(net))
                if cashback > 0:
                    msg += f" +{cashback:,} cashback <a:gold:1457409675963138205>"
        
        # End the game: credit the total_to_credit (handled inside end_game) and show the concise result
        await self.end_game(msg, total_to_credit, color=color)


class Blackjack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # track users with active games to prevent concurrent games per user
        self.active_games = set()

    @commands.command(name="blackjack", aliases=["bj"])
    async def blackjack(self, ctx, bet: str = None):
        """Play blackjack! Bet mora and try to beat the dealer by getting closer to 21 without going over.
        
        Usage: gblackjack <amount> or gbj <amount>
        Example: gbj 5000 or gbj all
        
        Min bet: 1,000 | Max bet: 15,000,000
        
        Actions:
        - Hit - Draw another card
        - Stand - Keep your hand
        - Double - Double your bet and draw one card
        - Split - Split matching cards into two hands
        - Surrender - Give up and get half your bet back"""
        if not await require_enrollment(ctx):
            return
        try:
            # Check if user has unlimited betting
            from utils.database import has_unlimited_game
            unlimited = await has_unlimited_game(ctx.author.id, "blackjack")
            
            if bet is None:
                limit_text = "No limit" if unlimited else f"Max: {200_000:,} Mora"
                embed = discord.Embed(
                    title="❌ Missing Bet Amount",
                    description="You need to specify how much you want to bet!",
                    color=0xE74C3C
                )
                embed.add_field(name="Usage", value="`gbj <amount>` or `gbj all`", inline=False)
                embed.add_field(name="Examples", value="`gbj 5000`\n`gbj 10000`\n`gbj all`", inline=False)
                embed.add_field(name="Limits", value=f"Min: {1_000:,} Mora\n{limit_text}", inline=False)
                return await ctx.send(embed=embed)
            
            MIN_BET = 1_000
            MAX_BET = 15_000_000
            
            data = await get_user_data(ctx.author.id)
            balance = data.get('mora', 0)

            if bet.lower() == 'all':
                amount = balance
                # Cap at MAX_BET even for 'all'
                if amount > MAX_BET:
                    amount = MAX_BET
                if amount < MIN_BET:
                    await ctx.send(f"<a:X_:1437951830393884788> You need at least {MIN_BET:,} <:mora:1437958309255577681> to play.")
                    return
            else:
                try:
                    amount = int(bet.replace(',',''))
                except Exception:
                    await ctx.send("<a:X_:1437951830393884788> Invalid bet amount.")
                    return

            if amount < MIN_BET:
                await ctx.send(f"Minimum bet is {MIN_BET:,} <:mora:1437958309255577681>.")
                return
            
            if amount > MAX_BET:
                await ctx.send(f"<a:X_:1437951830393884788> Maximum bet is {MAX_BET:,} <:mora:1437958309255577681>.")
                return
            
            if amount > balance:
                await ctx.send("You don't have enough Mora for that bet.")
                return

            # prevent concurrent games
            if ctx.author.id in self.active_games:
                await ctx.send("⏳ You already have an active Blackjack game.")
                return

            # reserve bet immediately
            data['mora'] -= amount
            await update_user_data(ctx.author.id, mora=data['mora'])

            # mark active
            self.active_games.add(ctx.author.id)

            # Check for Rigged Deck item (guaranteed blackjack)
            from utils.database import has_inventory_item, consume_inventory_item
            has_rigged = await has_inventory_item(ctx.author.id, "rigged_deck")
            
            if has_rigged > 0:
                # Consume rigged deck and give instant blackjack win
                await consume_inventory_item(ctx.author.id, "rigged_deck")
                payout = int(amount * 2.2)
                try:
                    data = await get_user_data(ctx.author.id)
                    data['mora'] += payout
                    await update_user_data(ctx.author.id, mora=data['mora'])
                except Exception as e:
                    print(f"Error crediting blackjack payout: {e}")

                # Track stats
                try:
                    await track_game_stat(ctx.author.id, "blackjack_wins")
                    await track_game_stat(ctx.author.id, "blackjack_plays")
                    await track_game_stat(ctx.author.id, "blackjack_naturals")
                    await check_and_award_game_achievements(ctx.author.id, self.bot, ctx)
                except Exception:
                    pass

                e = discord.Embed(
                    title=f"<a:deck:1457965675082551306> Rigged Deck - Blackjack!", 
                    description=f"**Rigged Deck guaranteed win!** +{payout:,} <:mora:1437958309255577681>",
                    color=0xF1C40F
                )
                e.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
                e.add_field(name="Dealer", value="?? ??\nValue: ??", inline=False)
                e.add_field(name="You", value="A\u2660 K\u2665\nValue: 21\nStake: {:,}".format(amount), inline=False)
                self.active_games.discard(ctx.author.id)
                return await send_embed(ctx, e)

            # prepare deck and hands
            deck = make_deck()
            random.shuffle(deck)
            player_cards = [deck.pop(), deck.pop()]
            dealer_cards = [deck.pop(), deck.pop()]

            # check for immediate player blackjack (initial 2-card 21)
            pv = hand_value(player_cards)
            dv = hand_value(dealer_cards)
            if pv == 21:
                # immediate player blackjack: reduced payout (2.2x instead of 2.5x)
                payout = int(amount * 2.2)
                try:
                    data = await get_user_data(ctx.author.id)
                    data['mora'] += payout
                    await update_user_data(ctx.author.id, mora=data['mora'])
                except Exception as e:
                    print(f"Error crediting blackjack payout: {e}")

                # build purple win embed and end game immediately
                e = discord.Embed(
                    title=f"Blackjack - {ctx.author.display_name}", 
                    description=f"**Lucky blackjack!** You win {payout:,} <:mora:1437958309255577681>",
                    color=0x9b59b6
                )
                e.add_field(name="Dealer", value=f"`{dealer_cards[0]}` `{dealer_cards[1]}`\nValue: {dv}", inline=False)
                e.add_field(name="You", value=f"`{player_cards[0]}` `{player_cards[1]}`\nValue: {pv}\nStake: {amount:,}", inline=False)
                try:
                    self.active_games.discard(ctx.author.id)
                except Exception:
                    pass
                await send_embed(ctx, e)
                return

            # reserved_total initially equals the amount; further actions (double/split) will increase it
            # pass starting balance (balance before reservation) so view can compute net correctly
            view = BlackjackView(ctx, amount, deck, player_cards, dealer_cards, reserved_total=amount, cog=self, start_balance=balance)
            embed = view.embed()
            message = await send_embed(ctx, embed, view=view)
            view.message = message
        except Exception as e:
            from utils.logger import setup_logger
            logger = setup_logger("Blackjack")
            logger.error(f"Error in blackjack command: {e}", exc_info=True)
            await ctx.send("<a:X_:1437951830393884788> Failed to start the blackjack game. Please try again.")


async def setup(bot):
    if bot.get_cog("Blackjack") is None:
        await bot.add_cog(Blackjack(bot))
    else:
        print("Blackjack cog already loaded; skipping add_cog")
