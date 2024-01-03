import asyncio
import discord
import os
import io
import time
import base64
import aiohttp
import requests
from io import BytesIO
from PIL import Image
from discord.ext import commands
from discord.commands import Option


# Instantiate bot object with command prefix and intents
intents = discord.Intents.default()
intents.messages = True  # For messages in guilds
intents.guilds = True  # For guild-related events
intents.presences = True             # If you need to track user statuses or activities
intents.members = True  # For member-related events
intents.message_content = True  # For message content access
intents.reactions = True             # For tracking reactions to messages
intents.dm_messages = True  # To receive direct messages
intents.dm_typing = True  # To detect typing in direct messages
intents.typing = False  # To detect typing in guilds

bot = commands.Bot(command_prefix='/', intents=intents)

# Retrieve environment variables for OpenAI and Discord Bot Token
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
BOT_TOKEN = os.getenv('AICHECK_DISCORD_BOT_TOKEN')
ADMIN_USER_ID = os.getenv('YOUR_DISCORD_ID')  # Retrieve your Discord ID from environment variable


# Dictionary to track the last use time of the command for each user
last_use_time = {}

def rate_limit_check():
    async def predicate(ctx):
        user_id = ctx.author.id
        current_time = time.time()

        if user_id in last_use_time:
            time_since_last_use = current_time - last_use_time[user_id]
            if time_since_last_use < 5:  # Less than 5 seconds since last use
                cooldown_remaining = 5 - time_since_last_use
                await ctx.respond(f"Please wait {cooldown_remaining:.2f} more seconds before using this command again.", ephemeral=True)
                return False

        last_use_time[user_id] = current_time
        return True

    return commands.check(predicate)

@bot.slash_command(description="PASTE Image for AI to Analyze")
@commands.cooldown(2, 86400, commands.BucketType.user)  # Two uses per day
async def aicheck(ctx, description: Option(str, "Enter any details about the image", required=False)):
    # Check if the command is invoked in a server
    if not ctx.guild:
        await ctx.respond("The `/aicheck` command can only be used in a server.", ephemeral=True)
        return

    # Check if the command is used in the "aicheck" channel
    if ctx.channel.name != "aicheck":
        await ctx.respond("Please use the `/aicheck` command in the 'aicheck' channel.", ephemeral=True)
        return

    # Bypass cooldown for the admin user
    if str(ctx.author.id) == ADMIN_USER_ID:
        ctx.command.reset_cooldown(ctx)

    await ctx.respond("Please PASTE an image.", ephemeral=True)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and len(m.attachments) > 0

    try:
        message = await bot.wait_for('message', check=check, timeout=120.0)
        attachment = message.attachments[0]
        encoded_image, error_message = await process_and_encode_image(attachment)
        
        # Delete the user's message after processing the image
        await message.delete()
        
        if error_message:
            await ctx.respond(error_message, ephemeral=True)
            return

        # Setup the payload for OpenAI API
        prompt = "Examine the quality and rendering, character reality, limb/digit count, details to determine if AI generation is TRUE or FALSE; Explain conclusions briefly. Reveal no personal information about the fictional characters or subjects. Limit the response to under two paragraphs. If determined to be AI generated append ' (APPEARS AI GENERATED)'."
        if description:
            prompt += f" Additional details provided: {description}"

        payload = {
            "model": "gpt-4-vision-preview",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}", "detail": "high"}},
                    ],
                }
            ],
            "max_tokens": 300
        }

        headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"}
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)

        if response.status_code == 200:
            analysis = response.json()["choices"][0]["message"]["content"]
#           save_health_analysis(str(ctx.author.id), message.attachments[0].url, analysis, description)
            embed = discord.Embed(title=" <:star:> Image Analysis <:star:> ", description=analysis, color=discord.Color.green())
            embed.set_thumbnail(url=message.attachments[0].url)
            await ctx.respond(embed=embed, ephemeral=True)
        else:
            await ctx.respond("Failed to analyze the image. Please try again later.")

    except asyncio.TimeoutError:
        await ctx.channel.send('You did not upload an image in time.')
        return

async def process_and_encode_image(attachment):
    # Check if file size exceeds 6 MB
    if attachment.size > 6 * 1024 * 1024:
        # If the image is too large, attempt to compress it
        image_data = io.BytesIO()
        await attachment.save(image_data)
        image = Image.open(image_data)

        # Adjust resolution if it's greater than 4K
        if image.width > 3840 or image.height > 2160:
            image.thumbnail((3840, 2160), Image.Resampling.LANCZOS)

        # Compress the image and check the size again
        compressed_image_data = io.BytesIO()
        image.save(compressed_image_data, format='JPEG', quality=85)
        compressed_image_size = compressed_image_data.tell()
        
        if compressed_image_size > 6 * 1024 * 1024:
            return None, "Unable to reduce the file size sufficiently. Please upload a smaller image."

        compressed_image_data.seek(0)  # Reset the stream position to the start
        return base64.b64encode(compressed_image_data.getvalue()).decode('utf-8'), None
    else:
        # If the image is within size limits, process as before
        image_data = io.BytesIO()
        await attachment.save(image_data)
        image = Image.open(image_data)

        # Check and adjust resolution if it's greater than 4K
        if image.width > 3840 or image.height > 2160:
            image.thumbnail((3840, 2160), Image.Resampling.LANCZOS)

        # Convert the image back to BytesIO for further processing
        new_image_data = io.BytesIO()
        image.save(new_image_data, format=image.format)
        new_image_data.seek(0)  # Reset the stream position to the start

        return base64.b64encode(new_image_data.getvalue()).decode('utf-8'), None

def get_thumbnail_image(image_folder):
    # Get the first image in the folder to use as a thumbnail
    image_paths = glob.glob(os.path.join(image_folder, '*.jpg')) + glob.glob(os.path.join(image_folder, '*.png'))
    return image_paths[0] if image_paths else None



@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print('------\n')
    
# Run the bot
bot.run(BOT_TOKEN)
