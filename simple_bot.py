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

def get_card_type(card_number):
    if card_number.startswith('4'): return 'Visa'
    elif card_number.startswith('5'): return 'Mastercard'
    elif card_number.startswith('3'): return 'Amex'
    elif card_number.startswith('6'): return 'Discover'
    else: return 'Card'


# --- DATABASE FUNCTIONS (ALL RESTORED) ---
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

def get_user_balance(user_id):
    user = get_or_create_user(user_id)
    return user[2] if user else 0.0

def add_product_to_db(name, description, price, file_path, file_name):
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO products (name, description, price, file_path, file_name) VALUES (?, ?, ?, ?, ?)", (name, description, price, file_path, file_name))
    conn.commit()
    pid = cursor.lastrowid
    conn.close()
    return pid

def get_products():
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE active = 1 ORDER BY created_at DESC")
    products = cursor.fetchall()
    conn.close()
    return products

def deactivate_product_in_db(product_id):
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE products SET active = 0 WHERE id = ?", (product_id,))
    conn.commit()
    rows = cursor.rowcount
    conn.close()
    return rows > 0

def get_product(product_id):
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    conn.close()
    return product

def create_purchase(user_id, username, product_id, payment_method, amount):
    payment_id = str(uuid.uuid4())
    access_token = str(uuid.uuid4())
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO purchases (user_id, username, product_id, payment_method, amount, payment_id, access_token) VALUES (?, ?, ?, ?, ?, ?, ?)", (user_id, username, product_id, payment_method, amount, payment_id, access_token))
    conn.commit()
    pid = cursor.lastrowid
    conn.close()
    return payment_id, access_token, pid

def confirm_payment(payment_id):
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE purchases SET payment_status = 'completed' WHERE payment_id = ?", (payment_id,))
    conn.commit()
    rows = cursor.rowcount
    conn.close()
    return rows > 0

def get_purchase_by_payment_id(payment_id):
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT pu.id, pu.user_id, pu.product_id, pu.payment_status, pu.access_token, p.name FROM purchases pu JOIN products p ON pu.product_id = p.id WHERE pu.payment_id = ?", (payment_id,))
    res = cursor.fetchone()
    conn.close()
    return res

def get_file_by_token(access_token):
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT p.file_path, p.file_name FROM purchases pu JOIN products p ON pu.product_id = p.id WHERE pu.access_token = ? AND pu.payment_status = 'completed'", (access_token,))
    res = cursor.fetchone()
    conn.close()
    return res


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

@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS: return
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
            base_product_name = os.path.splitext(file_info.file_name)[0]
            
            added_count = 0
            failed_count = 0
            for i, line in enumerate(lines):
                line = line.strip()
                if not line: continue
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
            debug_print(f"Major file processing error: {str(e)}")
            bot.send_message(user_id, "An unexpected error occurred while processing the file.")
        
        finally:
            user_states.pop(user_id, None)
    else:
        bot.send_message(user_id, "To upload products, please first set a price using the command:\n`/addproducts <price>`", parse_mode="MarkdownV2")

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

def browse_products(message):
    products = get_products()
    if not products:
        bot.send_message(message.chat.id, "No products available.")
        return
    markup = types.InlineKeyboardMarkup()
    for p in products:
        product_id, name, desc, price, _, _, _, _ = p
        button_text = f"{name} - {format_price(price)}"
        markup.row(types.InlineKeyboardButton(button_text, callback_data=f"product_{product_id}"))
    bot.send_message(message.chat.id, "Available Products:", reply_markup=markup)

def my_purchases(message):
    # This function's logic needs to be fully implemented
    bot.send_message(message.chat.id, "Fetching purchase history...")

def support(message):
     bot.send_message(message.chat.id, "For support, contact an admin.")

# (All other handlers and functions must be defined before the polling starts)

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
