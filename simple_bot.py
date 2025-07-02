import telebot
from telebot import types
import os
import sqlite3
import uuid
from datetime import datetime
import re
import time

# --- CONFIGURATION ---
TOKEN = '8108658761:AAE_2O5d8zstSITUiMoN9jBK2oyGRRg7QX8' # Replace with your bot's token
ADMIN_IDS = [
    7481885595,  # @packoa's ID
    7864373277,  # @xenslol's ID
]
PAYPAL_USERNAME = "CaitlinGetrajdman367" # Your PayPal.me username

# --- INITIALIZATION ---
bot = telebot.TeleBot(TOKEN)
DEBUG = True
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

user_states = {}

# --- HELPER FUNCTIONS ---
def debug_print(message):
    if DEBUG: print(f"DEBUG: {message}")

def format_price(price):
    return f"${price:.2f}"

def escape_markdown(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def save_individual_product_file(content):
    secure_filename = f"{uuid.uuid4()}.txt"
    file_path = os.path.join(UPLOAD_FOLDER, secure_filename)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return file_path, None
    except Exception as e:
        return None, str(e)


# --- DATABASE FUNCTIONS ---
def init_database():
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT, price REAL NOT NULL, file_path TEXT NOT NULL, file_name TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, active INTEGER DEFAULT 1)')
    cursor.execute('CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, username TEXT, product_id INTEGER NOT NULL, payment_method TEXT NOT NULL, payment_status TEXT DEFAULT \'pending\', payment_id TEXT, amount REAL NOT NULL, purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, access_token TEXT, FOREIGN KEY (product_id) REFERENCES products (id))')
    # ADDED 'role' COLUMN TO USERS TABLE
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0, role TEXT DEFAULT "user")')
    conn.commit()
    conn.close()

def get_or_create_user(user_id, username=None):
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    # When creating a user, they get the 'user' role by default
    cursor.execute("INSERT OR IGNORE INTO users (user_id, balance, role) VALUES (?, 0.0, 'user')", (user_id,))
    if username:
        cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.commit()
    conn.close()
    return user

def set_user_role(user_id, role):
    """Sets the role for a given user."""
    get_or_create_user(user_id) # Ensure user exists
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
    conn.commit()
    conn.close()

def get_user_role(user_id):
    """Gets a user's role."""
    user = get_or_create_user(user_id)
    # user[3] is the role column
    return user[3] if user else 'user'

# (Other database functions remain the same)
def get_all_users():
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, balance, role FROM users ORDER BY balance DESC")
    users = cursor.fetchall()
    conn.close()
    return users

def get_user_by_username(username):
    clean_username = username.lstrip('@')
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE username = ?", (clean_username,))
    user = cursor.fetchone()
    conn.close()
    return user[0] if user else None

def update_user_balance(user_id, amount_change):
    get_or_create_user(user_id)
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount_change, user_id))
    conn.commit()
    conn.close()

# ... (rest of DB functions are unchanged)

# --- BOT MESSAGE HANDLERS ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    get_or_create_user(message.from_user.id, message.from_user.username)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('Browse Products', 'My Purchases')
    markup.row('My Balance', 'Support')
    welcome_text = f"Welcome to Retrinity cc shop, {escape_markdown(message.from_user.first_name)}\!"
    bot.reply_to(message, welcome_text, reply_markup=markup, parse_mode="MarkdownV2")

# --- ADMIN COMMANDS ---

@bot.message_handler(commands=['addfunds'])
def add_funds_command(message):
    # Check for either Full Admin or Funds Admin
    user_role = get_user_role(message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and user_role != 'funds_admin':
        bot.reply_to(message, "You do not have permission to use this command\.", parse_mode="MarkdownV2")
        return

    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "Usage:\n/addfunds `<@username_or_id> <amount>`", parse_mode="MarkdownV2")
        return
        
    target_identifier = parts[1]
    target_user_id = None
    if target_identifier.startswith('@'):
        target_user_id = get_user_by_username(target_identifier)
        if not target_user_id:
            bot.reply_to(message, f"User `{escape_markdown(target_identifier)}` not found\. They must have started the bot at least once\.", parse_mode="MarkdownV2")
            return
    elif target_identifier.isdigit():
        target_user_id = int(target_identifier)
    else:
        bot.reply_to(message, "Invalid user identifier\. Please use a User ID or an @username\.", parse_mode="MarkdownV2")
        return
    try:
        amount = float(parts[2])
    except ValueError:
        bot.reply_to(message, "Invalid Amount\. Please use a number\.", parse_mode="MarkdownV2")
        return
        
    update_user_balance(target_user_id, amount)
    new_balance = get_user_balance(target_user_id)
    bot.reply_to(message, f"✅ Successfully added `{escape_markdown(format_price(amount))}` to user `{escape_markdown(target_identifier)}`\.\nTheir new balance is: `{escape_markdown(format_price(new_balance))}`", parse_mode="MarkdownV2")
    try:
        bot.send_message(target_user_id, f"An admin has added `{escape_markdown(format_price(amount))}` to your balance\.\nYour new balance is: `{escape_markdown(format_price(new_balance))}`", parse_mode="MarkdownV2")
    except Exception as e:
        debug_print(f"Could not notify user {target_user_id} about added funds: {e}")

@bot.message_handler(commands=['addfadmin'])
def add_funds_admin_command(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "This command is for full admins only\.")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /addfadmin `<@username_or_id>`", parse_mode="MarkdownV2")
        return

    target_identifier = parts[1]
    target_user_id = None
    if target_identifier.startswith('@'):
        target_user_id = get_user_by_username(target_identifier)
        if not target_user_id:
            bot.reply_to(message, f"User `{escape_markdown(target_identifier)}` not found\. They must have started the bot at least once\.", parse_mode="MarkdownV2")
            return
    elif target_identifier.isdigit():
        target_user_id = int(target_identifier)
    else:
        bot.reply_to(message, "Invalid user identifier\. Please use a User ID or an @username\.", parse_mode="MarkdownV2")
        return

    set_user_role(target_user_id, 'funds_admin')
    bot.reply_to(message, f"✅ User `{escape_markdown(target_identifier)}` has been promoted to Funds Admin\.", parse_mode="MarkdownV2")
    try:
        bot.send_message(target_user_id, "You have been promoted to a Funds Admin\. You can now use the `/addfunds` command\.", parse_mode="MarkdownV2")
    except Exception as e:
        debug_print(f"Could not notify user {target_user_id} about promotion: {e}")

@bot.message_handler(commands=['removefadmin'])
def remove_funds_admin_command(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "This command is for full admins only\.")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /removefadmin `<@username_or_id>`", parse_mode="MarkdownV2")
        return

    target_identifier = parts[1]
    target_user_id = None
    if target_identifier.startswith('@'):
        target_user_id = get_user_by_username(target_identifier)
        if not target_user_id:
            bot.reply_to(message, f"User `{escape_markdown(target_identifier)}` not found\.", parse_mode="MarkdownV2")
            return
    elif target_identifier.isdigit():
        target_user_id = int(target_identifier)
    else:
        bot.reply_to(message, "Invalid user identifier\.", parse_mode="MarkdownV2")
        return

    set_user_role(target_user_id, 'user')
    bot.reply_to(message, f"✅ User `{escape_markdown(target_identifier)}` has been demoted to a regular user\.", parse_mode="MarkdownV2")
    try:
        bot.send_message(target_user_id, "You have been demoted to a regular user\.", parse_mode="MarkdownV2")
    except Exception as e:
        debug_print(f"Could not notify user {target_user_id} about demotion: {e}")

@bot.message_handler(commands=['users'])
def list_users_command(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "This command is for admins only.")
        return
    users = get_all_users()
    if not users:
        bot.reply_to(message, "No users have interacted with the bot yet.")
        return
    file_content = "User ID,Username,Balance,Role\n"
    for user in users:
        user_id, username, balance, role = user
        file_content += f"{user_id},{username or 'N/A'},{balance:.2f},{role}\n"
    try:
        file_path = "user_list.csv"
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(file_content)
        with open(file_path, "rb") as file:
            bot.send_document(message.chat.id, file, caption="Here is the list of all bot users.")
        os.remove(file_path)
    except Exception as e:
        debug_print(f"Failed to send user list file: {e}")
        bot.reply_to(message, "An error occurred while generating the user list file.")

@bot.message_handler(commands=['remove'])
def remove_product_start(message):
    if message.from_user.id not in ADMIN_IDS: return
    products = get_products()
    if not products:
        bot.send_message(message.chat.id, "There are no active products to remove.")
        return
    markup = types.InlineKeyboardMarkup()
    for p in products:
        product_id, name, _, price, _, _, _, _ = p
        button_text = f"❌ {name} - {format_price(price)}"
        markup.row(types.InlineKeyboardButton(button_text, callback_data=f"remove_{product_id}"))
    markup.row(types.InlineKeyboardButton("🔙 Cancel", callback_data="cancel_action"))
    bot.send_message(message.chat.id, "Select a product to remove from the shop:", reply_markup=markup)


# This handler is the primary entry point for admins adding products
@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS: return
        
    if not message.document.file_name.lower().endswith('.txt'):
        bot.send_message(user_id, "Error: Only .txt files are accepted.")
        return
    
    bot.send_message(user_id, "This bot now uses a bulk upload format\. Please use the `/addproducts` command instead by providing the price as an argument\.\n\nExample:\n`/addproducts 10` \(this will set the price for each line in the file to $10\)", parse_mode="MarkdownV2")

@bot.message_handler(commands=['addproducts'])
def add_products_start(message):
    if message.from_user.id not in ADMIN_IDS: return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /addproducts `<price>`\nThen, upload your `\.txt` file\.", parse_mode="MarkdownV2")
        return
    
    try:
        price = float(parts[1])
        if price <= 0:
            bot.reply_to(message, "Price must be a positive number\.")
            return
        user_states[message.from_user.id] = {'state': 'admin_waiting_bulk_file', 'price': price}
        bot.reply_to(message, f"Ready to add products at a price of *{escape_markdown(format_price(price))}* each\. Now, please upload your `\.txt` file\.", parse_mode="MarkdownV2")
    except ValueError:
        bot.reply_to(message, "Invalid price format\. Please use a number\.", parse_mode="MarkdownV2")


@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    # This handler now only routes reply keyboard buttons
    if message.text == 'Browse Products':
        browse_products(message)
    elif message.text == 'My Purchases':
        my_purchases(message)
    elif message.text == 'Support':
        support(message)
    elif message.text == 'My Balance':
        show_balance_handler(message)
    else:
        bot.send_message(message.chat.id, "I don't understand that. Please use the menu buttons.")


# (The rest of the bot, especially handle_callbacks, would go here...)
# This is a large file, so focusing on the requested changes. 
# The full logic for other functions like Browse, purchasing, etc. would be included below.

if __name__ == "__main__":
    init_database()
    debug_print("Bot starting up with Roles system...")
    try:
        while True:
            try:
                bot.infinity_polling(timeout=30, long_polling_timeout=15)
            except Exception as e:
                debug_print(f"Polling failed, restarting in 5 seconds: {e}")
                time.sleep(5)
    except Exception as e:
        debug_print(f"An unexpected error occurred: {e}")
