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
    if card_number.startswith('4'):
        return 'Visa'
    elif card_number.startswith('5'):
        return 'Mastercard'
    elif card_number.startswith('3'):
        return 'Amex'
    elif card_number.startswith('6'):
        return 'Discover'
    else:
        return 'Card'


# --- DATABASE FUNCTIONS ---
def init_database():
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT, price REAL NOT NULL, file_path TEXT NOT NULL, file_name TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, active INTEGER DEFAULT 1)')
    cursor.execute('CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, username TEXT, product_id INTEGER NOT NULL, payment_method TEXT NOT NULL, payment_status TEXT DEFAULT \'pending\', payment_id TEXT, amount REAL NOT NULL, purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, access_token TEXT, FOREIGN KEY (product_id) REFERENCES products (id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0, role TEXT DEFAULT "user")')
    conn.commit()
    conn.close()

# (All other database functions like get_or_create_user, get_products, etc. remain the same)
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

# --- UPDATED DOCUMENT HANDLER WITH ADVANCED PARSING ---
@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
        
    if not message.document.file_name.lower().endswith('.txt'):
        bot.send_message(user_id, "Error: Only .txt files are accepted.")
        return
        
    state_info = user_states.get(user_id)
    
    if isinstance(state_info, dict) and state_info.get('state') == 'admin_waiting_bulk_file':
        price = state_info.get('price')
        file_info = message.document
        
        try:
            bot.send_message(user_id, "Processing your bulk file, please wait...")
            downloaded_file_info = bot.get_file(file_info.file_id)
            file_content = bot.download_file(downloaded_file_info.file_path)
            
            lines = file_content.decode('utf-8').splitlines()
            
            added_count = 0
            failed_count = 0

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split('|')
                if len(parts) != 10:
                    failed_count += 1
                    continue

                try:
                    card_number, exp_month, exp_year, cvv, holder, address, city, state, zip_code, country = [p.strip() for p in parts]
                    
                    # Create Product Name
                    card_type = get_card_type(card_number)
                    product_name = f"{card_type} - {card_number[:6]} - {country}"
                    
                    # Create Product Description
                    # Note: This is the PUBLIC description. The full card line is the file content.
                    product_description = (
                        f"Holder: {holder}\n"
                        f"Address: {address}, {city}, {state}, {zip_code}, {country}\n"
                        f"Expires: {exp_month}/{exp_year}\n"
                        f"CVV: {cvv}"
                    )

                    # Each line becomes its own product with its own file (containing the original full line)
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
    else:
        bot.send_message(user_id, "To upload products, please first set a price for the items in the file using the command:\n`/addproducts <price>`", parse_mode="MarkdownV2")


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
        
# --- 'BROWSE PRODUCTS' HANDLER (WITH 6-DIGIT PREVIEW) ---
@bot.message_handler(func=lambda message: message.text == 'Browse Products')
def browse_products(message):
    products = get_products()
    if not products:
        bot.send_message(message.chat.id, "No products available.")
        return
    markup = types.InlineKeyboardMarkup()
    for p in products:
        product_id, name, desc, price, _, _, _, _ = p
        # Use first 6 chars of the description for the preview
        preview = f" ({desc.splitlines()[0][:6]}...)" if desc else ""
        button_text = f"{name}{preview} - {format_price(price)}"
        markup.row(types.InlineKeyboardButton(button_text, callback_data=f"product_{product_id}"))
    bot.send_message(message.chat.id, "Available Products:", reply_markup=markup)

# (The rest of the handlers and functions like callbacks, my_purchases, etc. are assumed to be here)
# ...

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
