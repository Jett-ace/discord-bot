import discord
from discord.ext import commands
from deep_translator import GoogleTranslator
from deep_translator.constants import GOOGLE_LANGUAGES_TO_CODES
from utils.embed import send_embed


class Translate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Map of common language names to codes
        self.language_map = GOOGLE_LANGUAGES_TO_CODES

    @commands.command(name="translate", aliases=["tr"])
    async def translate(self, ctx, target_lang: str = "english"):
        """Translate a message to any language. Reply to a message and use gtranslate [language]
        
        Examples:
        gtranslate - Translates to English (default)
        gtranslate spanish - Translates to Spanish
        gtranslate arabic - Translates to Arabic
        gtranslate japanese - Translates to Japanese
        
        Supports 100+ languages!
        """
        # Check if this is a reply to another message
        if not ctx.message.reference:
            await ctx.send("❌ Please reply to a message you want to translate!\nUsage: Reply to a message and type `gtranslate [language]`")
            return

        try:
            # Get the message being replied to
            replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            text_to_translate = replied_message.content

            if not text_to_translate:
                await ctx.send("❌ The message you replied to has no text to translate!")
                return

            # Normalize target language name
            target_lang = target_lang.lower().strip()
            
            # Get language code
            if target_lang not in self.language_map:
                # Try to find a close match
                matches = [lang for lang in self.language_map.keys() if target_lang in lang]
                if matches:
                    target_lang = matches[0]
                else:
                    await ctx.send(f"❌ Language `{target_lang}` not recognized.\n Try: english, spanish, french, german, arabic, japanese, chinese, etc.\nUse `glanguages` to see all supported languages.")
                    return
            
            target_code = self.language_map[target_lang]

            # Detect source language and translate
            translator = GoogleTranslator(source='auto', target=target_code)
            translated_text = translator.translate(text_to_translate)

            # Detect the source language for display
            detected = GoogleTranslator(source='auto', target='en').translate(text_to_translate[:50])
            source_detector = GoogleTranslator(source='auto', target='en')
            
            # Get source language name
            try:
                # Try to detect source language
                from deep_translator import single_detection
                detected_lang_code = single_detection(text_to_translate, api_key='auto')
                source_lang_name = [k for k, v in self.language_map.items() if v == detected_lang_code]
                source_lang_name = source_lang_name[0].title() if source_lang_name else "Unknown"
            except:
                source_lang_name = "Auto-detected"

            # Create embed
            embed = discord.Embed(
                title="Translation",
                color=0x5865F2
            )
            
            embed.add_field(
                name=f"Original ({source_lang_name})",
                value=f"```{text_to_translate[:1000]}```",
                inline=False
            )
            
            embed.add_field(
                name=f"Translation ({target_lang.title()})",
                value=f"```{translated_text[:1000]}```",
                inline=False
            )
            
            embed.set_footer(text=f"Translated by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            
            await send_embed(ctx, embed)

        except Exception as e:
            print(f"Translation error: {e}")
            await ctx.send(f"❌ An error occurred while translating: {str(e)}\nMake sure the text is valid and try again.")

    @commands.command(name="languages", aliases=["langs"])
    async def languages(self, ctx):
        """Show all supported languages for translation"""
        
        # Get all languages and organize them
        all_langs = sorted(self.language_map.keys())
        
        # Split into chunks for better display
        chunk_size = 20
        chunks = [all_langs[i:i + chunk_size] for i in range(0, len(all_langs), chunk_size)]
        
        embed = discord.Embed(
            title="Supported Languages",
            description=f"Total: **{len(all_langs)}** languages supported!\n\nUse `gtranslate <language>` while replying to a message to translate it to the language you want.",
            color=0x5865F2
        )
        
        for i, chunk in enumerate(chunks[:3], 1):  # Show first 3 chunks (60 languages)
            langs_text = ", ".join(f"`{lang}`" for lang in chunk)
            embed.add_field(
                name=f"Languages (Part {i})",
                value=langs_text,
                inline=False
            )
        
        # Add popular languages example
        embed.add_field(
            name="Popular Examples",
            value="`english`, `spanish`, `french`, `german`, `arabic`, `japanese`, `chinese (simplified)`, `chinese (traditional)`, `korean`, `russian`, `portuguese`, `italian`, `hindi`, `turkish`",
            inline=False
        )
        
        embed.set_footer(text="Reply to any message and use gtranslate [language] to translate it!")
        
        await send_embed(ctx, embed)


async def setup(bot):
    await bot.add_cog(Translate(bot))
