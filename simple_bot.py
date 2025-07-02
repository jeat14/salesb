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
    if message.from_user.id in ADMIN_IDS:
        welcome_text += "\n\n*Admin tip:* To add items, upload a `\.txt` file\. Use `/addfunds`, `/users`, `/remove`, `/addfadmin`\."
    bot.reply_to(message, welcome_text, reply_markup=markup, parse_mode="MarkdownV2")

@bot.message_handler(commands=['addfadmin', 'removefadmin'])
def manage_funds_admin_command(message):
    # This logic is for full admins to manage funds admins
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "This command is for full admins only\.")
        return
    # ... (rest of logic from previous versions)

@bot.message_handler(commands=['users', 'addfunds', 'remove'])
def admin_commands(message):
    # This groups several admin commands
    if message.text.startswith('/users'):
        if message.from_user.id not in ADMIN_IDS: return
        users = get_all_users()
        if not users: bot.reply_to(message, "No users yet."); return
        file_content = "User ID,Username,Balance,Role\n"
        for user in users:
            file_content += f"{user[0]},{user[1] or 'N/A'},{user[2]:.2f},{user[3]}\n"
        try:
            with open("user_list.csv", "w", encoding="utf-8") as file: file.write(file_content)
            with open("user_list.csv", "rb") as file: bot.send_document(message.chat.id, file, caption="Here is the list of all bot users.")
            os.remove("user_list.csv")
        except Exception as e: debug_print(f"Failed to send user list file: {e}")

    elif message.text.startswith('/addfunds'):
        user_role = get_user_role(message.from_user.id)
        if message.from_user.id not in ADMIN_IDS and user_role != 'funds_admin':
             bot.reply_to(message, "You do not have permission to use this command\.")
             return
        # (rest of addfunds logic)

    elif message.text.startswith('/remove'):
        if message.from_user.id not in ADMIN_IDS: return
        products = get_products()
        if not products: bot.send_message(message.chat.id, "There are no active products to remove."); return
        markup = types.InlineKeyboardMarkup()
        for p in products:
            markup.row(types.InlineKeyboardButton(f"❌ {p[1]} - {format_price(p[3])}", callback_data=f"remove_{p[0]}"))
        markup.row(types.InlineKeyboardButton("🔙 Cancel", callback_data="cancel_action"))
        bot.send_message(message.chat.id, "Select a product to remove from the shop:", reply_markup=markup)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    if message.from_user.id not in ADMIN_IDS: return
    if not message.document.file_name.lower().endswith('.txt'):
        bot.send_message(message.from_user.id, "Error: Only .txt files are accepted.")
        return
    user_states[message.from_user.id] = { 'state': 'admin_waiting_price', 'file_id': message.document.file_id, 'file_name': message.document.file_name }
    bot.send_message(message.from_user.id, f"File `{escape_markdown(message.document.file_name)}` received\. Please reply with the price for each item in this file\.", parse_mode="MarkdownV2")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    state_info = user_states.get(user_id)
    if isinstance(state_info, dict) and state_info.get('state') == 'admin_waiting_price':
        try:
            price = float(message.text.strip())
            if price <= 0: bot.reply_to(message, "Price must be a positive number."); return
        except ValueError:
            bot.reply_to(message, "Invalid price format."); return
        
        bot.send_message(user_id, "Processing your bulk file, please wait...")
        file_id = state_info['file_id']
        base_product_name = os.path.splitext(state_info['file_name'])[0]
        try:
            downloaded_file_info = bot.get_file(file_id)
            file_content = bot.download_file(downloaded_file_info.file_path)
            lines = file_content.decode('utf-8').splitlines()
            added_count, failed_count = 0, 0
            for i, line in enumerate(lines):
                line = line.strip()
                if not line: continue
                parts = line.split('|')
                if len(parts) != 10: failed_count += 1; continue
                try:
                    card_number, exp_month, exp_year, cvv, holder, address, city, state, zip_code, country = [p.strip() for p in parts]
                    card_type = get_card_type(card_number)
                    product_name = f"{card_type} - {card_number[:6]} - {country}"
                    product_description = f"Holder: {holder}\nAddress: {address}, {city}, {state}, {zip_code}, {country}\nExpires: {exp_month}/{exp_year}\nCVV: {cvv}"
                    file_path, error = save_individual_product_file(line)
                    if error: failed_count += 1; continue
                    add_product_to_db(product_name, product_description, price, file_path, f"{product_name}.txt")
                    added_count += 1
                except Exception as e:
                    failed_count += 1; debug_print(f"Error processing line '{line}': {e}")
            summary_message = f"✅ *Bulk Upload Complete*\n\nSuccessfully added: `{added_count}`\nFailed to process: `{failed_count}`"
            bot.send_message(user_id, summary_message, parse_mode="MarkdownV2")
        except Exception as e:
            debug_print(f"File processing error: {str(e)}")
            bot.send_message(user_id, "An error occurred while processing the file.")
        finally:
            user_states.pop(user_id, None)

    elif message.text == 'Browse Products': browse_products(message)
    elif message.text == 'My Purchases': my_purchases(message)
    elif message.text == 'Support': support(message)
    elif message.text == 'My Balance': show_balance_handler(message)
    else: bot.send_message(message.chat.id, "I don't understand that. Please use the menu buttons.")

def browse_products(message):
    products = get_products()
    if not products: bot.send_message(message.chat.id, "No products available."); return
    markup = types.InlineKeyboardMarkup()
    for p in products:
        markup.row(types.InlineKeyboardButton(f"{p[1]} - {format_price(p[3])}", callback_data=f"product_{p[0]}"))
    bot.send_message(message.chat.id, "Available Products:", reply_markup=markup)

def my_purchases(message):
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT p.name, pu.amount, pu.purchase_date, pu.access_token, pu.payment_status FROM purchases pu JOIN products p ON pu.product_id = p.id WHERE pu.user_id = ? ORDER BY pu.purchase_date DESC", (message.from_user.id,))
    purchases = cursor.fetchall()
    conn.close()
    if not purchases: bot.send_message(message.chat.id, "You have not made any purchases yet\."); return
    text = "*📋 Your Purchase History*\n\n"
    markup = types.InlineKeyboardMarkup()
    status_emoji = {'pending': '⏳', 'completed': '✅'}
    for name, amount, date, token, payment_status in purchases:
        text += f"📄 *{escape_markdown(name)}*\n"
        text += f"💰 {escape_markdown(format_price(amount))}\n"
        text += f"💳 Status: {status_emoji.get(payment_status, '❓')} {escape_markdown(payment_status.title())}\n"
        text += f"📅 {escape_markdown(date.split('.')[0])}\n"
        if payment_status == 'completed':
            markup.row(types.InlineKeyboardButton(f"📥 Download {name[:20]}", callback_data=f"download_{token}"))
            text += "✅ Ready for download\n\n"
        else:
            text += f"⏳ Awaiting payment confirmation\.\n\n"
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="MarkdownV2")

def support(message):
     bot.send_message(message.chat.id, "💬 For any questions, please contact an admin\.")

def show_balance_handler(message):
    balance = get_user_balance(message.from_user.id)
    bot.send_message(message.chat.id, f"💰 Your current balance is: *{escape_markdown(format_price(balance))}*", parse_mode="MarkdownV2")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    try:
        if call.data.startswith('product_'):
            product_id = int(call.data.split('_')[1])
            product = get_product(product_id)
            if not product: bot.edit_message_text("Product not found\.", call.message.chat.id, call.message.message_id, parse_mode="MarkdownV2"); return
            _, name, description, price, _, _, _, _ = product
            balance = get_user_balance(user_id)
            esc_name = escape_markdown(name)
            esc_desc = escape_markdown(description or "No description available\.")
            desc_preview = f"{esc_desc[:6]}\.\.\." if len(esc_desc) > 6 else esc_desc
            product_text = f"📄 *{esc_name}*\n\n💰 *Price:* {escape_markdown(format_price(price))}\n📝 *Description:*\n{desc_preview}"
            markup = types.InlineKeyboardMarkup()
            if balance >= price:
                product_text += f"\n\n*You have enough funds to buy this item\!*"
                markup.row(types.InlineKeyboardButton(f"Pay with Balance ({format_price(price)})", callback_data=f"pay_balance_{product_id}"))
                markup.row(types.InlineKeyboardButton("Use Other Method instead", callback_data=f"show_external_options_{product_id}"))
            else:
                product_text += "\n\nChoose your payment method:"
                markup.row(types.InlineKeyboardButton("💳 CashApp", callback_data=f"buy_cashapp_{product_id}"), types.InlineKeyboardButton("₿ Crypto", callback_data=f"buy_crypto_{product_id}"))
                markup.row(types.InlineKeyboardButton(f"🅿️ PayPal", callback_data=f"buy_paypal_{product_id}"))
            markup.row(types.InlineKeyboardButton("🔙 Back to Products", callback_data="back_products"))
            bot.edit_message_text(product_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="MarkdownV2")

        elif call.data.startswith('show_external_options_'):
            product_id = int(call.data.split('_')[3])
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("💳 CashApp", callback_data=f"buy_cashapp_{product_id}"), types.InlineKeyboardButton("₿ Crypto", callback_data=f"buy_crypto_{product_id}"))
            markup.row(types.InlineKeyboardButton(f"🅿️ PayPal", callback_data=f"buy_paypal_{product_id}"))
            markup.row(types.InlineKeyboardButton("🔙 Back", callback_data=f"product_{product_id}"))
            bot.edit_message_text("Please choose your external payment method:", call.message.chat.id, call.message.message_id, reply_markup=markup)

        elif call.data.startswith('buy_'):
            parts = call.data.split('_'); payment_method, product_id = parts[1], int(parts[2])
            show_external_payment_info(call, payment_method, product_id)

        elif call.data.startswith('pay_balance_'):
            product_id = int(call.data.split('_')[2])
            product = get_product(product_id)
            if not product: bot.answer_callback_query(call.id, "Product not found\."); return
            price = product[3]
            if get_user_balance(user_id) >= price:
                update_user_balance(user_id, -price)
                new_balance = get_user_balance(user_id)
                payment_id, access_token, _ = create_purchase(user_id, call.from_user.username, product_id, 'balance', price)
                confirm_payment(payment_id)
                deactivate_product_in_db(product_id)
                success_text = f"✅ *Purchase Successful\!*\n\nYour new balance is *{escape_markdown(format_price(new_balance))}*\.\n\nHere is your download:"
                bot.edit_message_text(success_text, call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="MarkdownV2")
                handle_download_callback(call, access_token)
            else:
                bot.edit_message_text("Your balance is no longer sufficient\.", call.message.chat.id, call.message.message_id, parse_mode="MarkdownV2")
        
        elif call.data.startswith('remove_'):
            if user_id not in ADMIN_IDS: return
            product_id = int(call.data.split('_')[1])
            product = get_product(product_id)
            if deactivate_product_in_db(product_id):
                bot.answer_callback_query(call.id, "Product removed successfully.")
                bot.edit_message_text(f"✅ Product *{escape_markdown(product[1])}* has been removed\.", call.message.chat.id, call.message.message_id, parse_mode="MarkdownV2")
            else:
                bot.answer_callback_query(call.id, "Error: Could not remove product.")

        elif call.data.startswith('download_'):
            handle_download_callback(call, call.data.replace('download_', ''))
            
        elif call.data.startswith('confirm_'):
            if user_id not in ADMIN_IDS: return
            # ... confirmation logic ...
            
        elif call.data == "back_products":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            browse_products(call.message)
            
        elif call.data == "back_admin" or call.data == "cancel_action":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            
        bot.answer_callback_query(call.id)
    except Exception as e:
        debug_print(f"Callback error: {str(e)}")
        bot.answer_callback_query(call.id, "An error occurred.")

def show_external_payment_info(call, payment_method, product_id):
    product = get_product(product_id)
    if not product: bot.answer_callback_query(call.id, "Product not found"); return
    payment_id, _, _ = create_purchase(call.from_user.id, call.from_user.username, product_id, payment_method, product[3])
    esc_name, esc_price, esc_payment_id = escape_markdown(product[1]), escape_markdown(format_price(product[3])), payment_id[:8]
    payment_text = f"*💳 Payment Required*\n\n📄 *Product:* {esc_name}\n💰 *Amount:* {esc_price}\n\n"
    if payment_method == 'cashapp':
        payment_text += f"Send payment to `$shonwithcash`\nIn the 'For' / 'Note' section, you *MUST* include this ID:\n`{esc_payment_id}`"
    elif payment_method == 'paypal':
        payment_text += f"Send payment via the link below:\n{escape_markdown(f'https://paypal.me/{PAYPAL_USERNAME}')}\n\n"
        payment_text += f"In the 'Add a note' section, you *MUST* include this ID:\n`{esc_payment_id}`"
    else: # crypto
        payment_text += "*Send the exact amount to one of the addresses below*\n\n" \
                        "🟡 *Bitcoin \\(BTC\\):*\n`bc1q9nc2clammklw8jtvmzfqxg4e9exlcc7ww7e64e`\n\n" \
                        f"After sending, an admin will confirm your payment\. Your Order ID is `{esc_payment_id}`\."
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔙 Back to Products", callback_data="back_products"))
    bot.edit_message_text(payment_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="MarkdownV2")

def handle_download_callback(call, access_token):
    file_info = get_file_by_token(access_token)
    if not file_info: bot.send_message(
