"""Interactive PvP Battle System - Turn-based combat"""
import random
import asyncio
import discord
from discord.ext import commands
from datetime import datetime, timedelta
import aiosqlite

from config import DB_PATH
from utils.database import get_user_data, update_user_data, get_user_pulls, add_account_exp
from utils.embed import send_embed


class InteractiveBattleView(discord.ui.View):
    """Interactive turn-based battle interface"""
    
    def __init__(self, player, player_team, opponent_name, opponent_team, battle_cog, channel, is_ai=True, current_winstreak=0):
        super().__init__(timeout=120)
        self.player = player
        self.player_team = [c.copy() for c in player_team]
        self.opponent_name = opponent_name
        self.opponent_team = [c.copy() for c in opponent_team]
        self.battle_cog = battle_cog
        self.channel = channel
        self.is_ai = is_ai
        self.current_winstreak = current_winstreak
        
        # Battle state
        self.player_active_idx = 0
        self.opponent_active_idx = 0
        self.current_action = None
        
        # Initialize HP and NP gauge for each character
        for char in self.player_team:
            char['current_hp'] = char['hp']
            char['np_gauge'] = 0
        for char in self.opponent_team:
            char['current_hp'] = char['hp']
            char['np_gauge'] = 0
    
    def get_active_player_char(self):
        return self.player_team[self.player_active_idx]
    
    def get_active_opponent_char(self):
        return self.opponent_team[self.opponent_active_idx]
    
    def _create_hp_bar(self, current, maximum, length=20):
        """Create visual HP bar"""
        if maximum == 0:
            return "▱" * length
        percentage = current / maximum
        filled = int(percentage * length)
        filled = max(0, min(filled, length))
        
        return "▰" * filled + "▱" * (length - filled)
    
    async def update_battle_display(self, interaction=None, action_text=None):
        """Update the battle embed"""
        player_char = self.get_active_player_char()
        opponent_char = self.get_active_opponent_char()
        
        if action_text:
            self.current_action = action_text
        
        embed = discord.Embed(
            title="⚔️ PVP BATTLE",
            description=self.current_action if self.current_action else "Choose your move!",
            color=0x2F3136
        )
        
        # YOUR TEAM - Show all 3 cards
        your_team_display = []
        for i, char in enumerate(self.player_team):
            hp_bar = self._create_hp_bar(char['current_hp'], char['hp'], 10)
            status = "⚡" if i == self.player_active_idx else "💤" if char['current_hp'] > 0 else "💀"
            
            card = (
                f"{status} **{char['name']}**\n"
                f"`{hp_bar}` {char['current_hp']:,}/{char['hp']:,}\n"
                f"ATK: {char['atk']:,}"
            )
            your_team_display.append(card)
        
        # Show NP gauge for active character
        active_char = self.player_team[self.player_active_idx]
        np_gauge = active_char.get('np_gauge', 0)
        np_bar = "█" * (np_gauge // 10) + "░" * (10 - (np_gauge // 10))
        np_display = f"\n⚡ NP: `{np_bar}` {np_gauge}%"
        
        embed.add_field(
            name="━━━━━ YOUR TEAM ━━━━━",
            value="\n\n".join(your_team_display) + np_display,
            inline=False
        )
        
        # VS SEPARATOR
        embed.add_field(
            name="\u200b",
            value="⚔️ **VS** ⚔️",
            inline=False
        )
        
        # OPPONENT TEAM - Show all 3 cards
        opp_team_display = []
        for i, char in enumerate(self.opponent_team):
            hp_bar = self._create_hp_bar(char['current_hp'], char['hp'], 10)
            status = "⚡" if i == self.opponent_active_idx else "💤" if char['current_hp'] > 0 else "💀"
            
            card = (
                f"{status} **{char['name']}**\n"
                f"`{hp_bar}` {char['current_hp']:,}/{char['hp']:,}\n"
                f"ATK: {char['atk']:,}"
            )
            opp_team_display.append(card)
        
        embed.add_field(
            name="━━━━━ OPPONENT TEAM ━━━━━",
            value="\n\n".join(opp_team_display),
            inline=False
        )
        
        embed.set_footer(text=f"Win Streak: {self.current_winstreak} - 2 minute timeout")
        
        if interaction:
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            return embed
    
    def check_battle_end(self):
        """Check if battle is over"""
        player_alive = any(c['current_hp'] > 0 for c in self.player_team)
        opponent_alive = any(c['current_hp'] > 0 for c in self.opponent_team)
        
        if not player_alive:
            return "opponent"
        if not opponent_alive:
            return "player"
        return None
    
    async def switch_to_next_character(self, team, active_idx):
        """Switch to next alive character"""
        for i in range(len(team)):
            if team[i]['current_hp'] > 0:
                return i
        return active_idx
    
    async def handle_attack(self, interaction: discord.Interaction, attack_type: str):
        """Handle player attack with Command Cards"""
        if interaction.user.id != self.player.id:
            return await interaction.response.send_message("Not your battle!", ephemeral=True)
        
        player_char = self.get_active_player_char()
        opponent_char = self.get_active_opponent_char()
        
        # Initialize NP gauge if not exists
        if 'np_gauge' not in player_char:
            player_char['np_gauge'] = 0
        
        # Calculate damage and NP gain based on card type
        if attack_type == "buster":
            # Buster: High damage, no NP gain
            damage = int(player_char['atk'] * random.uniform(1.4, 1.7))
            np_gain = 0
            action = f"🔴 {player_char['name']} uses Buster Card"
        elif attack_type == "arts":
            # Arts: Moderate damage, high NP gain
            damage = int(player_char['atk'] * random.uniform(1.0, 1.3))
            np_gain = random.randint(20, 30)
            action = f"🔵 {player_char['name']} uses Arts Card"
        elif attack_type == "quick":
            # Quick: Lower damage, moderate NP gain, crit chance
            damage = int(player_char['atk'] * random.uniform(0.8, 1.1))
            np_gain = random.randint(10, 15)
            # 30% chance for crit (double damage)
            if random.random() < 0.30:
                damage = int(damage * 2)
                action = f"🟢 {player_char['name']} uses Quick Card - CRITICAL!"
            else:
                action = f"🟢 {player_char['name']} uses Quick Card"
        
        # Apply NP gain
        player_char['np_gauge'] = min(100, player_char['np_gauge'] + np_gain)
        
        # Apply damage
        opponent_char['current_hp'] -= damage
        opponent_char['current_hp'] = max(0, opponent_char['current_hp'])
        
        np_text = f" | NP +{np_gain}%" if np_gain > 0 else ""
        self.current_action = f"{action} → **{damage:,} DMG**{np_text}"
        
        # Check if opponent character defeated
        if opponent_char['current_hp'] <= 0:
            self.current_action += f"\n❌ {opponent_char['name']} defeated!"
            self.opponent_active_idx = await self.switch_to_next_character(self.opponent_team, self.opponent_active_idx)
        
        # Check if battle ended
        winner = self.check_battle_end()
        if winner:
            return await self.end_battle(interaction, winner)
        
        # Opponent's turn
        await self.opponent_turn()
        
        # Check again after opponent turn
        winner = self.check_battle_end()
        if winner:
            return await self.end_battle(interaction, winner)
        
        self.update_button_states()
        await self.update_battle_display(interaction)
    
    async def opponent_turn(self):
        """AI opponent's turn with Command Cards"""
        opponent_char = self.get_active_opponent_char()
        player_char = self.get_active_player_char()
        
        # Initialize NP gauge if not exists
        if 'np_gauge' not in opponent_char:
            opponent_char['np_gauge'] = 0
        
        # AI chooses card (balanced distribution)
        attack_choice = random.choices(
            ['buster', 'arts', 'quick'],
            weights=[40, 35, 25]
        )[0]
        
        if attack_choice == "buster":
            damage = int(opponent_char['atk'] * random.uniform(1.4, 1.7))
            np_gain = 0
            action = f"🔴 {opponent_char['name']} uses Buster Card"
        elif attack_choice == "arts":
            damage = int(opponent_char['atk'] * random.uniform(1.0, 1.3))
            np_gain = random.randint(20, 30)
            action = f"🔵 {opponent_char['name']} uses Arts Card"
        else:
            damage = int(opponent_char['atk'] * random.uniform(0.8, 1.1))
            np_gain = random.randint(10, 15)
            if random.random() < 0.30:
                damage = int(damage * 2)
                action = f"🟢 {opponent_char['name']} uses Quick Card - CRITICAL!"
            else:
                action = f"🟢 {opponent_char['name']} uses Quick Card"
        
        opponent_char['np_gauge'] = min(100, opponent_char['np_gauge'] + np_gain)
        
        player_char['current_hp'] -= damage
        player_char['current_hp'] = max(0, player_char['current_hp'])
        
        np_text = f" | NP +{np_gain}%" if np_gain > 0 else ""
        self.current_action += f"\n{action} → **{damage:,} DMG**{np_text}"
        
        # Check if player character defeated
        if player_char['current_hp'] <= 0:
            self.current_action += f"\n❌ {player_char['name']} defeated!"
            self.player_active_idx = await self.switch_to_next_character(self.player_team, self.player_active_idx)
    
    async def end_battle(self, interaction, winner):
        """End the battle and show results"""
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        if winner == "player":
            # Award rewards
            base_reward = 1000
            exp_reward = 500
            
            user_data = await get_user_data(self.player.id)
            await update_user_data(self.player.id, mora=user_data['mora'] + base_reward)
            await add_account_exp(self.player.id, exp_reward, source="battle_win")
            
            # Update quest progress
            try:
                quests_cog = self.battle_cog.bot.get_cog('Quests')
                if quests_cog:
                    await quests_cog.update_quest_progress(self.player.id, 'battle', 1)
            except:
                pass
            
            # Chest reward chance (10%)
            chest_text = ""
            if random.random() < 0.10:
                chest_cog = self.battle_cog.bot.get_cog('Chest')
                if chest_cog:
                    try:
                        chest_data = await chest_cog.generate_chest("common")
                        await update_user_data(self.player.id, chests=user_data.get('chests', 0) + 1)
                        chest_text = "🎁 1 Chest gained\n"
                    except:
                        pass
            
            # Increment winstreak
            new_streak = self.current_winstreak + 1
            self.battle_cog.winstreaks[self.player.id] = new_streak
            
            embed = discord.Embed(
                title="🎉 VICTORY",
                description=f"**{self.player.mention}** wins the battle!",
                color=0x2ECC71
            )
            
            # Rewards display
            rewards_text = (
                f"💰 {base_reward:,} Mora\n"
                f"⭐ {exp_reward:,} EXP\n"
            )
            if chest_text:
                rewards_text += f"🎁 Common Chest\n"
            rewards_text += f"\n*All cards gained {exp_reward} experience*"
            
            embed.add_field(
                name="**Rewards**",
                value=rewards_text,
                inline=False
            )
            
            # Show final team status
            player_status = "\n".join([
                f"{'❌' if c['current_hp'] <= 0 else '❤️'} {c['name']}"
                for c in self.player_team
            ])
            opponent_status = "\n".join([
                f"{'❌' if c['current_hp'] <= 0 else '❤️'} {c['name']}"
                for c in self.opponent_team
            ])
            
            embed.add_field(name="Your Team", value=player_status, inline=True)
            embed.add_field(name="Enemy Team", value=opponent_status, inline=True)
            
            embed.set_footer(text=f"Win Streak: {new_streak} - Cooldown: 30 seconds")
            
        elif winner == "opponent":
            # Reset winstreak on defeat
            self.battle_cog.winstreaks[self.player.id] = 0
            
            embed = discord.Embed(
                title="💀 DEFEAT",
                description=f"**{self.opponent_name}** wins the battle!",
                color=0xE74C3C
            )
            
            # Show final team status
            player_status = "\n".join([
                f"{'❌' if c['current_hp'] <= 0 else '❤️'} {c['name']}"
                for c in self.player_team
            ])
            opponent_status = "\n".join([
                f"{'❌' if c['current_hp'] <= 0 else '❤️'} {c['name']}"
                for c in self.opponent_team
            ])
            
            embed.add_field(name="Your Team", value=player_status, inline=True)
            embed.add_field(name="Enemy Team", value=opponent_status, inline=True)
            
            embed.set_footer(text=f"Cooldown: 30 seconds")
        else:
            embed = discord.Embed(
                title="⏱️ DRAW",
                description="Battle ended in a draw!",
                color=0x95A5A6
            )
            embed.set_footer(text=f"Cooldown: 30 seconds")
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Update cooldown
        self.battle_cog.battle_cooldowns[self.player.id] = datetime.utcnow()
        self.battle_cog.active_battles.discard(self.player.id)
        
        self.stop()
    
    def update_button_states(self):
        """Update button states - all Command Cards are always available"""
        # Command Cards don't have limited uses, so all buttons stay enabled
        pass
    
    @discord.ui.button(label="Buster Card", style=discord.ButtonStyle.red, emoji="🔴", row=0)
    async def buster_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_attack(interaction, "buster")
    
    @discord.ui.button(label="Arts Card", style=discord.ButtonStyle.blurple, emoji="🔵", row=0)
    async def arts_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_attack(interaction, "arts")
    
    @discord.ui.button(label="Quick Card", style=discord.ButtonStyle.green, emoji="🟢", row=0)
    async def quick_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_attack(interaction, "quick")
    
    @discord.ui.button(label="Forfeit", style=discord.ButtonStyle.grey, emoji="🏳️", row=1)
    async def forfeit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player.id:
            return await interaction.response.send_message("Not your battle!", ephemeral=True)
        
        await self.end_battle(interaction, "opponent")


class Battle(commands.Cog):
    """Interactive PvP Battle System"""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_battles = set()
        self.battle_cooldowns = {}
        self.winstreaks = {}  # {user_id: streak_count}
    
    @commands.command(name="battle", aliases=["b", "fight", "duel"])
    async def battle(self, ctx, opponent: discord.Member = None):
        """Challenge another player to a Fate-style Command Card battle!
        
        Fight using your 3 strongest Servants with turn-based combat.
        Choose your Command Cards strategically to defeat your opponent!
        
        Usage: 
        - !battle - Fight a random opponent
        - !battle @user - Challenge a specific player (coming soon)
        
        Command Cards:
        🔴 Buster Card (1.4-1.7x ATK) - Pure damage
        🔵 Arts Card (1.0-1.3x ATK) - Charges NP gauge +20-30%
        🟢 Quick Card (0.8-1.1x ATK) - 30% crit chance, +10-15% NP
        
        Rewards: 1,000 Mora + 500 EXP + 10% chest chance
        Cooldown: 30 seconds
        """
        # Random battle mode
        if opponent is None:
            return await self._start_random_battle(ctx)
        
        # Player challenge coming soon
        return await ctx.send("❌ Player vs Player battles coming soon! Use `gbattle` for random matches.")
    
    async def _start_random_battle(self, ctx):
        """Start a random AI battle"""
        # Check cooldown
        if ctx.author.id in self.battle_cooldowns:
            last_battle = self.battle_cooldowns[ctx.author.id]
            cooldown_end = last_battle + timedelta(seconds=30)
            now = datetime.utcnow()
            
            if now < cooldown_end:
                time_left = cooldown_end - now
                seconds = int(time_left.total_seconds())
                return await ctx.send(f"⏳ Cooldown: {seconds}s remaining")
        
        if ctx.author.id in self.active_battles:
            return await ctx.send("⚔️ You're already in a battle!")
        
        # Get player's team
        player_pulls = await get_user_pulls(ctx.author.id)
        
        if not player_pulls:
            return await ctx.send("❌ You don't have any characters yet! Use `gwish` to get some.")
        
        player_team = self._select_best_team(player_pulls)
        
        # Get random opponent
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT DISTINCT user_id FROM pulls 
                WHERE user_id != ? 
                ORDER BY RANDOM() 
                LIMIT 1
            """, (ctx.author.id,))
            result = await cursor.fetchone()
        
        if not result:
            return await ctx.send("❌ No opponents available. Try again later!")
        
        opponent_id = result[0]
        opponent_pulls = await get_user_pulls(opponent_id)
        
        if not opponent_pulls:
            return await self._start_random_battle(ctx)
        
        opponent_team = self._select_best_team(opponent_pulls)
        
        # Get opponent name (clean, no AI indicators)
        try:
            opponent_member = await ctx.guild.fetch_member(opponent_id)
            opponent_name = opponent_member.display_name
        except:
            opponent_name = f"Challenger #{opponent_id % 10000}"
        
        # Mark as in battle
        self.active_battles.add(ctx.author.id)
        
        # Create interactive battle
        current_streak = self.winstreaks.get(ctx.author.id, 0)
        view = InteractiveBattleView(
            ctx.author,
            player_team,
            opponent_name,
            opponent_team,
            self,
            ctx.channel,
            is_ai=True,
            current_winstreak=current_streak
        )
        
        embed = await view.update_battle_display()
        await send_embed(ctx, embed, view=view)
    
    def _select_best_team(self, pulls, team_size=3):
        """Select strongest characters"""
        characters = []
        for pull in pulls:
            name, rarity, count, relics, region, hp, atk = pull
            characters.append({
                'name': name,
                'rarity': rarity,
                'region': region,
                'hp': hp,
                'atk': atk,
                'power': hp + atk
            })
        
        characters.sort(key=lambda x: x['power'], reverse=True)
        return characters[:team_size]
    
    @commands.command(name="battlestats", aliases=["bs"])
    async def battle_stats(self, ctx):
        """View your battle team and stats"""
        pulls = await get_user_pulls(ctx.author.id)
        
        if not pulls:
            return await ctx.send("❌ You don't have any characters yet!")
        
        team = self._select_best_team(pulls)
        
        total_hp = sum(c['hp'] for c in team)
        total_atk = sum(c['atk'] for c in team)
        
        embed = discord.Embed(
            title=f"⚔️ {ctx.author.display_name}'s Battle Team",
            description="Your 3 strongest characters:",
            color=0x9B59B6
        )
        
        for i, char in enumerate(team, 1):
            hp_bar = "█" * 20
            char_info = (
                f"```css\n"
                f"[ {char['name']} ] {char['rarity']}\n"
                f"HP  {hp_bar} 100%\n"
                f"    {char['hp']:,}\n"
                f"ATK {char['atk']:,}\n"
                f"PWR {char['power']:,}\n"
                f"```"
            )
            embed.add_field(
                name=f"#{i} Fighter",
                value=char_info,
                inline=True
            )
        
        embed.add_field(
            name="═══ Team Statistics ═══",
            value=f"**Combined HP:** {total_hp:,}\n**Combined ATK:** {total_atk:,}\n**Total Power:** {total_hp + total_atk:,}",
            inline=False
        )
        
        # Check cooldown
        if ctx.author.id in self.battle_cooldowns:
            last_battle = self.battle_cooldowns[ctx.author.id]
            cooldown_end = last_battle + timedelta(minutes=5)
            now = datetime.utcnow()
            
            if now < cooldown_end:
                time_left = cooldown_end - now
                minutes = int(time_left.total_seconds() // 60)
                seconds = int(time_left.total_seconds() % 60)
                embed.set_footer(text=f"⏳ Next battle in: {minutes}m {seconds}s")
            else:
                embed.set_footer(text="✅ Ready to battle")
        else:
            embed.set_footer(text="✅ Ready to battle")
        
        await send_embed(ctx, embed)
    
    @commands.command(name='resetbattle')
    @commands.has_permissions(administrator=True)
    async def reset_battle_cooldown(self, ctx, member: discord.Member = None):
        """Reset battle cooldown for yourself or another user (Admin only)"""
        target = member or ctx.author
        
        if target.id in self.battle_cooldowns:
            del self.battle_cooldowns[target.id]
            await send_embed(ctx, discord.Embed(
                title="✅ Battle Cooldown Reset",
                description=f"Battle cooldown has been reset for {target.mention}",
                color=0x2ecc71
            ))
        else:
            await send_embed(ctx, discord.Embed(
                title="ℹ️ No Cooldown",
                description=f"{target.mention} doesn't have an active battle cooldown",
                color=0x3498db
            ))


async def setup(bot):
    await bot.add_cog(Battle(bot))
