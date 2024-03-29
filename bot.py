import interactions
from interactions import OptionType, SlashContext, slash_command
import sqlite3
from interactions.ext.paginators import Page, Paginator
from interactions.models import Member
import random
import asyncio
from datetime import datetime, timedelta
import secrets
from typing import Optional
import json

class ForwardButton(interactions.Button):
    def __init__(self, style=interactions.ButtonStyle.PRIMARY, emoji="➡️"):
        super().__init__(custom_id="forward_page", style=style, emoji=emoji)

class BackwardButton(interactions.Button):
    def __init__(self, style=interactions.ButtonStyle.PRIMARY, emoji="⬅️"):
        super().__init__(custom_id="backward_page", style=style, emoji=emoji)
    
conn = sqlite3.connect('C:\\Users\\kosta\\Documents\\code\\cards.db')
c = conn.cursor()




c.execute('CREATE TABLE IF NOT EXISTS cards (card_code TEXT PRIMARY KEY, rarity TEXT, group_name TEXT, member_name TEXT, image_url TEXT, creator INTEGER, droppable BOOLEAN DEFAULT 1)')
    

c.execute('UPDATE cards SET card_code = UPPER(rarity || "." || group_name || "." || member_name)')


c.execute('CREATE TABLE IF NOT EXISTS inventories (user_id TEXT, card_code TEXT, quantity INTEGER)')
c.execute('CREATE TABLE IF NOT EXISTS balances (user_id TEXT PRIMARY KEY, balance INTEGER)')
c.execute('CREATE TABLE IF NOT EXISTS marketplace (unique_code TEXT, card_code TEXT, seller_id TEXT, price INTEGER)')
c.execute('SELECT DISTINCT card_code FROM inventories')



# Commit changes
conn.commit()

c.execute('SELECT * FROM cards')
print(c.fetchall())





bot_token = ""
bot = interactions.Client(
    token=bot_token,
    default_scope="applications.commands"
)

drop_command_enabled = True

ITEMS_PER_PAGE = 10

# Load custom rarities from file
with open("custom_rarities.json", "r") as file:
    CUSTOM_RARITIES = json.load(file)

RARITIES = ["EVENT", "EPIC", "RARE", "UNCOMMON", "COMMON"]
CUSTOM_RARITIES = ["EVENT1", "EVENT2"]  # Add your custom rarity names

# Define percentage chances for each rarity
percentage_chances = {
    "EVENT": 3,
    "EPIC": 5,
    "RARE": 8,
    "UNCOMMON": 15,
    "COMMON": 60,
    # Add your custom rarities with equal chances
    **{custom_rarity: 10 for custom_rarity in CUSTOM_RARITIES}
}








DAILY_COOLDOWN = {}
WORK_COOLDOWN = {}


def insert_card(rarity, group, member, image_url, creator):
    c.execute("INSERT INTO cards (rarity, group_name, member_name, image_url, creator) VALUES (?, ?, ?, ?, ?)",
              (rarity, group, member, image_url, creator))
    conn.commit()


def add_to_inventory(user_id, card_code):
   
    c.execute("SELECT quantity FROM inventories WHERE user_id = ? AND card_code = ?", (user_id, card_code))
    existing_quantity = c.fetchone()

    if existing_quantity:
        new_quantity = existing_quantity[0] + 1
        c.execute("UPDATE inventories SET quantity = ? WHERE user_id = ? AND card_code = ?", (new_quantity, user_id, card_code))
    else:
        c.execute("INSERT INTO inventories (user_id, card_code, quantity) VALUES (?, ?, ?)", (user_id, card_code, 1))

    conn.commit()

def add_to_balance(user_id, amount):
    c.execute("INSERT OR IGNORE INTO balances VALUES (?, 0)", (user_id,))
    c.execute("UPDATE balances SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

def get_user_balance(user_id):
    c.execute("SELECT balance FROM balances WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    return result[0] if result else 0


def is_daily_cooldown(user_id):
    last_daily_time = DAILY_COOLDOWN.get(user_id)
    if last_daily_time is not None:
        elapsed_time = datetime.now() - last_daily_time
        remaining_time = timedelta(days=1) - elapsed_time
        return elapsed_time < timedelta(days=1), remaining_time
    return False, None

def is_work_cooldown(user_id):
    last_work_time = WORK_COOLDOWN.get(user_id)
    if last_work_time is not None:
        elapsed_time = datetime.now() - last_work_time
        remaining_time = timedelta(hours=1) - elapsed_time
        return elapsed_time < timedelta(hours=1), remaining_time
    return False, None

try:
    with open("custom_rarities.json", "r") as file:
        CUSTOM_RARITIES = json.load(file)
except FileNotFoundError:
    # If the file is not found, initialize with an empty list
    CUSTOM_RARITIES = []


@slash_command(
    name="viewcard",
    description="View details of a specific card in the pool",
    options=[
        {
            "name": "card_code",
            "description": "The card code to view (e.g., rarity_group_member)",
            "type": OptionType.STRING,
            "required": True,
        },
    ],
)
async def view_card(ctx: SlashContext, card_code: str):
    card_details = get_card_details(card_code)

    if card_details:
        rarity, group, member, image_url = card_details

        embed = interactions.Embed(title=f"{card_code.upper()} Card")
        embed.set_image(url=image_url)
        embed.add_field(name="Rarity", value=rarity, inline=True)
        embed.add_field(name="Group", value=group, inline=True)
        embed.add_field(name="Member", value=member, inline=True)

        await ctx.send(embed=embed)
    else:
        await ctx.send(f"Card {card_code.upper()} not found in the pool.")

@slash_command(
    name="newcard",
    description="Adds a new card to the card database (admin, card creator, and mod roles only)",
    options=[
        {
            "name": "card_code",
            "description": "The card code in the format of rarity_group_member",
            "type": OptionType.STRING,
            "required": True,
        },
        {
            "name": "image_url",
            "description": "The URL of the card image",
            "type": OptionType.STRING,
            "required": True,
        },
        {
            "name": "creator",
            "description": "The creator of the card",
            "type": OptionType.USER,
            "required": True,
        },
        {
            "name": "droppable",
            "description": "Is the card droppable?",
            "type": OptionType.BOOLEAN,
            "required": True,
        },
    ],
)
async def add_card(ctx: SlashContext, card_code: str, image_url: str, creator: Member, droppable: bool):
    allowed_user_ids = [868784129372725279, 840434880419987466, 757304883878690866, 933865723812524032, 1135960567232860243, 933865723812524032, 838412060073132094]
    allowed_role_ids = [1127549099638530098, 1158081583807471656, 1158283472155181066, 1158282772360736788]
    
    if (
        ctx.author.id in allowed_user_ids or
        any(role.id in allowed_role_ids for role in ctx.author.roles)
    ):
        creator_id = creator.id  
        parts = card_code.split(".")
        rarity = parts[0].upper() if parts[0].upper() in RARITIES else parts[0].upper()
        group = parts[1].upper()
        member = parts[2].upper()

        insert_card(rarity, group, member, image_url, creator_id, droppable)
        droppable_status = "Droppable" if droppable else "Not Droppable"
        await ctx.send(f"Card {card_code.upper()} added! Created by <@{creator_id}>. {droppable_status}")
    else:
        await ctx.send("Only authorized users with the correct role or user ID can add cards.")



def insert_card(rarity, group, member, image_url, creator_id, droppable):
    c.execute(
        "INSERT INTO cards (rarity, group_name, member_name, image_url, creator, droppable) VALUES (?, ?, ?, ?, ?, ?)",
        (rarity, group, member, image_url, creator_id, droppable),
    )
    conn.commit()


@slash_command(
    name="setalldroppable",
    description="Set all existing cards to droppable",
)
async def set_all_droppable(ctx: SlashContext):
    allowed_user_ids = ['868784129372725279', '838412060073132094', '933865723812524032', '578344208025255937', '757304883878690866']

    if str(ctx.author.id) in allowed_user_ids:
        guild_id = 1127548284110635071  
        user_roles = [role.name.lower() for role in ctx.author.roles if role.guild.id == guild_id]

        if str(ctx.author.id) == "868784129372725279" or "Admin" in user_roles:
            c.execute("UPDATE cards SET droppable = 1")
            conn.commit()
            await ctx.send("All existing cards have been set to droppable.")
        else:
            await ctx.send("Only the bot owner or Admin can set all cards to droppable.")
    else:
        await ctx.send("You are not authorized to use this command.")

@slash_command(
    name="toggledroppable",
    description="Toggle the droppable status of a card",
    options=[
        {
            "name": "card_code",
            "description": "The code of the card",
            "type": interactions.OptionType.STRING,
            "required": True,
        },
        {
            "name": "droppable",
            "description": "Select if the card should be droppable",
            "type": interactions.OptionType.BOOLEAN,
            "required": True,
        },
    ],
)
async def toggle_droppable(ctx: SlashContext, card_code: str, droppable: bool):
    # Check if the user is the bot owner or has the necessary permissions
    if ctx.author.id == 868784129372725279 or any(role.id == 1127549099638530098 for role in ctx.author.roles):
        # Update the droppable status based on the user's input
        c.execute("UPDATE cards SET droppable = ? WHERE card_code = ?", (droppable, card_code))
        conn.commit()

        await ctx.send(f"The droppable status of card {card_code} has been updated to {droppable}.")
    else:
        await ctx.send("You do not have the necessary permissions to use this command.")

@slash_command(
    name="removecard",
    description="Remove a card from the database (admin only)",
    options=[
        {
            "name": "card_code",
            "description": "The card code in the format of rarity_group_member",
            "type": OptionType.STRING,
            "required": True,
        },
    ],
)
async def remove_card(ctx: SlashContext, card_code: str):
    if str(ctx.author.id) in allowed_user_ids:
        card_details = get_card_details(card_code)

        if card_details:
            rarity, group, member, image_url = card_details

            c.execute("DELETE FROM cards WHERE rarity = ? AND group_name = ? AND member_name = ?", (rarity, group, member))
            conn.commit()

            c.execute("DELETE FROM inventories WHERE card_code = ?", (card_code,))
            conn.commit()

            c.execute("DELETE FROM marketplace WHERE card_code = ?", (card_code,))
            conn.commit()

            await ctx.send(f"Card {card_code.upper()} removed from the database.")
        else:
            await ctx.send(f"Card {card_code.upper()} not found in the database.")
    else:
        await ctx.send("You are not authorized to use this command.")

@slash_command(
    name="disable_drop",
    description="Enable or disable the drop command",
    options=[
        {
            "name": "status",
            "description": "True to disable, False to enable",
            "type": interactions.OptionType.BOOLEAN,
            "required": True,
        },
    ],
)
async def disable_drop(ctx: interactions.SlashContext, status: bool):
    global drop_command_enabled

    if ctx.author.id == 868784129372725279:
        drop_command_enabled = not status
        await ctx.send(f"The drop command is now {'disabled' if not drop_command_enabled else 'enabled'}.")
    else:
        await ctx.send("You do not have permission to use this command.")

cooldowns = {}

@slash_command(
    name="drop",
    description="Drops a random card",
)
async def drop(ctx: interactions.SlashContext):
    if not drop_command_enabled:
        await ctx.send("The drop command is currently disabled.")
        return
    
    # Define event drop chance and drop rates
    event_drop_chance = 0.26  # 3% chance of dropping an event card
    drop_rates = {
        "COMMON": 79.92,
        "UNCOMMON": 15.98,
        "RARE": 3.2,
        "EPIC": 0.64,
        # Add your custom rarities here with their drop rates
    }
    
    # Function to select the rarity based on drop rates
    def select_rarity():
        # Generate a random number between 0 and 100
        random_number = random.randint(1, 100)
        
        # Determine if it's an event drop
        if random_number <= event_drop_chance:
            return "EVENT"
        
        # Determine the rarity based on drop rates
        cumulative_probability = 0
        for rarity, rate in drop_rates.items():
            cumulative_probability += rate
            if random_number <= cumulative_probability:
                return rarity
        
        # If for some reason the loop ends without returning a rarity, return "COMMON" as a fallback
        return "COMMON"
    
    # Function to select a droppable card of a given rarity
    def select_card(rarity):
        # If the selected rarity is "EVENT", set it as the default rarity for card selection
        if rarity == "EVENT":
            rarity = select_rarity()
        
        # Query your database to select a droppable card of the given rarity
        # Implement your database logic here to select a card of the specified rarity
        # Return the selected card details or None if no droppable card is found
        
        # Example query:
        c.execute("SELECT rarity, group_name, member_name, image_url, creator FROM cards WHERE rarity = ? AND droppable = 1 ORDER BY RANDOM() LIMIT 1", (rarity,))
        return c.fetchone()
    
    now = datetime.now()
    cooldown_key = str(ctx.author.id)  # Ensure the cooldown_key is a string

    # Set the maximum number of rerolls
    max_rerolls = 7

    # Get the cooldown expiration time, defaulting to now if not found
    cooldown_expiration = cooldowns.get(cooldown_key, now)

    if now < cooldown_expiration:
        # Calculate remaining cooldown time
        remaining_cooldown = (cooldown_expiration - now).seconds
        await ctx.respond(f"This command is on cooldown! Try again in {remaining_cooldown} seconds.", ephemeral=True)
        return

    # Select the rarity for the dropped card
    chosen_rarity = select_rarity()

    card = None  # Initialize card to None

    for reroll_count in range(max_rerolls):
        card = select_card(chosen_rarity)
        if card:
            break
        else:
            # If no droppable card is found for the chosen rarity, reroll with a different rarity
            chosen_rarity = select_rarity()

    # Check if card is None
    if card is None:
        await ctx.respond("No droppable card found. Please try again.")
        return

    rarity, group, member, image_url, creator = card
    card_code = f"{rarity}.{group}.{member}"

    add_to_inventory(str(ctx.author.id), card_code)

    embed = interactions.Embed(title=f"{card_code.upper()} Card")
    embed.set_image(url=image_url)
    embed.add_field(name="Rarity", value=rarity, inline=True)
    embed.add_field(name="Group", value=group, inline=True)
    embed.add_field(name="Member", value=member, inline=True)
    embed.add_field(
        name="Card Creator",
        value=f"Created by <@{creator}>",
        inline=True,
    )

    # Set the cooldown for the user
    cooldown_duration = timedelta(seconds=0)  # Adjust the cooldown duration as needed
    cooldowns[cooldown_key] = now + cooldown_duration

    await ctx.respond(
        content=f"{ctx.author.mention}, you got a {card_code.upper()} card!",
        embed=embed,
    )








@slash_command(
    name="addevent",
    description="Adds a new custom event rarity to the bot",
    options=[
        {
            "name": "event_name",
            "description": "The name of the custom event rarity",
            "type": OptionType.STRING,
            "required": True,
        },
    ],
)
async def add_event(ctx: SlashContext, event_name: str):
    # Assuming these are defined earlier in your script
    # If not, define them appropriately
    RARITIES = ["EVENT", "EPIC", "RARE", "UNCOMMON", "COMMON"]
    CUSTOM_RARITIES = ["EVENT1", "EVENT2"]
    weights = {
        "EVENT": 5,
        "EPIC": 5,
        "RARE": 15,
        "UNCOMMON": 20,
        "COMMON": 60,
        **{custom_rarity: 10 for custom_rarity in CUSTOM_RARITIES}
    }
    card_weights = {rarity: weight for rarity, weight in weights.items() if weight > 0}

    if event_name.upper() not in CUSTOM_RARITIES:
        CUSTOM_RARITIES.append(event_name.upper())

        # Save the updated list to the file
        with open("custom_rarities.json", "w") as file:
            json.dump(CUSTOM_RARITIES, file)

        # Update rarities and weights
        RARITIES.append(event_name.upper())
        weights[event_name.upper()] = 10  # Set the predefined drop rate for custom event rarities
        card_weights[event_name.upper()] = 10  # Set the weight for the new custom event rarity

        await ctx.send(f"Custom event rarity '{event_name}' added.")
    else:
        await ctx.send(f"Custom event rarity '{event_name}' already exists. Use a different name.")




@slash_command(
    name="cd",
    description="Check remaining cooldown for daily, work, and drop commands",
)
async def check_cooldown(ctx: SlashContext):
    user_id = str(ctx.author.id)

    daily_on_cooldown, daily_remaining_time = is_daily_cooldown(user_id)
    work_on_cooldown, work_remaining_time = is_work_cooldown(user_id)
    drop_on_cooldown, drop_remaining_time = is_drop_cooldown(user_id)

    embed = interactions.Embed(title="Cooldowns")
    embed.add_field(name="Daily Command", value=get_cooldown_string(daily_on_cooldown, daily_remaining_time))
    embed.add_field(name="Work Command", value=get_cooldown_string(work_on_cooldown, work_remaining_time))
    embed.add_field(name="Drop Command", value=get_cooldown_string(drop_on_cooldown, drop_remaining_time))

    await ctx.send(embed=embed)

def get_cooldown_string(on_cooldown, remaining_time):
    if on_cooldown:
        remaining_time_str = str(remaining_time).split(".")[0]
        return f"Cooldown: {remaining_time_str}"
    else:
        return "Not on cooldown"

def is_drop_cooldown(user_id):
    now = datetime.now()
    cooldown_key = user_id

    # Get the cooldown expiration time, defaulting to now if not found
    cooldown_expiration = cooldowns.get(cooldown_key, now)

    if now < cooldown_expiration:
        # Calculate remaining cooldown time
        remaining_time = cooldown_expiration - now
        return True, remaining_time
    else:
        return False, None

allowed_user_ids = ['868784129372725279', '838412060073132094', '933865723812524032', '578344208025255937', '757304883878690866']

@slash_command(
    name="gift",
    description="Gifts a specific card to a user from your inventory",
    options=[
        {
            "name": "user",
            "description": "The user to gift a card to",
            "type": OptionType.USER,
            "required": True,
        },
        {
            "name": "card_code",
            "description": "The card code to gift (e.g., rarity_group_member)",
            "type": OptionType.STRING,
            "required": True,
        },
    ],
)
async def gift(ctx: SlashContext, user: interactions.User, card_code: str):
    card_code = card_code.upper()
    
    user_id = str(ctx.author.id)
    c.execute("SELECT quantity FROM inventories WHERE user_id = ? AND card_code = ?", (user_id, card_code))
    existing_quantity = c.fetchone()

    if existing_quantity and existing_quantity[0] > 0:
        c.execute("UPDATE inventories SET quantity = quantity - 1 WHERE user_id = ? AND card_code = ?", (user_id, card_code))
        conn.commit()

        add_to_inventory(str(user.id), card_code)

        recipient_display_name = user.display_name

        rarity, group, member, image_url = get_card_details(card_code)
        embed = interactions.Embed()
        embed.set_image(url=image_url)
        embed.title = f"{card_code} card"

        await ctx.send(content=f"You gifted a {card_code} card to {recipient_display_name}!", embed=embed)
    else:
        await ctx.send(f"You don't have the specified card ({card_code}) in your inventory!")
@slash_command(
    name="bulkgift",
    description="Gifts multiple cards to a user from your inventory",
    options=[
        {
            "name": "user",
            "description": "The user to gift cards to",
            "type": OptionType.USER,
            "required": True,
        },
        {
            "name": "card_codes",
            "description": "The card codes and quantities to gift (e.g., rarity_group_member/2, another_card/3)",
            "type": OptionType.STRING,
            "required": True,
        },
    ],
)
async def bulkgift(ctx: SlashContext, user: interactions.User, card_codes: str):
    card_codes_and_quantities = card_codes.upper().split(',')
    user_id = str(ctx.author.id)

    gifted_cards = []

    for entry in card_codes_and_quantities:
        card_code, quantity_str = map(str.strip, entry.split('/'))
        quantity = int(quantity_str) if quantity_str.isdigit() else 1

        for _ in range(quantity):
            c.execute("SELECT quantity FROM inventories WHERE user_id = ? AND card_code = ?", (user_id, card_code))
            existing_quantity = c.fetchone()

            if existing_quantity and existing_quantity[0] > 0:
                c.execute("UPDATE inventories SET quantity = quantity - 1 WHERE user_id = ? AND card_code = ?", (user_id, card_code))
                conn.commit()

                add_to_inventory(str(user.id), card_code)

                rarity, group, member, image_url = get_card_details(card_code)
                gifted_cards.append(f"{card_code} card")

    if gifted_cards:
        recipient_display_name = user.display_name
        gifted_cards_str = "\n".join(gifted_cards)

        embed = interactions.Embed()
        embed.title = f"Gifted cards to {recipient_display_name}"
        embed.description = gifted_cards_str

        await ctx.send(embed=embed)
    else:
        await ctx.send("No cards were gifted.")



@slash_command(
    name="work",
    description="Earn Dallas by working",
)
async def work(ctx: SlashContext):
    user_id = str(ctx.author.id)

    on_cooldown, remaining_time = is_work_cooldown(user_id)
    if on_cooldown:
        minutes, seconds = divmod(remaining_time.total_seconds(), 60)
        remaining_time_str = f"{int(minutes)} minutes and {int(seconds)} seconds"
        embed = interactions.Embed()
        embed.title = "Work Command - Cooldown"
        embed.description = f"Sorry, you need to wait {remaining_time_str} before working again."
        await ctx.send(embed=embed)
    else:
        earnings = random.randint(100, 500)
        add_to_balance(user_id, earnings)
        WORK_COOLDOWN[user_id] = datetime.now()

        work_messages = [
            f"You helped organize an Itzy fan meeting and earned {earnings} Dallas.",
            f"After a day of dance practice with Yeji, you earned {earnings} Dallas.",
            f"While promoting Itzy's latest album, you earned {earnings} Dallas.",
            f"You joined Yeji for a workout session and earned {earnings} Dallas.",
        ]

        message = random.choice(work_messages)

        updated_balance = get_user_balance(user_id)

        embed = interactions.Embed()
        embed.title = "Work Command"
        embed.description = f"{message}\n\nYou now have {updated_balance} Dallas."
        await ctx.send(embed=embed)

@interactions.slash_command(
    name="oppay",
    description="Admin command to pay any user with Dallas",
    options=[
        {
            "name": "user",
            "description": "The user to pay",
            "type": OptionType.USER,
            "required": True,
        },
        {
            "name": "amount",
            "description": "The amount of Dallas to pay",
            "type": OptionType.INTEGER,
            "required": True,
        },
    ],
)
async def oppay(ctx: SlashContext, user: interactions.User, amount: int):
    if any(role.name == "Admin" for role in ctx.author.roles) and ctx.guild.id == 1127548284110635071:
        if amount <= 0:
            embed = interactions.Embed(color=0xFF0000)  
            embed.title = "Error"
            embed.description = "That's not a valid value for the amount."
            await ctx.send(embed=embed)
            return

        target_user_id = str(user.id)

        add_to_balance(target_user_id, amount)

        embed = interactions.Embed()
        embed.title = "Admin Payment Successful"
        embed.description = f"{ctx.author.display_name} (Admin) has paid {user.display_name} {amount} Dallas!"
        await ctx.send(embed=embed)
    else:
        await ctx.send("You do not have permission to use this command.")

@slash_command(
    name="opgift",
    description="Gift a user any card in the database (Admin only)",
    options=[
        {
            "name": "user",
            "description": "The user to gift cards to",
            "type": OptionType.USER,
            "required": True,
        },
        {
            "name": "cards",
            "description": "List of card codes to gift (comma-separated)",
            "type": OptionType.STRING,
            "required": True,
        },
    ],
)
async def opgift(ctx: SlashContext, user: interactions.User, cards: str):
    admin_role_name = "Admin"
    base_server_id = 1127548284110635071

    if (
        any(role.name == admin_role_name for role in ctx.author.roles) and
        ctx.guild.id == base_server_id
    ):
        # Split the input string into a list of card codes
        card_list = [card.strip().upper() for card in cards.split(',')]

        # Check if all card codes are valid
        if not all(get_card_details(card) for card in card_list):
            await ctx.send("Invalid card code(s). Please provide valid card code(s).")
            return

        # Gift each card to the specified user
        for card_code in card_list:
            add_to_inventory(str(user.id), card_code)

        # Send a confirmation message
        await ctx.send(content=f"You gifted the following cards to {user.display_name}: {', '.join(card_list)}")
    else:
        await ctx.send("You do not have permission to use this command.")







@interactions.slash_command(
    name="pay",
    description="Pay another user with Dallas",
    options=[
        {
            "name": "user",
            "description": "The user to pay",
            "type": OptionType.USER,
            "required": True,
        },
        {
            "name": "amount",
            "description": "The amount of Dallas to pay",
            "type": OptionType.INTEGER,
            "required": True,
        },
    ],
)
async def pay(ctx: SlashContext, user: interactions.User, amount: int):
    user_id = str(ctx.author.id)
    target_user_id = str(user.id)

    balance = get_user_balance(user_id)

    if amount <= 0:
        embed = interactions.Embed(color=0xFF0000)  
        embed.title = "Error"
        embed.description = "That's not a valid value for the amount."
        await ctx.send(embed=embed)
        return

    if balance >= amount:
        add_to_balance(user_id, -amount)

        add_to_balance(target_user_id, amount)

        embed = interactions.Embed()
        embed.title = "Payment Successful"
        embed.description = f"{ctx.author.display_name} has paid {user.display_name} {amount} Dallas!"
        await ctx.send(embed=embed)
    else:
        await ctx.send("Insufficient balance for payment.")

@slash_command(
    name="changeurl",
    description="Change the image URL of a card (admin only)",
    options=[
        {
            "name": "card_code",
            "description": "The card code in the format of rarity_group_member",
            "type": OptionType.STRING,
            "required": True,
        },
        {
            "name": "new_url",
            "description": "The new image URL for the card",
            "type": OptionType.STRING,
            "required": True,
        },
    ],
)
async def change_url(ctx: SlashContext, card_code: str, new_url: str):
    if str(ctx.author.id) in allowed_user_ids:
        card_details = get_card_details(card_code)

        if card_details:
            rarity, group, member, _ = card_details

            c.execute("UPDATE cards SET image_url = ? WHERE rarity = ? AND group_name = ? AND member_name = ?", (new_url, rarity, group, member))
            conn.commit()

            await ctx.send(f"Image URL for card {card_code.upper()} updated.")
        else:
            await ctx.send(f"Card {card_code.upper()} not found in the database.")
    else:
        await ctx.send("You are not authorized to use this command.")

@slash_command(
    name="clear_database",
    description="Clear the entire database (Admin only)",
)
async def clear_database(ctx: SlashContext):
    if str(ctx.author.id) == "868784129372725279":
        c.execute("DELETE FROM cards")
        c.execute("DELETE FROM inventories")
        c.execute("DELETE FROM balances")
        c.execute("DELETE FROM marketplace")
        conn.commit()

        embed = interactions.Embed()
        embed.title = "Database Cleared"
        embed.description = "All data in the database has been cleared."
        await ctx.send(embed=embed)
    else:
        await ctx.send("You do not have permission to use this command.")

@slash_command(
    name="daily",
    description="Claim your daily Dallas reward",
)
async def daily(ctx: SlashContext):
    user_id = str(ctx.author.id)

    on_cooldown, remaining_time = is_daily_cooldown(user_id)
    if on_cooldown:
        remaining_time_str = str(remaining_time).split(".")[0]  # Convert timedelta to string and remove microseconds
        embed = interactions.Embed()
        embed.title = "Daily Command - Cooldown"
        embed.description = f"Sorry, you need to wait {remaining_time_str} before claiming your daily reward."
        await ctx.send(embed=embed)
    else:
        earnings = random.randint(500, 1000)
        add_to_balance(user_id, earnings)
        DAILY_COOLDOWN[user_id] = datetime.now()

        embed = interactions.Embed()
        embed.title = "Daily Command"
        embed.description = f"You claimed your daily reward and earned {earnings} Dallas!"
        await ctx.send(embed=embed)

@slash_command(
    name="exchange",
    description="Exchange a card for money",
    options=[
        {
            "name": "card_code",
            "description": "Card code to exchange",
            "type": OptionType.STRING,
            "required": True,
        },
    ],
)
async def exchange(ctx: SlashContext, card_code: str):
    user_id = str(ctx.author.id)

    # Check if the user has the specified card in their inventory
    c.execute("SELECT quantity FROM inventories WHERE user_id = ? AND card_code = ?", (user_id, card_code))
    quantity = c.fetchone()

    if quantity is None or quantity[0] <= 0:
        await ctx.send(content="You don't have the specified card in your inventory.")
        return

    # Determine the rarity of the card to calculate money gained
    c.execute("SELECT rarity FROM cards WHERE UPPER(card_code) = UPPER(?) COLLATE NOCASE", (card_code,))
    rarity = c.fetchone()

    if rarity is None:
        await ctx.send(content="Invalid card code.")
        return

    rarity = rarity[0].upper()
    money_gained = 0

    if rarity == "COMMON":
        money_gained = 40
    elif rarity == "UNCOMMON":
        money_gained = 100
    elif rarity == "RARE":
        money_gained = 150
    elif rarity == "EPIC":
        money_gained = 200
    elif rarity == "EVENT":
        money_gained = 500

    # Update user balance
    add_to_balance(user_id, money_gained)

    # Remove the exchanged card from the inventory
    c.execute("UPDATE inventories SET quantity = quantity - 1 WHERE user_id = ? AND card_code = ?", (user_id, card_code))
    conn.commit()

    await ctx.send(content=f"You exchanged {card_code.upper()} for {money_gained} Dallas!")


@slash_command(
    name="bal",
    description="Check your Dallas balance",
)
async def bal(ctx: SlashContext):
    user_id = str(ctx.author.id)
    balance = get_user_balance(user_id)

    embed = interactions.Embed()
    embed.title = "Balance Command"
    embed.description = f"Your Dallas balance: {balance} Dallas"
    await ctx.send(embed=embed)

def get_card_details(card_code):
    try:
        rarity, group, member = card_code.split('.')  
        rarity = rarity.upper()
        group = group.upper()
        member = member.upper()

        c.execute("SELECT rarity, group_name, member_name, image_url FROM cards WHERE rarity = ? AND group_name = ? AND member_name = ?", (rarity, group, member))
        return c.fetchone()
    except ValueError:
        return None


@slash_command(
    name="inv",
    description="Check your inventory",
    options=[
        {
            "name": "user",
            "description": "User whose inventory to check",
            "type": interactions.OptionType.USER,
            "required": False,
        },
        {
            "name": "group",
            "description": "Filter by group",
            "type": interactions.OptionType.STRING,
            "required": False,
        },
        {
            "name": "member",
            "description": "Filter by member",
            "type": interactions.OptionType.STRING,
            "required": False,
        },
        {
            "name": "rarity",
            "description": "Filter by rarity",
            "type": interactions.OptionType.STRING,
            "required": False,
        },
    ],
)
async def inv(ctx: interactions.ContextMenu, user: interactions.User = None, group: str = None, member: str = None, rarity: str = None):
    if user:
        user_id = str(user.id)
    else:
        user_id = str(ctx.author.id)

    query = "SELECT inventories.card_code, quantity FROM inventories WHERE inventories.user_id = ? AND inventories.quantity > 0"

    params = [user_id]

    if group:
        query += " AND EXISTS (SELECT 1 FROM cards WHERE UPPER(cards.card_code) = UPPER(inventories.card_code) AND UPPER(cards.group_name) = UPPER(?) COLLATE NOCASE)"
        params.append(group)
    
    if member:
        query += " AND EXISTS (SELECT 1 FROM cards WHERE UPPER(cards.card_code) = UPPER(inventories.card_code) AND UPPER(cards.member_name) = UPPER(?) COLLATE NOCASE)"
        params.append(member)

    if rarity:
        query += " AND EXISTS (SELECT 1 FROM cards WHERE UPPER(cards.card_code) = UPPER(inventories.card_code) AND UPPER(cards.rarity) = UPPER(?) COLLATE NOCASE)"
        params.append(rarity)

    c.execute(query, params)
    cards = c.fetchall()

    if cards:
        items_per_page = 5  # adjust this value as needed

        # Create a list of pages
        pages = []
        for i in range(0, len(cards), items_per_page):
            paginated_cards = cards[i:i + items_per_page]
            embed = interactions.Embed(title="Inventory")

            for card_code, quantity in paginated_cards:
                if card_code is not None:
                    embed.add_field(name=card_code.upper(), value=f"Quantity: {quantity}", inline=False)

            pages.append(embed)

        if not pages:
            await ctx.send(content="Your inventory is empty!")
            return

        paginator = Paginator(
            client=ctx.bot,
            pages=pages,
            show_back_button=True,
            show_next_button=True,
            show_first_button=True,
            show_last_button=True,
        )

        await paginator.send(ctx, start_page=0)

    else:
        await ctx.send(content="Your inventory is empty!")

def is_card_in_inventory(user_id, card_code):
    c.execute("SELECT COUNT(*) FROM inventories WHERE user_id = ? AND card_code = ? AND quantity > 0", (user_id, card_code))
    result = c.fetchone()
    return result[0] > 0 if result else False

def remove_from_inventory(user_id, card_code):
    c.execute("SELECT quantity FROM inventories WHERE user_id = ? AND card_code = ?", (user_id, card_code))
    existing_quantity = c.fetchone()

    if existing_quantity and existing_quantity[0] > 0:
        c.execute("UPDATE inventories SET quantity = quantity - 1 WHERE user_id = ? AND card_code = ?", (user_id, card_code))
        conn.commit()
    else:
        # Handle the case where the card is not in the user's inventory
        raise ValueError(f"The card ({card_code}) is not in the user's inventory.")
    
def get_higher_rarity(current_rarity):
    rarities_order = ["COMMON", "UNCOMMON", "RARE", "EPIC"]
    current_index = rarities_order.index(current_rarity)
    if current_index < len(rarities_order) - 1:
        return rarities_order[current_index + 1]
    else:
        return current_rarity
    
def get_group_upgrade_card(rarity, group):
    # Function to get a random card of the specified rarity and group for group upgrade

    c.execute(
        "SELECT card_code FROM cards WHERE rarity = ? AND group_name = ? AND droppable = 1 ORDER BY RANDOM() LIMIT 1",
        (rarity, group),
    )
    card = c.fetchone()
    return card[0] if card else None
    
def get_random_card(rarity, group):
    c.execute("SELECT member_name FROM cards WHERE rarity = ? AND group_name = ? ORDER BY RANDOM() LIMIT 1", (rarity, group))
    result = c.fetchone()
    if result:
        member_name = result[0]
        return f"{rarity.upper()}.{group.upper()}.{member_name.upper()}"
    return None

def get_random_card_by_rarity(rarity):
    c.execute("SELECT card_code FROM cards WHERE UPPER(rarity) = UPPER(?) ORDER BY RANDOM() LIMIT 1", (rarity,))
    result = c.fetchone()
    return result[0] if result else None

@slash_command(
    name="randomupgrade",
    description="Upgrade cards to a random higher rarity",
    options=[
        {
            "name": "cards",
            "description": "List of 5 cards to upgrade, separated by commas",
            "type": OptionType.STRING,
            "required": True,
        },
    ],
)
async def random_upgrade(ctx: SlashContext, cards: str):
    user_id = str(ctx.author.id)

    # Split the input into a list of card codes
    card_codes = [card.strip().upper() for card in cards.split(",")]

    # Check if the user has the required number of cards in the inventory
    if len(card_codes) != 5 or not all(is_card_in_inventory(user_id, card) for card in card_codes):
        await ctx.send("Not enough cards or invalid cards have been provided for the upgrade.")
        return

    # Determine the current rarity
    first_card_details = get_card_details(card_codes[0])
    if not first_card_details:
        await ctx.send("Invalid card details.")
        return

    current_rarity = first_card_details[0]

    # Determine the higher rarity
    higher_rarity = get_higher_rarity(current_rarity)
    if not higher_rarity:
        await ctx.send("No higher rarity exists.")
        return

    # Choose a random card with the higher rarity
    higher_rarity_card = get_random_card_by_rarity(higher_rarity)
    if not higher_rarity_card:
        await ctx.send(f"No cards found in the higher rarity ({higher_rarity}). Your cards have not been upgraded.")
        return

    # Update user's inventory
    for card_code in card_codes:
        remove_from_inventory(user_id, card_code)

    # Fetch card details for the embed
    higher_rarity_card_details = get_card_details(higher_rarity_card)

    if not higher_rarity_card_details:
        await ctx.send(f"No cards found in the higher rarity ({higher_rarity}). Your cards have not been upgraded.")
        return

    _, _, _, image_url, creator, _ = higher_rarity_card_details

    # Add the upgraded card to the user's inventory
    add_to_inventory(user_id, higher_rarity_card)

    # Display an embed with the upgrade result
    embed = interactions.Embed(title="Upgrade Result", color=0x00ff00)
    embed.set_image(url=image_url)
    embed.add_field(name="Upgraded Cards", value=", ".join(card_codes), inline=False)
    embed.add_field(name="Upgraded To", value=f"{higher_rarity_card}", inline=False)
    embed.add_field(name="Card Creator", value=f"Created by <@{creator}>", inline=False)

    await ctx.send(content=f"Congratulations! You have successfully upgraded your cards to a {higher_rarity_card}!", embed=embed)


@slash_command(
    name="groupupgrade",
    description="Upgrade cards within the same group",
    options=[
        {
            "name": "cards",
            "description": "List of cards to upgrade (comma-separated)",
            "type": OptionType.STRING,
            "required": True,
        },
    ],
)
async def groupupgrade(ctx: SlashContext, cards: str):
    user_id = str(ctx.author.id)

    # Split the input string into a list of cards
    card_list = [card.strip().upper() for card in cards.split(',')]

    # Check if at least 2 cards are provided
    if len(card_list) < 5:
        await ctx.send(content="Not enough cards have been put in. Your cards have not been upgraded.")
        return

    # Check if all cards have the same rarity and group
    rarity, group, _ = card_list[0].split('.')
    for card_code in card_list[1:]:
        card_rarity, card_group, _ = card_code.split('.')
        if card_rarity != rarity or card_group != group:
            await ctx.send(content="All cards must have the same rarity and group for the upgrade. Your cards have not been upgraded.")
            return

    # Check if the cards are in the user's inventory
    for card_code in card_list:
        if not is_card_in_inventory(user_id, card_code):
            await ctx.send(content=f"You don't have the specified card ({card_code}) in your inventory. Your cards have not been upgraded.")
            return

    # Perform the upgrade logic
    upgraded_rarity = get_higher_rarity(rarity)
    upgraded_card = get_group_upgrade_card(upgraded_rarity, group)

    # Remove the input cards from the user's inventory
    for card_code in card_list:
        remove_from_inventory(user_id, card_code)

    if upgraded_card:
        # Fetch card details for the embed
        upgraded_card_details = get_card_details(upgraded_card)

        if upgraded_card_details and len(upgraded_card_details) == 4:
            rarity, group, member, image_url = upgraded_card_details

            # Display an embed with the upgrade result
            embed = interactions.Embed(title="Upgrade Result", color=0x00ff00)
            embed.set_image(url=image_url)
            embed.add_field(name="Upgraded Cards", value=", ".join(card_list), inline=False)
            embed.add_field(name="Upgraded To", value=f"{upgraded_card}", inline=False)
            embed.add_field(name="Rarity", value=rarity, inline=True)
            embed.add_field(name="Group", value=group, inline=True)
            embed.add_field(name="Member", value=member, inline=True)

            await ctx.send(content=f"Congratulations! You have successfully upgraded your cards to a {upgraded_card}!", embed=embed)
        else:
            await ctx.send(f"Error fetching details for the upgraded card ({upgraded_card}). Your cards have not been upgraded.")
    else:
        await ctx.send(f"No cards found in the higher rarity ({upgraded_rarity}). Your cards have not been upgraded.")




@slash_command(
    name="duplicates",
    description="Check duplicate cards in your inventory",
    options=[
        {
            "name": "user",
            "description": "User whose inventory to check",
            "type": interactions.OptionType.USER,
            "required": False,
        },
        {
            "name": "group",
            "description": "Filter by group",
            "type": interactions.OptionType.STRING,
            "required": False,
        },
        {
            "name": "member",
            "description": "Filter by member",
            "type": interactions.OptionType.STRING,
            "required": False,
        },
        {
            "name": "rarity",
            "description": "Filter by rarity",
            "type": interactions.OptionType.STRING,
            "required": False,
        },
    ],
)
async def dupes(ctx: interactions.ContextMenu, user: interactions.User = None, group: str = None, member: str = None, rarity: str = None):
    if user:
        user_id = str(user.id)
    else:
        user_id = str(ctx.author.id)

    query = """
        SELECT card_code, quantity
        FROM inventories
        WHERE user_id = ? AND quantity > 1
    """

    params = [user_id]

    if group:
        query += """
            AND EXISTS (
                SELECT 1
                FROM cards
                WHERE UPPER(cards.card_code) = UPPER(inventories.card_code)
                    AND UPPER(cards.group_name) = UPPER(?)
                    COLLATE NOCASE
            )
        """
        params.append(group)
    
    if member:
        query += """
            AND EXISTS (
                SELECT 1
                FROM cards
                WHERE UPPER(cards.card_code) = UPPER(inventories.card_code)
                    AND UPPER(cards.member_name) = UPPER(?)
                    COLLATE NOCASE
            )
        """
        params.append(member)

    if rarity:
        query += """
            AND EXISTS (
                SELECT 1
                FROM cards
                WHERE UPPER(cards.card_code) = UPPER(inventories.card_code)
                    AND UPPER(cards.rarity) = UPPER(?)
                    COLLATE NOCASE
            )
        """
        params.append(rarity)

    c.execute(query, params)
    dupes = c.fetchall()

    if dupes:
        items_per_page = 5  # adjust this value as needed

        # Create a list of pages
        pages = []
        for i in range(0, len(dupes), items_per_page):
            paginated_dupes = dupes[i:i + items_per_page]
            embed = interactions.Embed(title="Duplicate Cards in Inventory")

            for card_code, quantity in paginated_dupes:
                embed.add_field(name=card_code.upper(), value=f"Quantity: {quantity}", inline=False)

            pages.append(embed)

        if not pages:
            await ctx.send(content="No duplicate cards found in your inventory!")
            return

        paginator = Paginator(
            client=ctx.bot,
            pages=pages,
            show_back_button=True,
            show_next_button=True,
            show_first_button=True,
            show_last_button=True,
        )

        await paginator.send(ctx, start_page=0)

    else:
        await ctx.send(content="No duplicate cards found in your inventory!")

def get_filtered_duplicates(user_id, group, member, rarity):
    query = "SELECT card_code, quantity FROM inventories WHERE user_id = ? AND quantity > 1"

    params = [user_id]

    if group:
        query += " AND EXISTS (SELECT 1 FROM cards WHERE UPPER(cards.card_code) = UPPER(inventories.card_code) AND UPPER(cards.group_name) = UPPER(?) COLLATE NOCASE)"
        params.append(group)

    if member:
        query += " AND EXISTS (SELECT 1 FROM cards WHERE UPPER(cards.card_code) = UPPER(inventories.card_code) AND UPPER(cards.member_name) = UPPER(?) COLLATE NOCASE)"
        params.append(member)

    if rarity:
        query += " AND EXISTS (SELECT 1 FROM cards WHERE UPPER(cards.card_code) = UPPER(inventories.card_code) AND UPPER(cards.rarity) = UPPER(?) COLLATE NOCASE)"
        params.append(rarity)

    c.execute(query, params)
    return c.fetchall()

def create_dupes_embed(ctx, user_id, duplicates, current_page, total_pages):
    embed = interactions.Embed(title=f"{ctx.author.display_name}'s Duplicates (Page {current_page}/{total_pages})")

    for card_code, quantity in duplicates:
        rarity, group, member, image_url = get_card_details(card_code)
        embed.add_field(
            name=f"{card_code} (Quantity: {quantity})",
            value=f"Rarity: {rarity}\nGroup: {group}\nMember: {member}",
            inline=False,
        )

    return embed

@slash_command(
    name="pool",
    description="Displays all cards in the pool",
    options=[
        {
            "name": "page",
            "description": "Page number of the pool",
            "type": OptionType.INTEGER,
            "required": False,
        },
        {
            "name": "group",
            "description": "Filter by group",
            "type": OptionType.STRING,
            "required": False,
        },
        {
            "name": "member",
            "description": "Filter by member",
            "type": OptionType.STRING,
            "required": False,
        },
        {
            "name": "rarity",
            "description": "Filter by rarity",
            "type": OptionType.STRING,
            "required": False,
        },
    ],
)
async def pool(ctx: SlashContext, page: int = 1, group: str = None, member: str = None, rarity: str = None):
    query = "SELECT rarity, group_name, member_name FROM cards WHERE 1"
    params = []

    if group:
        query += " AND LOWER(group_name) = ?"
        params.append(group.lower())

    if member:
        query += " AND LOWER(member_name) = ?"
        params.append(member.lower())

    if rarity:
        query += " AND LOWER(rarity) = ?"
        params.append(rarity.lower())

    try:
        c.execute(query, params)
        cards = c.fetchall()
    except Exception as e:
        print("Error executing SQL query:", e)
        await ctx.send(content="An error occurred while fetching the card pool.")
        return

    if cards:
        pool_entries = []

        # Get user's inventory
        user_id = str(ctx.author.id)
        user_inventory_query = "SELECT card_code FROM inventories WHERE user_id = ?"
        c.execute(user_inventory_query, [user_id])
        user_inventory = {row[0].upper() for row in c.fetchall() if row[0] is not None}  # Check for None before applying upper

        for rarity, group, member in cards:
            card_code = f"{rarity}.{group}.{member}".upper() if rarity and group and member else None  # Check for None values before applying upper
            if card_code:
                check_mark = "✅" if card_code in user_inventory else "❌"
                pool_entries.append(f"{check_mark} {card_code}")

        pages = [Page(content="\n".join(pool_entries[i:i + ITEMS_PER_PAGE])) for i in range(0, len(pool_entries), ITEMS_PER_PAGE)]
        page_count = len(pages)

        if page < 1 or page > page_count:
            await ctx.send(content="Invalid page number!")
            return

        current_page = page - 1  
        page_items = pages[current_page]
        footer_text = f"Page {page}/{page_count}"

        paginator = Paginator(
            client=bot,
            pages=pages,
            timeout_interval=60,  
            show_back_button=True,
            show_next_button=True,
            show_first_button=True,
            show_last_button=True,
        )

        await paginator.send(ctx, start_page=current_page)

    else:
        await ctx.send(content="The card pool is empty!")



@slash_command(
    name="market",
    description="View cards in the marketplace",
    options=[
        {
            "name": "page",
            "description": "Page number of the marketplace",
            "type": OptionType.INTEGER,
            "required": False,
        },
        {
            "name": "group",
            "description": "Filter by group",
            "type": OptionType.STRING,
            "required": False,
        },
        {
            "name": "member",
            "description": "Filter by member",
            "type": OptionType.STRING,
            "required": False,
        },
        {
            "name": "rarity",
            "description": "Filter by rarity",
            "type": OptionType.STRING,
            "required": False,
        },
        {
            "name": "mine",  # New option for "Mine"
            "description": "Show only your own listings",
            "type": OptionType.BOOLEAN,
            "required": False,
        },
    ],
)
async def market(ctx: SlashContext, page: int = 1, group: str = None, member: str = None, rarity: str = None, mine: bool = False):
    query = "SELECT unique_code, card_code, seller_id, price FROM marketplace WHERE 1"
    params = []

    if group:
        query += " AND EXISTS (SELECT 1 FROM cards WHERE LOWER(group_name) = ? AND card_code = marketplace.card_code)"
        params.append(group.lower())

    if member:
        query += " AND EXISTS (SELECT 1 FROM cards WHERE LOWER(member_name) = ? AND card_code = marketplace.card_code)"
        params.append(member.lower())

    if rarity:
        query += " AND EXISTS (SELECT 1 FROM cards WHERE LOWER(rarity) = ? AND card_code = marketplace.card_code)"
        params.append(rarity.lower())

    if mine:
        query += " AND seller_id = ?"
        params.append(str(ctx.author.id))

    try:
        c.execute(query, params)
        listings = c.fetchall()
    except Exception as e:
        print("Error executing SQL query:", e)
        await ctx.send(content="An error occurred while fetching the marketplace listings.")
        return

    if listings:
        marketplace_entries = []

        for unique_code, card_code, seller_id, price in listings:
            card_details = get_card_details(card_code)
            if card_details:
                rarity, group, member, _ = card_details

                seller = await bot.fetch_user(int(seller_id))
                seller_name = seller.username if seller else f"Unknown User ({seller_id})"

                entry = (
                    f"**Listing Code:** `{unique_code}`\n"
                    f"**Card:** {card_code.upper()} ({rarity}/{group}/{member})\n"
                    f"**Seller:** {seller_name}\n"
                    f"**Price:** {price} Dallas\n"
                    f"------------------------------"
                )
                marketplace_entries.append(entry)

        pages = [marketplace_entries[i:i + ITEMS_PER_PAGE] for i in range(0, len(marketplace_entries), ITEMS_PER_PAGE)]
        page_count = len(pages)

        if page < 1 or page > page_count:
            await ctx.send(content="Invalid page number!")
            return

        current_page = page - 1  
        page_items = pages[current_page]
        footer_text = f"Page {page}/{page_count}"

        paginator = Paginator(
            client=bot,
            pages=[Page(content="\n".join(page)) for page in pages],
            timeout_interval=60,  
            show_back_button=True,
            show_next_button=True,
            show_first_button=True,
            show_last_button=True,
        )

        await paginator.send(ctx, start_pag=current_page)

    else:
        await ctx.send(content="There are currently no listings in the marketplace.")

@slash_command(
    name="opmarketremove",
    description="Remove any card from the marketplace (Admin only)",
    options=[
        {
            "name": "unique_code",
            "description": "Unique code of the listing to remove",
            "type": OptionType.STRING,
            "required": True,
        },
    ],
)
async def op_market_remove(ctx: SlashContext, unique_code: str):
    # Check if the user has the "Admin" role
    admin_role_id = 1127549099638530098  # Replace with the actual ID of the Admin role
    user_has_admin_role = any(role.id == admin_role_id for role in ctx.author.roles)

    if user_has_admin_role:
        # Admin is authorized to remove any listing
        c.execute("DELETE FROM marketplace WHERE unique_code = ?", (unique_code,))
        conn.commit()
        await ctx.send(content=f"The listing with unique code `{unique_code}` has been removed from the marketplace.")
    else:
        await ctx.send(content="You do not have the necessary permissions to use this command.")


@slash_command(
    name="marketremove",
    description="Remove your own card from the marketplace",
    options=[
        {
            "name": "unique_code",
            "description": "Unique code of the listing to remove",
            "type": OptionType.STRING,
            "required": True,
        },
    ],
)
async def market_remove(ctx: SlashContext, unique_code: str):
    user_id = str(ctx.author.id)

    # Check if the user has a listing with the specified unique code
    c.execute("SELECT card_code FROM marketplace WHERE seller_id = ? AND unique_code = ?", (user_id, unique_code))
    result = c.fetchone()

    if result:
        card_code = result[0]

        # User is authorized to remove their own listing
        c.execute("DELETE FROM marketplace WHERE seller_id = ? AND unique_code = ?", (user_id, unique_code))
        conn.commit()

        # Add the card back to the user's inventory
        add_to_inventory(user_id, card_code)

        await ctx.send(content=f"Your listing for card `{card_code.upper()}` with unique code `{unique_code}` has been removed from the marketplace and added back to your inventory.")
    else:
        await ctx.send(content="You do not have a listing for the specified unique code.")






@slash_command(
    name="sell",
    description="Put a card on the marketplace",
    options=[
        {
            "name": "card_code",
            "description": "The card code to sell",
            "type": OptionType.STRING,
            "required": True,
        },
        {
            "name": "price",
            "description": "The price to sell the card for",
            "type": OptionType.INTEGER,
            "required": True,
        },
    ],
)
async def sell(ctx: SlashContext, card_code: str, price: int):
    user_id = str(ctx.author.id)

    c.execute("SELECT quantity FROM inventories WHERE user_id = ? AND card_code = ?", (user_id, card_code))
    existing_quantity = c.fetchone()

    if existing_quantity and existing_quantity[0] > 0:
        c.execute("UPDATE inventories SET quantity = quantity - 1 WHERE user_id = ? AND card_code = ?", (user_id, card_code))
        conn.commit()

        unique_code = generate_unique_code()

        c.execute("INSERT INTO marketplace (unique_code, card_code, seller_id, price) VALUES (?, ?, ?, ?)", (unique_code, card_code, user_id, price))
        conn.commit()

        await ctx.send(f"You have put a {card_code} card on the marketplace for {price} Dallas! (Listing Code: {unique_code})")
    else:
        await ctx.send(f"You don't have the specified card ({card_code}) in your inventory!")

def generate_unique_code():
    characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    unique_code = ''.join(secrets.choice(characters) for _ in range(8))
    return unique_code

@slash_command(
    name="buy",
    description="Buy a card from the marketplace",
    options=[
        {
            "name": "listing_code",
            "description": "The unique code of the listing you want to buy",
            "type": OptionType.STRING,
            "required": True,
        },
    ],
)
async def buy(ctx: SlashContext, listing_code: str):
    buyer_id = str(ctx.author.id)

    c.execute("SELECT card_code, seller_id, price FROM marketplace WHERE unique_code = ?", (listing_code,))
    listing = c.fetchone()

    if listing:
        card_code, seller_id, price = listing

        buyer_balance = get_user_balance(buyer_id)
        if buyer_balance >= price:
            seller_balance = get_user_balance(seller_id)

            # Transfer money from buyer to seller
            add_to_balance(seller_id, price)
            add_to_balance(buyer_id, -price)

            # Add the purchased card to the buyer's inventory
            add_to_inventory(buyer_id, card_code)

            # Remove the listing from the marketplace
            c.execute("DELETE FROM marketplace WHERE unique_code = ?", (listing_code,))
            conn.commit()

            # Notify the buyer and seller about the successful transaction
            buyer_embed = interactions.Embed()
            buyer_embed.title = "Marketplace - Purchase Successful"
            buyer_embed.description = f"You have successfully purchased the card {card_code.upper()} for {price} Dallas!"
            await ctx.send(embed=buyer_embed, ephemeral=True)

            seller_embed = interactions.Embed()
            seller_embed.title = "Marketplace - Item Sold"
            seller_embed.description = f"Your listing for the card {card_code.upper()} has been sold to {ctx.author.display_name} for {price} Dallas!"
            await bot.get_user(int(seller_id)).send(embed=seller_embed)

        else:
            await ctx.send(content="You don't have enough Dallas to make this purchase!", ephemeral=True)
    else:
        await ctx.send(content=f"No listing found with the code {listing_code} in the marketplace.", ephemeral=True)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, interactions.errors.CommandError):
        await ctx.send("An error occurred while processing your command. Please check your input and try again.")
        print(f"Error in command {ctx.command} for user {ctx.author.id}: {error}")

@bot.event
async def on_shutdown():
    conn.close()

@bot.event
async def on_ready():
    await bot.register_command(add_card)
    await bot.register_command(drop)
    await bot.register_command(gift)
    await bot.register_command(inv)
    await bot.register_command(pool)
    await bot.register_command(clear_database)
    await bot.register_command(change_url)
    await bot.register_command(work)  
    await bot.register_command(daily)  
    await bot.register_command(bal)  
    await bot.register_command(market)
    await bot.register_command(oppay)
    await bot.register_command(opgift)
    await bot.register_command(pay)
    await bot.register_command(view_card)
    await bot.register_command(market_remove)
    await bot.register_command(op_market_remove)
    await bot.register_command(exchange)
    await bot.register_command(bulkgift)


    print("Bot is ready!")

bot.start()
