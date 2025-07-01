import telebot
from telebot import types
import os
import sqlite3
import uuid
from datetime import datetime
import re

# --- CONFIGURATION ---
TOKEN = '8060770660:AAHh2Y1YH0GR2F6hIhC3Ip3r5RIN1xtcgcE' # Replace with your bot's token
ADMIN_IDS = [
    7481885595,  # @packoa's ID
    7864373277,  # @xenslol's ID
]
PAYPAL_USERNAME = "CaitlinGetrajdman367" # Your PayPal.me username

# --- INITIALIZATION ---
bot = telebot.TeleBot(TOKEN, parse_mode='MarkdownV2') # Set default parse mode for all messages
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

def save_file(file_content, original_filename):
    file_ext = os.path.splitext(original_filename)[1].lower()
    if file_ext != '.txt': return None, "Only \.txt files are allowed"
    secure_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(UPLOAD_FOLDER, secure_filename)
    with open(file_path, 'wb') as f: f.write(file_content)
    return file_path, None


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
    debug_print(f"Start command from user {message.from_user.id}")
    if len(message.text.split()) > 1:
        token = message.text.split()[1]
        if token.startswith('download_'):
            handle_download(message, token.replace('download_', ''))
            return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('Browse Products', 'My Purchases')
    markup.row('My Balance', 'Support')
    if message.from_user.id in ADMIN_IDS:
        markup.row('Admin Panel')
    welcome_text = f"Welcome to Retrinity cc shop, {escape_markdown(message.from_user.first_name)}\!"
    bot.reply_to(message, welcome_text, reply_markup=markup)

@bot.message_handler(commands=['addfunds'])
def add_funds_command(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "This command is for admins only\.")
        return
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "Usage:\n/addfunds `<@username_or_id> <amount>`")
        return
    target_identifier = parts[1]
    target_user_id = None
    if target_identifier.startswith('@'):
        target_user_id = get_user_by_username(target_identifier)
        if not target_user_id:
            bot.reply_to(message, f"User `{escape_markdown(target_identifier)}` not found\. They must have started the bot at least once\.")
            return
    elif target_identifier.isdigit():
        target_user_id = int(target_identifier)
    else:
        bot.reply_to(message, "Invalid user identifier\. Please use a User ID or an @username\.")
        return
    try:
        amount = float(parts[2])
    except ValueError:
        bot.reply_to(message, "Invalid Amount\. Please use a number\.")
        return
    update_user_balance(target_user_id, amount)
    new_balance = get_user_balance(target_user_id)
    bot.reply_to(message, f"✅ Successfully added `{escape_markdown(format_price(amount))}` to user `{escape_markdown(target_identifier)}`\.\nTheir new balance is: `{escape_markdown(format_price(new_balance))}`")
    try:
        bot.send_message(target_user_id, f"An admin has added `{escape_markdown(format_price(amount))}` to your balance\.\nYour new balance is: `{escape_markdown(format_price(new_balance))}`")
    except Exception as e:
        debug_print(f"Could not notify user {target_user_id} about added funds: {e}")

@bot.message_handler(func=lambda message: message.text == 'My Balance')
def show_balance_handler(message):
    balance = get_user_balance(message.from_user.id)
    bot.send_message(message.chat.id, f"💰 Your current balance is: *{escape_markdown(format_price(balance))}*")

@bot.message_handler(func=lambda message: message.text == 'Admin Panel')
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "Access denied.", parse_mode=None)
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('Add Product', 'Remove Product')
    markup.row('View Orders', '🧪 Test Mode')
    markup.row('Back to Shop')
    user_states.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "Admin Panel\n\nSelect an option:", reply_markup=markup, parse_mode=None)

@bot.message_handler(func=lambda message: message.text == 'Add Product')
def add_product_start(message):
    if message.from_user.id not in ADMIN_IDS: return
    user_states[message.from_user.id] = 'waiting_file'
    bot.send_message(message.chat.id, "Please upload the .txt file you want to sell.", parse_mode=None)

@bot.message_handler(func=lambda message: message.text == 'Remove Product')
def remove_product_start(message):
    if message.from_user.id not in ADMIN_IDS: return
    products = get_products()
    if not products:
        bot.send_message(message.chat.id, "There are no active products to remove.", parse_mode=None)
        return
    markup = types.InlineKeyboardMarkup()
    for p in products:
        product_id, name, _, price, _, _, _, _ = p
        button_text = f"❌ {name} - {format_price(price)}"
        markup.row(types.InlineKeyboardButton(button_text, callback_data=f"remove_{product_id}"))
    markup.row(types.InlineKeyboardButton("🔙 Back to Admin", callback_data="back_admin"))
    bot.send_message(message.chat.id, "Select a product to remove from the shop:", reply_markup=markup, parse_mode=None)

@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS or user_states.get(user_id) != 'waiting_file': return
    if not message.document.file_name.lower().endswith('.txt'):
        bot.send_message(message.chat.id, "Error: Only .txt files are accepted.", parse_mode=None)
        return
    try:
        file_info = bot.get_file(message.document.file_id)
        file_content = bot.download_file(file_info.file_path)
        file_path, error = save_file(file_content, message.document.file_name)
        if error:
            bot.send_message(message.chat.id, f"Error: {error}", parse_mode=None)
            return
        product_name = os.path.splitext(message.document.file_name)[0]
        try: description = file_content.decode('utf-8')
        except: description = "Unable to read file content."
        user_states[user_id] = {'state': 'waiting_price', 'file_path': file_path, 'file_name': message.document.file_name, 'product_name': product_name, 'description': description}
        bot.send_message(message.chat.id, f"File {message.document.file_name} uploaded.\nNow, please enter the price for this item.", parse_mode=None)
    except Exception as e:
        debug_print(f"File upload error: {str(e)}")
        bot.send_message(message.chat.id, "An error occurred during file upload.", parse_mode=None)

@bot.message_handler(func=lambda message: message.text == 'Browse Products')
def browse_products(message):
    products = get_products()
    if not products:
        bot.send_message(message.chat.id, "No products available.", parse_mode=None)
        return
    markup = types.InlineKeyboardMarkup()
    for p in products:
        product_id, name, desc, price, _, _, _, _ = p
        button_text = f"{name} ({format_price(price)})"
        markup.row(types.InlineKeyboardButton(button_text, callback_data=f"product_{product_id}"))
    bot.send_message(message.chat.id, "Available Products:", reply_markup=markup, parse_mode=None)

@bot.message_handler(func=lambda message: message.text == 'My Purchases')
def my_purchases(message):
    bot.send_message(message.chat.id, "Fetching your purchase history...", parse_mode=None)

@bot.message_handler(func=lambda message: message.text == 'Support')
def support(message):
    bot.send_message(message.chat.id, "For any questions, please contact the admin: @xenslol", parse_mode=None)

@bot.message_handler(func=lambda message: message.text == 'Back to Shop')
def back_to_shop(message):
    send_welcome(message)

@bot.message_handler(func=lambda message: message.text == 'View Orders')
def view_orders(message):
    bot.send_message(message.chat.id, "Fetching all orders...", parse_mode=None)

@bot.message_handler(func=lambda message: message.text == '🧪 Test Mode')
def test_mode(message):
    if message.from_user.id not in ADMIN_IDS: return
    bot.send_message(message.chat.id, "Entering test mode...", parse_mode=None)

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    user_id = message.from_user.id
    if isinstance(user_states.get(user_id), dict) and user_states[user_id].get('state') == 'waiting_price':
        try:
            price = float(message.text.strip())
            if price <= 0:
                bot.send_message(message.chat.id, "Price must be a positive number.", parse_mode=None)
                return
        except ValueError:
            bot.send_message(message.chat.id, "Invalid price format.", parse_mode=None)
            return
        product_data = user_states[user_id]
        try:
            add_product_to_db(name=product_data['product_name'], description=product_data['description'], price=price, file_path=product_data['file_path'], file_name=product_data['file_name'])
            bot.send_message(message.chat.id, "✅ Product Added Successfully!", parse_mode=None)
            user_states.pop(user_id, None)
            admin_panel(message)
        except Exception as e:
            debug_print(f"Product creation error: {str(e)}")
            bot.send_message(message.chat.id, "Failed to create the product.", parse_mode=None)
    else:
        bot.send_message(message.chat.id, "I don't understand that. Please use the menu buttons.", parse_mode=None)


@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    try:
        if call.data.startswith('product_'):
            product_id = int(call.data.split('_')[1])
            product = get_product(product_id)
            if not product: bot.edit_message_text("Product not found\.", call.message.chat.id, call.message.message_id); return
            
            _, name, description, price, _, _, _, _ = product
            
            esc_name = escape_markdown(name)
            esc_desc = escape_markdown(description or "No description available\.")
            desc_preview = f"{esc_desc[:20]}..." if len(esc_desc) > 20 else esc_desc
            
            product_text = f"📄 *{esc_name}*\n\n💰 *Price:* {escape_markdown(format_price(price))}\n📝 *Description:*\n{desc_preview}\n\nChoose your payment method:"
            
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("💳 CashApp", callback_data=f"buy_cashapp_{product_id}"), types.InlineKeyboardButton("₿ Crypto", callback_data=f"buy_crypto_{product_id}"))
            markup.row(types.InlineKeyboardButton(f"🅿️ PayPal", callback_data=f"buy_paypal_{product_id}"))
            markup.row(types.InlineKeyboardButton("🔙 Back to Products", callback_data="back_products"))
            bot.edit_message_text(product_text, call.message.chat.id, call.message.message_id, reply_markup=markup)

        elif call.data.startswith('buy_'):
            parts = call.data.split('_')
            payment_method, product_id = parts[1], int(parts[2])
            product = get_product(product_id)
            if not product: bot.answer_callback_query(call.id, "Product not found"); return
            
            price = product[3]
            if get_user_balance(user_id) >= price:
                markup = types.InlineKeyboardMarkup()
                markup.row(types.InlineKeyboardButton(f"Pay with Balance ({format_price(price)})", callback_data=f"pay_balance_{product_id}"))
                markup.row(types.InlineKeyboardButton("Pay with External Method", callback_data=f"pay_external_{payment_method}_{product_id}"))
                markup.row(types.InlineKeyboardButton("Cancel", callback_data="back_products"))
                bot.edit_message_text("You have enough funds to buy this item\.\n\nHow would you like to pay?", call.message.chat.id, call.message.message_id)
            else:
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
                bot.edit_message_text(success_text, call.message.chat.id, call.message.message_id, reply_markup=None)
                handle_download_callback(call, access_token)
            else:
                bot.edit_message_text("Your balance is no longer sufficient\.", call.message.chat.id, call.message.message_id, reply_markup=None)
        
        elif call.data.startswith('pay_external_'):
            parts = call.data.split('_')
            payment_method, product_id = parts[2], int(parts[3])
            show_external_payment_info(call, payment_method, product_id)
            
        bot.answer_callback_query(call.id)
    except Exception as e:
        debug_print(f"Callback error: {str(e)}")
        bot.answer_callback_query(call.id, "An error occurred.")


def show_external_payment_info(call, payment_method, product_id):
    product = get_product(product_id)
    if not product: bot.answer_callback_query(call.id, "Product not found"); return
    
    payment_id, _, _ = create_purchase(call.from_user.id, call.from_user.username, product_id, payment_method, product[3])
    
    esc_name = escape_markdown(product[1])
    esc_price = escape_markdown(format_price(product[3]))
    esc_payment_id = payment_id[:8] # This is for code block, no need to escape

    payment_text = f"*💳 Payment Required*\n\n📄 *Product:* {esc_name}\n💰 *Amount:* {esc_price}\n\n"
    
    if payment_method == 'cashapp':
        payment_text += f"Send payment to `$shonwithcash`\nIn the 'For' / 'Note' section, you *MUST* include this ID:\n`{esc_payment_id}`"
    elif payment_method == 'paypal':
        paypal_link = escape_markdown(f"https://paypal.me/{PAYPAL_USERNAME}")
        payment_text += f"Send payment via the link below:\n{paypal_link}\n\n"
        payment_text += f"In the 'Add a note' section, you *MUST* include this ID:\n`{esc_payment_id}`"
    else: # crypto
        payment_text += "*Send the exact amount to one of the addresses below*\n\n" \
                        "🟡 *Bitcoin \\(BTC\\):*\n`bc1q9nc2clammklw8jtvmzfqxg4e9exlcc7ww7e64e`\n\n" \
                        "🔵 *Litecoin \\(LTC\\):*\n`LZXDSYuxo2XZroFMgdQPRxfi2vjV3ncq3r`\n\n" \
                        "🟣 *Ethereum \\(ETH\\):*\n`0xf812b0466ea671B3FadC75E9624dFeFd507F22C8`\n\n" \
                        f"After sending, an admin will confirm your payment\. Your Order ID is `{esc_payment_id}`\."
    
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔙 Back to Products", callback_data="back_products"))
    bot.edit_message_text(payment_text, call.message.chat.id, call.message.message_id, reply_markup=markup)

def handle_download_callback(call, access_token):
    file_info = get_file_by_token(access_token)
    if not file_info: bot.send_message(call.message.chat.id, "File not found or your payment is not yet confirmed\."); return
    file_path, file_name = file_info
    try:
        with open(file_path, 'rb') as f:
            bot.send_document(call.message.chat.id, f, caption=f"Thank you for your purchase\!\n\n📁 {escape_markdown(file_name)}")
    except Exception as e:
        debug_print(f"Download error: {str(e)}")
        bot.send_message(call.message.chat.id, "Failed to send the file\. Please contact support\.")

def handle_download(message, access_token):
    file_info = get_file_by_token(access_token)
    if not file_info: bot.send_message(message.chat.id, "File not found or your payment is not yet confirmed\."); return
    file_path, file_name = file_info
    try:
        with open(file_path, 'rb') as f:
            bot.send_document(message.chat.id, f, caption=f"Thank you for your purchase\!\n\n📁 {escape_markdown(file_name)}")
    except Exception as e:
        debug_print(f"Download error: {str(e)}")
        bot.send_message(message.chat.id, "Failed to send the file\. Please contact support\.")

if __name__ == "__main__":
    init_database()
    debug_print("Bot starting up...")
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        debug_print(f"An error occurred in the polling loop: {e}")
