import telebot
from telebot import types
import os
import sqlite3
import uuid
from datetime import datetime

# --- CONFIGURATION ---
TOKEN = '8060770660:AAHh2Y1YH0GR2F6hIhC3Ip3r5RIN1xtcgcE'
ADMIN_IDS = [
    7481885595,  # @packoa's ID
    7864373277,  # @xenslol's ID
]

# --- INITIALIZATION ---
bot = telebot.TeleBot(TOKEN)
DEBUG = True
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

user_states = {}

# --- DATABASE FUNCTIONS ---

def init_database():
    """Initializes the database and creates tables if they don't exist."""
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT,
            price REAL NOT NULL, file_path TEXT NOT NULL, file_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, active INTEGER DEFAULT 1
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, username TEXT,
            product_id INTEGER NOT NULL, payment_method TEXT NOT NULL,
            payment_status TEXT DEFAULT 'pending', payment_id TEXT, amount REAL NOT NULL,
            purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, access_token TEXT,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0.0
        )
    ''')
    conn.commit()
    conn.close()

def get_or_create_user(user_id, username=None):
    """Robustly retrieves a user or creates them if they don't exist."""
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
    """Finds a user's ID by their username from the local database."""
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
    """Gets purchase details, including the product_id."""
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

# --- HELPER FUNCTIONS ---
def debug_print(message):
    if DEBUG: print(f"DEBUG: {message}")
def format_price(price):
    return f"${price:.2f}"
def save_file(file_content, original_filename):
    file_ext = os.path.splitext(original_filename)[1].lower()
    if file_ext != '.txt': return None, "Only .txt files are allowed."
    secure_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(UPLOAD_FOLDER, secure_filename)
    with open(file_path, 'wb') as f: f.write(file_content)
    return file_path, None

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
    bot.reply_to(message, f"Welcome to Retrinity cc shop, {message.from_user.first_name}!", reply_markup=markup)

@bot.message_handler(commands=['addfunds'])
def add_funds_command(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "This command is for admins only.")
        return
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "Usage:\n/addfunds <@username_or_id> <amount>")
        return
    target_identifier = parts[1]
    target_user_id = None
    if target_identifier.startswith('@'):
        target_user_id = get_user_by_username(target_identifier)
        if not target_user_id:
            bot.reply_to(message, f"User {target_identifier} not found. They must have started the bot at least once.")
            return
    elif target_identifier.isdigit():
        target_user_id = int(target_identifier)
    else:
        bot.reply_to(message, "Invalid user identifier. Please use a User ID or an @username.")
        return
    try:
        amount = float(parts[2])
    except ValueError:
        bot.reply_to(message, "Invalid Amount. Please use a number.")
        return
    update_user_balance(target_user_id, amount)
    new_balance = get_user_balance(target_user_id)
    bot.reply_to(message, f"✅ Successfully added {format_price(amount)} to user {target_identifier}.\nTheir new balance is: {format_price(new_balance)}")
    try:
        bot.send_message(target_user_id, f"An admin has added {format_price(amount)} to your balance.\nYour new balance is: {format_price(new_balance)}")
    except Exception as e:
        debug_print(f"Could not notify user {target_user_id} about added funds: {e}")

@bot.message_handler(func=lambda message: message.text == 'My Balance')
def show_balance_handler(message):
    balance = get_user_balance(message.from_user.id)
    bot.send_message(message.chat.id, f"💰 Your current balance is: {format_price(balance)}")

@bot.message_handler(func=lambda message: message.text == 'Admin Panel')
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "Access denied.")
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('Add Product', 'Remove Product')
    markup.row('View Orders', '🧪 Test Mode')
    markup.row('Back to Shop')
    user_states.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "Admin Panel\n\nSelect an option:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == 'Add Product')
def add_product_start(message):
    if message.from_user.id not in ADMIN_IDS: return
    user_states[message.from_user.id] = 'waiting_file'
    bot.send_message(message.chat.id, "Please upload the .txt file you want to sell.")

@bot.message_handler(func=lambda message: message.text == 'Remove Product')
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
    markup.row(types.InlineKeyboardButton("🔙 Back to Admin", callback_data="back_admin"))
    bot.send_message(message.chat.id, "Select a product to remove from the shop:", reply_markup=markup)

@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS or user_states.get(user_id) != 'waiting_file': return
    if not message.document.file_name.lower().endswith('.txt'):
        bot.send_message(message.chat.id, "Error: Only .txt files are accepted.")
        return
    try:
        file_info = bot.get_file(message.document.file_id)
        file_content = bot.download_file(file_info.file_path)
        file_path, error = save_file(file_content, message.document.file_name)
        if error:
            bot.send_message(message.chat.id, f"Error: {error}")
            return
        product_name = os.path.splitext(message.document.file_name)[0]
        try:
            description = file_content.decode('utf-8')
        except:
            description = "Unable to read file content."
        user_states[user_id] = {'state': 'waiting_price', 'file_path': file_path, 'file_name': message.document.file_name, 'product_name': product_name, 'description': description}
        bot.send_message(message.chat.id, f"📄 File `{message.document.file_name}` uploaded.\n**Now, please enter the price for this item.**", parse_mode="Markdown")
    except Exception as e:
        debug_print(f"File upload error: {str(e)}")
        bot.send_message(message.chat.id, "An error occurred during file upload.")
        user_states.pop(user_id, None)

@bot.message_handler(func=lambda message: message.text == 'Browse Products')
def browse_products(message):
    products = get_products()
    if not products:
        bot.send_message(message.chat.id, "No products available.")
        return
    markup = types.InlineKeyboardMarkup()
    for p in products:
        product_id, name, desc, price, _, _, _, _ = p
        preview = f" ({desc[:6]}...)" if desc else ""
        button_text = f"{name}{preview} - {format_price(price)}"
        markup.row(types.InlineKeyboardButton(button_text, callback_data=f"product_{product_id}"))
    bot.send_message(message.chat.id, "Available Products:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == 'My Purchases')
def my_purchases(message):
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT p.name, p.description, pu.amount, pu.purchase_date, pu.access_token, pu.payment_status FROM purchases pu JOIN products p ON pu.product_id = p.id WHERE pu.user_id = ? ORDER BY pu.purchase_date DESC", (message.from_user.id,))
    purchases = cursor.fetchall()
    conn.close()
    if not purchases:
        bot.send_message(message.chat.id, "You have not made any purchases yet.")
        return
    text = "📋 **Your Purchase History**\n\n"
    markup = types.InlineKeyboardMarkup()
    status_emoji = {'pending': '⏳', 'completed': '✅'}
    for purchase in purchases:
        name, description, amount, date, token, payment_status = purchase
        preview = f" ({description[:6]}...)" if description else ""
        text += f"📄 {name}{preview}\n"
        text += f"💰 {format_price(amount)}\n"
        text += f"💳 Status: {status_emoji.get(payment_status, '❓')} {payment_status.title()}\n"
        text += f"📅 {date.split('.')[0]}\n"
        if payment_status == 'completed':
            markup.row(types.InlineKeyboardButton(f"📥 Download {name[:20]}", callback_data=f"download_{token}"))
            text += "✅ Ready for download\n\n"
        else:
            text += f"⏳ Awaiting payment confirmation.\n\n"
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == 'Support')
def support(message):
    bot.send_message(message.chat.id, "💬 **Customer Support**\n\nFor any questions, please contact the admin:\n📱 Telegram: @xenslol", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == 'Back to Shop')
def back_to_shop(message):
    send_welcome(message)

@bot.message_handler(func=lambda message: message.text == 'View Orders')
def view_orders(message):
    if message.from_user.id not in ADMIN_IDS: return
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT pu.id, pu.username, p.name, p.description, pu.amount, pu.payment_status, pu.payment_id, pu.payment_method, pu.purchase_date FROM purchases pu JOIN products p ON pu.product_id = p.id ORDER BY pu.purchase_date DESC")
    orders = cursor.fetchall()
    conn.close()
    if not orders:
        bot.send_message(message.chat.id, "No orders found.")
        return
    pending_orders = [o for o in orders if o[5] == 'pending']
    completed_orders = [o for o in orders if o[5] == 'completed']
    if pending_orders:
        text = "⏳ **PENDING PAYMENTS**\n\n"
        markup = types.InlineKeyboardMarkup()
        for order in pending_orders:
            order_id, username, product_name, description, amount, _, payment_id, method, date = order
            preview = f" ({description[:6]}...)" if description else ""
            text += f"**Order #{order_id}**\n👤 User: @{username or 'Unknown'}\n"
            text += f"📄 Product: {product_name}{preview}\n💰 Amount: {format_price(amount)} ({method})\n"
            text += f"🆔 Payment ID: `{payment_id[:8]}`\n📅 {date.split('.')[0]}\n\n"
            markup.row(types.InlineKeyboardButton(f"✅ Confirm #{order_id}", callback_data=f"confirm_{payment_id}"))
        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "No pending orders found.")
    if completed_orders:
        text = "\n✅ **COMPLETED ORDERS (Last 10)**\n\n"
        total_revenue = sum(o[4] for o in completed_orders)
        for order in completed_orders[:10]:
            order_id, username, product_name, description, amount, _, _, _, date = order
            preview = f" ({description[:6]}...)" if description else ""
            text += f"**Order #{order_id}** - @{username or 'Unknown'}\n📄 {product_name}{preview} - {format_price(amount)}\n\n"
        text += f"💵 **Total Revenue:** {format_price(total_revenue)}"
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == '🧪 Test Mode')
def test_mode(message):
    if message.from_user.id not in ADMIN_IDS: return
    bot.send_message(message.chat.id, "Entering test mode...")

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    user_id = message.from_user.id
    text = message.text
    if isinstance(user_states.get(user_id), dict) and user_states[user_id].get('state') == 'waiting_price':
        try:
            price = float(text.strip())
            if price <= 0:
                bot.send_message(message.chat.id, "Price must be a positive number.")
                return
        except ValueError:
            bot.send_message(message.chat.id, "Invalid price format.")
            return
        product_data = user_states[user_id]
        try:
            add_product_to_db(name=product_data['product_name'], description=product_data['description'], price=price, file_path=product_data['file_path'], file_name=product_data['file_name'])
            bot.send_message(message.chat.id, "✅ **Product Added Successfully!**", parse_mode="Markdown")
            user_states.pop(user_id, None)
            admin_panel(message)
        except Exception as e:
            debug_print(f"Product creation error: {str(e)}")
            bot.send_message(message.chat.id, "Failed to create the product.")
    else:
        bot.send_message(message.chat.id, "I don't understand that. Please use the menu buttons.")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    debug_print(f"Callback received: {call.data}")
    user_id = call.from_user.id
    username = call.from_user.username
    try:
        if call.data.startswith('product_'):
            product_id = int(call.data.split('_')[1])
            product = get_product(product_id)
            if not product:
                bot.edit_message_text("Product not found.", call.message.chat.id, call.message.message_id); return
            _, name, description, price, _, _, _, _ = product
            desc_preview = f"{description[:6]}..." if description and len(description) > 6 else (description or "No description.")
            product_text = f"📄 **{name}**\n\n💰 **Price:** {format_price(price)}\n📝 **Description:**\n{desc_preview}\n\nChoose your payment method:"
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("💳 CashApp", callback_data=f"buy_cashapp_{product_id}"), types.InlineKeyboardButton("₿ Crypto", callback_data=f"buy_crypto_{product_id}"))
            markup.row(types.InlineKeyboardButton("🔙 Back to Products", callback_data="back_products"))
            bot.edit_message_text(product_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

        elif call.data.startswith('buy_'):
            parts = call.data.split('_')
            payment_method, product_id = parts[1], int(parts[2])
            product = get_product(product_id)
            if not product:
                bot.answer_callback_query(call.id, "Product not found"); return
            price = product[3]
            balance = get_user_balance(user_id)
            if balance >= price:
                markup = types.InlineKeyboardMarkup()
                markup.row(types.InlineKeyboardButton(f"Pay with Balance ({format_price(balance)})", callback_data=f"pay_balance_{product_id}"))
                markup.row(types.InlineKeyboardButton("Pay with CashApp/Crypto instead", callback_data=f"pay_external_{payment_method}_{product_id}"))
                markup.row(types.InlineKeyboardButton("Cancel", callback_data="back_products"))
                bot.edit_message_text("You have enough funds to buy this item.\n\nHow would you like to pay?", call.message.chat.id, call.message.message_id, reply_markup=markup)
            else:
                show_external_payment_info(call, payment_method, product_id)

        elif call.data.startswith('pay_balance_'):
            product_id = int(call.data.split('_')[2])
            product = get_product(product_id)
            if not product:
                bot.answer_callback_query(call.id, "Product not found."); return
            price = product[3]
            balance = get_user_balance(user_id)
            if balance >= price:
                update_user_balance(user_id, -price)
                new_balance = get_user_balance(user_id)
                payment_id, access_token, _ = create_purchase(user_id, username, product_id, 'balance', price)
                confirm_payment(payment_id)
                deactivate_product_in_db(product_id) # Deactivate product after sale
                success_text = f"✅ Purchase Successful!\n\nYour new balance is {format_price(new_balance)}.\n\nHere is your download:"
                bot.edit_message_text(success_text, call.message.chat.id, call.message.message_id, reply_markup=None)
                handle_download_callback(call, access_token)
            else:
                bot.edit_message_text("Your balance is no longer sufficient for this purchase.", call.message.chat.id, call.message.message_id, reply_markup=None)

        elif call.data.startswith('pay_external_'):
            parts = call.data.split('_')
            payment_method, product_id = parts[2], int(parts[3])
            show_external_payment_info(call, payment_method, product_id)

        elif call.data.startswith('remove_'):
            if user_id not in ADMIN_IDS: return
            product_id = int(call.data.split('_')[1])
            if deactivate_product_in_db(product_id):
                bot.answer_callback_query(call.id, "Product removed successfully.")
                bot.edit_message_text("✅ Product has been removed.", call.message.chat.id, call.message.message_id, reply_markup=None)
            else:
                bot.answer_callback_query(call.id, "Error: Could not remove product.")
        
        elif call.data.startswith('confirm_'):
            if user_id not in ADMIN_IDS: return
            payment_id = call.data.replace('confirm_', '')
            purchase = get_purchase_by_payment_id(payment_id)
            if not purchase:
                bot.answer_callback_query(call.id, "Purchase not found.")
                return
            
            _, customer_user_id, product_id_to_deactivate, _, access_token, product_name = purchase

            if confirm_payment(payment_id):
                deactivate_product_in_db(product_id_to_deactivate) # Deactivate product after sale
                bot.answer_callback_query(call.id, "✅ Payment confirmed and product removed from shop!")
                bot.edit_message_text(f"✅ Payment confirmed for order of '{product_name}'.", call.message.chat.id, call.message.message_id, reply_markup=None)
                try:
                    markup = types.InlineKeyboardMarkup()
                    markup.row(types.InlineKeyboardButton("📥 Download Now", callback_data=f"download_{access_token}"))
                    bot.send_message(customer_user_id, f"🎉 Your payment for **{product_name}** has been confirmed!\n\nYou can now download your file.", reply_markup=markup, parse_mode="Markdown")
                except Exception as e:
                    debug_print(f"Failed to notify customer {customer_user_id}: {e}")
            else:
                 bot.answer_callback_query(call.id, "❌ Failed to confirm payment.")

        elif call.data.startswith('download_'):
            access_token = call.data.replace('download_', '')
            handle_download_callback(call, access_token)
            
        elif call.data == "back_products":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            browse_products(call.message)
        elif call.data == "back_admin":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            admin_panel(call.message)
            
        bot.answer_callback_query(call.id)
    except Exception as e:
        debug_print(f"Callback error: {str(e)}")
        bot.answer_callback_query(call.id, "An error occurred.")

def show_external_payment_info(call, payment_method, product_id):
    product = get_product(product_id)
    if not product:
        bot.answer_callback_query(call.id, "Product not found"); return
    payment_id, _, _ = create_purchase(call.from_user.id, call.from_user.username, product_id, payment_method, product[3])
    payment_text = f"**💳 Payment Required**\n\n📄 **Product:** {product[1]}\n💰 **Amount:** {format_price(product[3])}\n\n"
    if payment_method == 'cashapp':
        payment_text += f"Send payment to `$shonwithcash`\nIn the 'For' / 'Note' section, you **MUST** include this ID:\n`{payment_id[:8]}`"
    else: # crypto
        payment_text += "**Send the exact amount to one of the addresses below.**\n\n" \
                        "🟡 **Bitcoin (BTC):**\n`bc1q9nc2clammklw8jtvmzfqxg4e9exlcc7ww7e64e`\n\n" \
                        "🔵 **Litecoin (LTC):**\n`LZXDSYuxo2XZroFMgdQPRxfi2vjV3ncq3r`\n\n" \
                        "🟣 **Ethereum (ETH):**\n`0xf812b0466ea671B3FadC75E9624dFeFd507F22C8`\n\n" \
                        f"After sending, an admin will confirm your payment. Your Order ID is `{payment_id[:8]}`."
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔙 Back to Products", callback_data="back_products"))
    bot.edit_message_text(payment_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

def handle_download_callback(call, access_token):
    file_info = get_file_by_token(access_token)
    if not file_info:
        bot.send_message(call.message.chat.id, "File not found or your payment is not yet confirmed."); return
    file_path, file_name = file_info
    try:
        with open(file_path, 'rb') as f:
            bot.send_document(call.message.chat.id, f, caption=f"Thank you for your purchase!\n\n📁 {file_name}")
    except Exception as e:
        debug_print(f"Download error: {str(e)}")
        bot.send_message(call.message.chat.id, "Failed to send the file. Please contact support.")

def handle_download(message, access_token):
    file_info = get_file_by_token(access_token)
    if not file_info:
        bot.send_message(message.chat.id, "File not found or your payment is not yet confirmed."); return
    file_path, file_name = file_info
    try:
        with open(file_path, 'rb') as f:
            bot.send_document(message.chat.id, f, caption=f"Thank you for your purchase!\n\n📁 {file_name}")
    except Exception as e:
        debug_print(f"Download error: {str(e)}")
        bot.send_message(message.chat.id, "Failed to send the file. Please contact support.")

if __name__ == "__main__":
    init_database()
    debug_print("Bot starting up...")
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        debug_print(f"An error occurred in the polling loop: {e}")
