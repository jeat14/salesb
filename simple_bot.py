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
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0)')
    conn.commit()
    conn.close()

def get_or_create_user(user_id, username=None):
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0.0)", (user_id,))
    if username:
        cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.commit()
    conn.close()
    return user

def get_all_users():
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, balance FROM users ORDER BY balance DESC")
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
    if len(message.text.split()) > 1:
        token = message.text.split()[1]
        if token.startswith('download_'):
            handle_download(message, token.replace('download_', ''))
            return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('Browse Products', 'My Purchases')
    markup.row('My Balance', 'Support')
    
    welcome_text = f"Welcome to Retrinity cc shop, {escape_markdown(message.from_user.first_name)}\!"
    
    if message.from_user.id in ADMIN_IDS:
        welcome_text += "\n\n*Admin tip:* To add products, just upload a `\.txt` file\. To add funds, use `/addfunds`\."

    bot.reply_to(message, welcome_text, reply_markup=markup, parse_mode="MarkdownV2")

@bot.message_handler(commands=['addfunds'])
def add_funds_command(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "This command is for admins only\.")
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

@bot.message_handler(commands=['users'])
def list_users_command(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "This command is for admins only.")
        return
    users = get_all_users()
    if not users:
        bot.reply_to(message, "No users have interacted with the bot yet.")
        return
    file_content = "User ID,Username,Balance\n"
    for user in users:
        user_id, username, balance = user
        file_content += f"{user_id},{username or 'N/A'},{balance:.2f}\n"
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
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "This command is for admins only\.")
        return
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


@bot.message_handler(func=lambda message: message.text == 'My Balance')
def show_balance_handler(message):
    balance = get_user_balance(message.from_user.id)
    bot.send_message(message.chat.id, f"💰 Your current balance is: *{escape_markdown(format_price(balance))}*", parse_mode="MarkdownV2")


@content_types=['document'])
def handle_file_upload(message):
    user_id = message.from_user.id
    # This function is now the primary way for admins to add products.
    if user_id not in ADMIN_IDS:
        # Ignore files sent by non-admins
        return
        
    if not message.document.file_name.lower().endswith('.txt'):
        bot.send_message(message.chat.id, "Error: Only .txt files are accepted.")
        return
    
    # Store the file info and ask for the price.
    user_states[user_id] = {
        'state': 'admin_waiting_price',
        'file_info': message.document
    }
    bot.send_message(message.chat.id, f"File `{escape_markdown(message.document.file_name)}` received\. What should the price be for each item in this file\?", parse_mode="MarkdownV2")

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    user_id = message.from_user.id
    
    # Handle the price input from an admin after uploading a file
    if isinstance(user_states.get(user_id), dict) and user_states[user_id].get('state') == 'admin_waiting_price':
        try:
            price = float(message.text.strip())
            if price <= 0:
                bot.send_message(message.chat.id, "Price must be a positive number.")
                return
        except ValueError:
            bot.send_message(message.chat.id, "Invalid price format. Please send only a number.")
            return

        # Process the file with the given price
        file_info = user_states[user_id]['file_info']
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
                
                # Each line becomes its own product with its own file
                product_name = f"{base_product_name}-{i+1}"
                file_path, error = save_individual_product_file(description)
                if error:
                    failed_count += 1
                    continue

                add_product_to_db(product_name, description, price, file_path, os.path.basename(file_path))
                added_count += 1
            
            summary_message = f"✅ **Bulk Upload Complete**\n\nSuccessfully added: *{added_count}* products\.\nFailed to process: *{failed_count}* lines\."
            bot.send_message(message.chat.id, escape_markdown(summary_message), parse_mode="MarkdownV2")
        
        except Exception as e:
            debug_print(f"File processing error: {str(e)}")
            bot.send_message(message.chat.id, "An error occurred while processing the file.")
        
        finally:
            # Clear the state
            user_states.pop(user_id, None)
            
    # Handle regular user button presses
    elif message.text == 'Browse Products':
        browse_products(message)
    elif message.text == 'My Purchases':
        my_purchases(message)
    elif message.text == 'Support':
        support(message)
    else:
        bot.send_message(message.chat.id, "I don't understand that. Please use the menu buttons.")


# ... (The rest of the handlers and functions like browse_products, my_purchases, support, callbacks, etc.)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    # This function handles all inline button presses
    # It remains largely the same, but the logic for removing products is now inside here.
    user_id = call.from_user.id
    try:
        if call.data.startswith('remove_'):
            if user_id not in ADMIN_IDS: return
            product_id = int(call.data.split('_')[1])
            if deactivate_product_in_db(product_id):
                bot.answer_callback_query(call.id, "Product removed successfully.")
                bot.edit_message_text("✅ Product has been removed.", call.message.chat.id, call.message.message_id)
            else:
                bot.answer_callback_query(call.id, "Error: Could not remove product.")
        
        elif call.data == "cancel_action":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id, "Cancelled.")

        # ... other callbacks for buying products ...
        
        bot.answer_callback_query(call.id)
    except Exception as e:
        debug_print(f"Callback error: {str(e)}")
        bot.answer_callback_query(call.id, "An error occurred.")


if __name__ == "__main__":
    init_database()
    debug_print("Bot starting up in simplified admin mode...")
    try:
        while True:
            try:
                bot.infinity_polling(timeout=30, long_polling_timeout=15)
            except Exception as e:
                debug_print(f"Polling failed, restarting in 5 seconds: {e}")
                time.sleep(5)
    except Exception as e:
        debug_print(f"An unexpected error occurred: {e}")
