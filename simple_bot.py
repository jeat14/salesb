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
    """Helper function to escape telegram markdown V2 characters."""
    if not isinstance(text, str):
        text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def save_individual_product_file(content):
    """Saves a string content to a new unique txt file."""
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
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0, role TEXT DEFAULT "user")')
    conn.commit()
    conn.close()

def get_or_create_user(user_id, username=None):
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, balance, role) VALUES (?, 0.0, 'user')", (user_id,))
    if username:
        cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.commit()
    conn.close()
    return user
    
def get_user_role(user_id):
    user = get_or_create_user(user_id)
    return user[3] if user else 'user'

def set_user_role(user_id, role):
    get_or_create_user(user_id)
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, balance, role FROM users ORDER BY balance DESC")
    users = cursor.fetchall()
    conn.close()
    return users

# (Other database functions remain unchanged)
# ...

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
    user_role = get_user_role(message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and user_role != 'funds_admin':
        bot.reply_to(message, "You do not have permission to use this command\.")
        return
    # (rest of the addfunds logic)

@bot.message_handler(commands=['addfadmin', 'removefadmin'])
def manage_funds_admin_command(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "This command is for full admins only\.")
        return
    
    parts = message.text.split()
    command = parts[0]
    
    if len(parts) != 2:
        bot.reply_to(message, f"Usage: {command} `<@username_or_id>`", parse_mode="MarkdownV2")
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
    
    if command == '/addfadmin':
        set_user_role(target_user_id, 'funds_admin')
        bot.reply_to(message, f"✅ User `{escape_markdown(target_identifier)}` has been promoted to Funds Admin\.", parse_mode="MarkdownV2")
        try:
            bot.send_message(target_user_id, "You have been promoted to a Funds Admin\. You can now use the `/addfunds` command\.", parse_mode="MarkdownV2")
        except Exception as e:
            debug_print(f"Could not notify user {target_user_id} about promotion: {e}")
    elif command == '/removefadmin':
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
    # (rest of the users logic)

@bot.message_handler(commands=['remove'])
def remove_product_start(message):
    if message.from_user.id not in ADMIN_IDS: return
    # (rest of the remove logic)

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


# --- SMART DOCUMENT HANDLER ---
@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        # Ignore files sent by non-admins
        return
        
    if not message.document.file_name.lower().endswith('.txt'):
        bot.send_message(user_id, "Error: Only .txt files are accepted.")
        return
        
    state_info = user_states.get(user_id)
    
    # Check if we are waiting for a bulk upload file
    if isinstance(state_info, dict) and state_info.get('state') == 'admin_waiting_bulk_file':
        price = state_info.get('price')
        file_info = message.document
        
        try:
            downloaded_file_info = bot.get_file(file_info.file_id)
            file_content = bot.download_file(downloaded_file_info.file_path)
            
            lines = file_content.decode('utf-8').splitlines()
            base_product_name = os.path.splitext(file_info.file_name)[0]
            
            added_count = 0
            failed_count = 0

            for i, line in enumerate(lines):
                description = line.strip()
                if not description:
                    continue
                
                try:
                    product_name = f"{base_product_name}-{i+1}"
                    file_path, error = save_individual_product_file(description)
                    if error:
                        failed_count += 1
                        continue
                    # In a real bulk upload, each line might have its own price
                    # For now, we use the price set in the command
                    add_product_to_db(product_name, description, price, file_path, os.path.basename(file_path))
                    added_count += 1
                except Exception as e:
                    failed_count += 1
                    debug_print(f"Error adding line {i+1}: {e}")
            
            summary_message = f"✅ *Bulk Upload Complete*\n\nSuccessfully added: `{added_count}` products\.\nFailed to process: `{failed_count}` lines\."
            bot.send_message(user_id, summary_message, parse_mode="MarkdownV2")
        
        except Exception as e:
            debug_print(f"File processing error: {str(e)}")
            bot.send_message(user_id, "An error occurred while processing the file.")
        
        finally:
            # Clear the state
            user_states.pop(user_id, None)
    else:
        # If the state is not set, instruct the admin on how to use the command
        bot.send_message(user_id, "To upload products, please first set a price using the command:\n`/addproducts <price>`", parse_mode="MarkdownV2")


# --- REGULAR USER MESSAGE HANDLERS ---
@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
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

# (All other functions like browse_products, my_purchases, handle_callbacks, etc. go here)
# ...

if __name__ == "__main__":
    init_database()
    debug_print("Bot starting up with simplified admin workflow...")
    try:
        while True:
            try:
                bot.infinity_polling(timeout=30, long_polling_timeout=15)
            except Exception as e:
                debug_print(f"Polling failed, restarting in 5 seconds: {e}")
                time.sleep(5)
    except Exception as e:
        debug_print(f"An unexpected error occurred: {e}")
