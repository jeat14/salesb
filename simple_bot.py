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

def get_card_type(card_number):
    """Determines card type from the first digit."""
    if card_number.startswith('4'): return 'Visa'
    elif card_number.startswith('5'): return 'Mastercard'
    elif card_number.startswith('3'): return 'Amex'
    elif card_number.startswith('6'): return 'Discover'
    else: return 'Card'

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

# (Other DB functions...)
def get_all_users():
    # ...
    pass
# ...

# --- BOT MESSAGE HANDLERS ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    get_or_create_user(message.from_user.id, message.from_user.username)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('Browse Products', 'My Purchases')
    markup.row('My Balance', 'Support')
    welcome_text = f"Welcome to Retrinity cc shop, {escape_markdown(message.from_user.first_name)}\!"
    if message.from_user.id in ADMIN_IDS:
        welcome_text += "\n\n*Admin tip:* To add products, just upload a `\.txt` file\. To add funds, use `/addfunds`\."
    bot.reply_to(message, welcome_text, reply_markup=markup, parse_mode="MarkdownV2")

@bot.message_handler(commands=['addfunds'])
def add_funds_command(message):
    user_role = get_user_role(message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and user_role != 'funds_admin':
        bot.reply_to(message, "You do not have permission to use this command\.")
        return
    # (rest of addfunds logic...)

@bot.message_handler(commands=['addfadmin', 'removefadmin'])
def manage_funds_admin_command(message):
    if message.from_user.id not in ADMIN_IDS: return
    # (rest of fadmin logic...)

@bot.message_handler(commands=['users'])
def list_users_command(message):
    if message.from_user.id not in ADMIN_IDS: return
    # (rest of users logic...)

@bot.message_handler(commands=['remove'])
def remove_product_start(message):
    if message.from_user.id not in ADMIN_IDS: return
    # (rest of remove logic...)


# --- NEW, SIMPLIFIED UPLOAD FLOW ---

@bot.message_handler(content_types=['document'])
def handle_document_upload(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        # Ignore files sent by non-admins
        return
        
    if not message.document.file_name.lower().endswith('.txt'):
        bot.send_message(user_id, "Error: Only .txt files are accepted.")
        return
    
    # Save the file ID and ask for the price
    user_states[user_id] = {
        'state': 'admin_waiting_price_for_bulk_upload',
        'file_id': message.document.file_id,
        'file_name': message.document.file_name
    }
    bot.send_message(user_id, f"File `{escape_markdown(message.document.file_name)}` received\. Please reply with the price for each item in this file\.", parse_mode="MarkdownV2")

@bot.message_handler(func=lambda message: True)
def handle_all_text(message):
    user_id = message.from_user.id
    state_info = user_states.get(user_id)

    # Check if this message is a price for a pending bulk upload
    if isinstance(state_info, dict) and state_info.get('state') == 'admin_waiting_price_for_bulk_upload':
        try:
            price = float(message.text.strip())
            if price <= 0:
                bot.reply_to(message, "Price must be a positive number.")
                return
        except ValueError:
            bot.reply_to(message, "Invalid price format. Please send only a number.")
            return

        # We have the price, now process the file
        bot.send_message(user_id, "Processing your bulk file, please wait...")
        try:
            file_id = state_info['file_id']
            base_product_name = os.path.splitext(state_info['file_name'])[0]
            
            downloaded_file_info = bot.get_file(file_id)
            file_content = bot.download_file(downloaded_file_info.file_path)
            
            lines = file_content.decode('utf-8').splitlines()
            
            added_count = 0
            failed_count = 0

            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split('|')
                if len(parts) != 10:
                    failed_count += 1
                    continue

                try:
                    card_number, exp_month, exp_year, cvv, holder, address, city, state, zip_code, country = [p.strip() for p in parts]
                    
                    card_type = get_card_type(card_number)
                    product_name = f"{card_type} - {card_number[:6]} - {country}"
                    
                    product_description = f"Holder: {holder}\nAddress: {address}, {city}, {state}, {zip_code}, {country}\nExpires: {exp_month}/{exp_year}\nCVV: {cvv}"

                    file_path, error = save_individual_product_file(line)
                    if error:
                        failed_count += 1
                        continue

                    add_product_to_db(product_name, product_description, price, file_path, f"{product_name}.txt")
                    added_count += 1
                except Exception as e:
                    failed_count += 1
                    debug_print(f"Error processing line '{line}': {e}")
            
            summary_message = f"✅ *Bulk Upload Complete*\n\nSuccessfully added: `{added_count}` products\.\nFailed to process: `{failed_count}` lines\."
            bot.send_message(user_id, summary_message, parse_mode="MarkdownV2")
        
        except Exception as e:
            debug_print(f"File processing error: {str(e)}")
            bot.send_message(user_id, "An error occurred while processing the file.")
        
        finally:
            user_states.pop(user_id, None)

    # If not a special state, handle regular menu buttons
    elif message.text == 'Browse Products':
        browse_products(message)
    elif message.text == 'My Purchases':
        my_purchases(message)
    elif message.text == 'Support':
        support(message)
    elif message.text == 'My Balance':
        show_balance_handler(message)
    else:
        bot.send_message(message.chat.id, "I don't understand that. Please use the menu buttons.")

# --- BROWSE PRODUCTS HANDLER (WITH 6-DIGIT PREVIEW) ---
def browse_products(message):
    products = get_products()
    if not products:
        bot.send_message(message.chat.id, "No products available.")
        return
    markup = types.InlineKeyboardMarkup()
    for p in products:
        product_id, name, desc, price, _, _, _, _ = p
        # Use first 6 chars of the product name for the preview, as the description is long
        preview = f" ({name[:6]}...)"
        button_text = f"{name} - {format_price(price)}" # Preview removed for clarity, name is descriptive enough
        markup.row(types.InlineKeyboardButton(button_text, callback_data=f"product_{product_id}"))
    bot.send_message(message.chat.id, "Available Products:", reply_markup=markup)
    
# (Callbacks and other handlers would go here...)

if __name__ == "__main__":
    init_database()
    debug_print("Bot starting up...")
    try:
        while True:
            try:
                bot.infinity_polling(timeout=30, long_polling_timeout=15)
            except Exception as e:
                debug_print(f"Polling failed, restarting in 5 seconds: {e}")
                time.sleep(5)
    except Exception as e:
        debug_print(f"An unexpected error occurred: {e}")
