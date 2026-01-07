import discord
from discord.ext import commands
import aiohttp
import os
from collections import defaultdict
from datetime import datetime, timedelta


class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv('OPENAI_API_KEY')
        # Store conversation history per user (last 10 messages, expires after 30 min)
        self.conversations = defaultdict(list)
        self.last_activity = {}
        
    def _get_system_prompt(self):
        """System prompt to make the bot sound natural"""
        return """You are a casual, friendly Discord bot in a gaming/minigames server. 
You chat naturally like a regular person - no formal language, no "I'm an AI" disclaimers.
Keep responses SHORT (1-3 sentences max unless asked for detail).
Use casual language, contractions, and be chill. You can use emojis occasionally but don't overdo it.
You help with questions, chat about games, and just hang out like a friend.
If asked about games, you know the server has: slots, blackjack, coinflip, wheel, mines, rps, connect4, tictactoe, dice.
Don't mention you're an AI unless directly asked."""

    def _clean_old_conversations(self):
        """Remove conversations older than 30 minutes"""
        now = datetime.now()
        cutoff = now - timedelta(minutes=30)
        old_users = [uid for uid, time in self.last_activity.items() if time < cutoff]
        for uid in old_users:
            if uid in self.conversations:
                del self.conversations[uid]
            del self.last_activity[uid]

    async def _get_ai_response(self, user_id: int, message: str) -> str:
        """Get AI response from OpenAI"""
        if not self.api_key:
            return "I'm not configured yet! The bot owner needs to add an OpenAI API key to the .env file."
        
        # Clean old conversations
        self._clean_old_conversations()
        
        # Add user message to history
        self.conversations[user_id].append({"role": "user", "content": message})
        
        # Keep only last 10 messages (5 exchanges)
        if len(self.conversations[user_id]) > 10:
            self.conversations[user_id] = self.conversations[user_id][-10:]
        
        # Update last activity
        self.last_activity[user_id] = datetime.now()
        
        # Build messages for API
        messages = [{"role": "system", "content": self._get_system_prompt()}]
        messages.extend(self.conversations[user_id])
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-3.5-turbo",
                        "messages": messages,
                        "max_tokens": 150,
                        "temperature": 0.9,
                    },
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"OpenAI API error: {error_text}")
                        return "Sorry, I'm having trouble thinking right now. Try again in a sec?"
                    
                    data = await response.json()
                    ai_message = data["choices"][0]["message"]["content"].strip()
                    
                    # Add AI response to history
                    self.conversations[user_id].append({"role": "assistant", "content": ai_message})
                    
                    return ai_message
        except Exception as e:
            print(f"Error getting AI response: {e}")
            return "My brain just lagged out lol, try again?"

    @commands.command(name="hey", aliases=["chat", "ask"])
    async def chat_with_bot(self, ctx, *, message: str = None):
        """Chat with the bot! Ask questions or just hang out. [PREMIUM ONLY]
        
        Examples:
        !hey what's up?
        !chat tell me a joke
        !ask how do I play blackjack?
        """
        # Check premium status
        premium_cog = self.bot.get_cog("Premium")
        if not premium_cog or not await premium_cog.is_premium(ctx.author.id):
            embed = discord.Embed(
                title="🔒 Premium Feature",
                description="AI Chat requires **Premium** subscription!",
                color=0xFFD700
            )
            embed.add_field(
                name="⭐ Premium Benefits:",
                value=(
                    "<a:arrow:1437968863026479258> **AI Chat Bot** - Natural conversations!\n"
                    "<a:arrow:1437968863026479258> **3x higher betting limits**\n"
                    "<a:arrow:1437968863026479258> **3x daily rewards**\n"
                    "<a:arrow:1437968863026479258> **Unlimited RPS plays**\n"
                    "<a:arrow:1437968863026479258> **Unlimited bank deposits**\n"
                    "<a:arrow:1437968863026479258> **1M max loans & 3 per day**\n"
                    "<a:arrow:1437968863026479258> Premium badge & early access"
                ),
                inline=False
            )
            embed.add_field(
                name="💰 Pricing:",
                value="**$9.99/month** or **$25/3 months** (save $5!)",
                inline=False
            )
            embed.add_field(
                name="Get Started",
                value="Use `gpremium` for subscription info!",
                inline=False
            )
            return await ctx.send(embed=embed)
        
        if not message:
            await ctx.send("To start a conversation do `ghey how are you`")
            return
        
        # Show typing indicator
        async with ctx.typing():
            response = await self._get_ai_response(ctx.author.id, message)
        
        await ctx.send(response)
    
    @commands.command(name="forget", aliases=["reset"])
    async def forget_conversation(self, ctx):
        """Clear your conversation history with the bot"""
        if ctx.author.id in self.conversations:
            del self.conversations[ctx.author.id]
        if ctx.author.id in self.last_activity:
            del self.last_activity[ctx.author.id]
        await ctx.send("Forgot our whole convo, starting fresh! 🧠")


async def setup(bot):
    await bot.add_cog(Chat(bot))
