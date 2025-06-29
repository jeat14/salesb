import telebot
from telebot import types
import os
import sqlite3
import uuid
from datetime import datetime

# --- CONFIGURATION ---
# Replace with your real bot token
TOKEN = '8108658761:AAE_2O5d8zstSITUiMoN9jBK2oyGRRg7QX8'
# Add the Telegram User IDs of all admins
ADMIN_IDS = [
    7481885595,  # @packoa's ID
    # 789012345, # Example: Add another admin ID here
]

# --- INITIALIZATION ---
bot = telebot.TeleBot(TOKEN)
DEBUG = True
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# This dictionary will manage the different steps of a user's action
user_states = {}

# --- DATABASE FUNCTIONS ---

def init_database():
    """Initializes the database and creates tables if they don't exist."""
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            file_path TEXT NOT NULL,
            file_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active INTEGER DEFAULT 1
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            product_id INTEGER NOT NULL,
            payment_method TEXT NOT NULL,
            payment_status TEXT DEFAULT 'pending',
            payment_id TEXT,
            amount REAL NOT NULL,
            purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            access_token TEXT,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')
    conn.commit()
    conn.close()

def add_product_to_db(name, description, price, file_path, file_name):
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO products (name, description, price, file_path, file_name)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, description, price, file_path, file_name))
    conn.commit()
    product_id = cursor.lastrowid
    conn.close()
    return product_id

def get_products():
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE active = 1 ORDER BY created_at DESC')
    products = cursor.fetchall()
    conn.close()
    return products

def get_product(product_id):
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    conn.close()
    return product

def create_purchase(user_id, username, product_id, payment_method, amount):
    payment_id = str(uuid.uuid4())
    access_token = str(uuid.uuid4())
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO purchases (user_id, username, product_id, payment_method, amount, payment_id, access_token)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, product_id, payment_method, amount, payment_id, access_token))
    conn.commit()
    purchase_id = cursor.lastrowid
    conn.close()
    return payment_id, access_token, purchase_id

def confirm_payment(payment_id):
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE purchases SET payment_status = 'completed' WHERE payment_id = ?", (payment_id,))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0

def get_purchase_by_payment_id(payment_id):
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pu.id, pu.user_id, pu.payment_status, pu.access_token, p.name, p.file_name
        FROM purchases pu
        JOIN products p ON pu.product_id = p.id
        WHERE pu.payment_id = ?
    ''', (payment_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def get_file_by_token(access_token):
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.file_path, p.file_name
        FROM purchases pu
        JOIN products p ON pu.product_id = p.id
        WHERE pu.access_token = ? AND pu.payment_status = 'completed'
    ''', (access_token,))
    result = cursor.fetchone()
    conn.close()
    return result

# --- HELPER FUNCTIONS ---

def debug_print(message):
    if DEBUG:
        print(f"DEBUG: {message}")

def format_price(price):
    return f"${price:.2f}"

def save_file(file_content, original_filename):
    file_ext = os.path.splitext(original_filename)[1].lower()
    if file_ext != '.txt':
        return None, "Only .txt files are allowed for this simplified upload."
    secure_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(UPLOAD_FOLDER, secure_filename)
    with open(file_path, 'wb') as f:
        f.write(file_content)
    return file_path, None

# --- BOT MESSAGE HANDLERS ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    debug_print(f"Start command from user {message.from_user.id}")
    if len(message.text.split()) > 1:
        token = message.text.split()[1]
        if token.startswith('download_'):
            handle_download(message, token.replace('download_', ''))
            return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('Browse Products', 'My Purchases')
    markup.row('Support')
    if message.from_user.id in ADMIN_IDS:
        markup.row('Admin Panel')
    bot.reply_to(message, f"Welcome to the Shop, {message.from_user.first_name}!", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == 'Admin Panel')
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "Access denied.")
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('Add Product', 'View Orders')
    markup.row('🧪 Test Mode', 'Back to Shop')
    user_states.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "Admin Panel\n\nSelect an option:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == 'Add Product')
def add_product_start(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_states[message.from_user.id] = 'waiting_file'
    bot.send_message(message.chat.id, "Please upload the .txt file you want to sell.")

@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS or user_states.get(user_id) != 'waiting_file':
        return
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
        except Exception as e:
            debug_print(f"Could not decode file content: {e}")
            description = "Unable to read file content."
        user_states[user_id] = {
            'state': 'waiting_price',
            'file_path': file_path,
            'file_name': message.document.file_name,
            'product_name': product_name,
            'description': description
        }
        bot.send_message(message.chat.id,
                         f"📄 File `{message.document.file_name}` uploaded.\n"
                         f"The product name will be: `{product_name}`.\n\n"
                         f"**Now, please enter the price for this item.**",
                         parse_mode="Markdown")
    except Exception as e:
        debug_print(f"File upload error: {str(e)}")
        bot.send_message(message.chat.id, "An error occurred during file upload. Please try again.")
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
    cursor.execute('''
        SELECT p.name, p.description, pu.amount, pu.purchase_date, pu.access_token, pu.payment_status, pu.payment_id
        FROM purchases pu
        JOIN products p ON pu.product_id = p.id
        WHERE pu.user_id = ?
        ORDER BY pu.purchase_date DESC
    ''', (message.from_user.id,))
    purchases = cursor.fetchall()
    conn.close()
    if not purchases:
        bot.send_message(message.chat.id, "You have not made any purchases yet.")
        return
    text = "📋 **Your Purchase History**\n\n"
    markup = types.InlineKeyboardMarkup()
    status_emoji = {'pending': '⏳', 'completed': '✅'}
    for purchase in purchases:
        name, description, amount, date, token, payment_status, payment_id = purchase
        preview = f" ({description[:6]}...)" if description else ""
        text += f"📄 {name}{preview}\n"
        text += f"💰 {format_price(amount)}\n"
        text += f"💳 Status: {status_emoji.get(payment_status, '❓')} {payment_status.title()}\n"
        text += f"📅 {date.split('.')[0]}\n"
        if payment_status == 'completed':
            markup.row(types.InlineKeyboardButton(f"📥 Download {name[:20]}", callback_data=f"download_{token}"))
            text += "✅ Ready for download\n\n"
        else:
            text += f"⏳ Awaiting payment confirmation.\nOrder ID: `{payment_id[:8]}`\n\n"
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == 'Support')
def support(message):
    bot.send_message(message.chat.id,
                     "💬 **Customer Support**\n\nFor any questions or issues, please contact the admin:\n📱 Telegram: @xenslol",
                     parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == 'Back to Shop')
def back_to_shop(message):
    send_welcome(message)

@bot.message_handler(func=lambda message: message.text == 'View Orders')
def view_orders(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pu.id, pu.username, p.name, p.description, pu.amount, pu.payment_status, pu.payment_id, pu.payment_method, pu.purchase_date
        FROM purchases pu
        JOIN products p ON pu.product_id = p.id
        ORDER BY pu.purchase_date DESC
    ''')
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
            text += f"**Order #{order_id}**\n"
            text += f"👤 User: @{username or 'Unknown'}\n"
            text += f"📄 Product: {product_name}{preview}\n"
            text += f"💰 Amount: {format_price(amount)} ({method})\n"
            text += f"🆔 Payment ID: `{payment_id[:8]}`\n"
            text += f"📅 {date.split('.')[0]}\n\n"
            markup.row(types.InlineKeyboardButton(f"✅ Confirm #{order_id}", callback_data=f"confirm_{payment_id}"))
        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "No pending orders found.")
    if completed_orders:
        text = "\n✅ **COMPLETED ORDERS (Last 10)**\n\n"
        total_revenue = sum(o[4] for o in completed_orders)
        for order in completed_orders[:10]:
            order_id, username, product_name, description, amount, _, payment_id, method, date = order
            preview = f" ({description[:6]}...)" if description else ""
            text += f"**Order #{order_id}** - @{username or 'Unknown'}\n"
            text += f"📄 {product_name}{preview} - {format_price(amount)}\n\n"
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
                bot.send_message(message.chat.id, "Price must be a positive number. Please try again.")
                return
        except ValueError:
            bot.send_message(message.chat.id, "Invalid price format. Please send only a number (e.g., 10.99).")
            return
        product_data = user_states[user_id]
        try:
            add_product_to_db(
                name=product_data['product_name'], description=product_data['description'],
                price=price, file_path=product_data['file_path'], file_name=product_data['file_name']
            )
            bot.send_message(message.chat.id,
                             f"✅ **Product Added Successfully!**\n\n"
                             f"**Name:** {product_data['product_name']}\n"
                             f"**Price:** {format_price(price)}\n",
                             parse_mode="Markdown")
            user_states.pop(user_id, None)
            admin_panel(message)
        except Exception as e:
            debug_print(f"Product creation error: {str(e)}")
            bot.send_message(message.chat.id, "Failed to create the product. Please try again.")
    else:
        bot.send_message(message.chat.id, "I don't understand that. Please use the menu buttons.")

# --- CALLBACK QUERY HANDLER (UPDATED) ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    debug_print(f"Callback received: {call.data}")
    try:
        if call.data.startswith('product_'):
            product_id = int(call.data.split('_')[1])
            product = get_product(product_id)
            if not product:
                bot.edit_message_text("Product not found.", call.message.chat.id, call.message.message_id)
                return
            
            _, name, description, price, _, _, _, _ = product
            
            # --- THIS IS THE CORRECTED PART ---
            # Create a 6-digit preview for the description text
            desc_preview = f"{description[:6]}..." if description and len(description) > 6 else (description or "No description.")

            product_text = f"📄 **{name}**\n\n" \
                           f"💰 **Price:** {format_price(price)}\n" \
                           f"📝 **Description:**\n{desc_preview}\n\n" \
                           f"Choose your payment method:"

            markup = types.InlineKeyboardMarkup()
            markup.row(
                types.InlineKeyboardButton("💳 CashApp", callback_data=f"buy_cashapp_{product_id}"),
                types.InlineKeyboardButton("₿ Crypto", callback_data=f"buy_crypto_{product_id}")
            )
            markup.row(types.InlineKeyboardButton("🔙 Back to Products", callback_data="back_products"))
            bot.edit_message_text(product_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

        elif call.data.startswith('download_'):
            access_token = call.data.replace('download_', '')
            handle_download_callback(call, access_token)

        elif call.data.startswith('confirm_'):
             if call.from_user.id not in ADMIN_IDS:
                bot.answer_callback_query(call.id, "Access Denied.")
                return
             payment_id = call.data.replace('confirm_', '')
             bot.answer_callback_query(call.id, "Order confirmed!")

        elif call.data == "back_products":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            browse_products(call.message)
            
        bot.answer_callback_query(call.id)
    except Exception as e:
        debug_print(f"Callback error: {str(e)}")
        bot.answer_callback_query(call.id, "An error occurred.")

def handle_download_callback(call, access_token):
    file_info = get_file_by_token(access_token)
    if not file_info:
        bot.send_message(call.message.chat.id, "File not found or your payment is not yet confirmed.")
        return
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
        bot.send_message(message.chat.id, "File not found or your payment is not yet confirmed.")
        return
    file_path, file_name = file_info
    try:
        with open(file_path, 'rb') as f:
            bot.send_document(message.chat.id, f, caption=f"Thank you for your purchase!\n\n📁 {file_name}")
    except Exception as e:
        debug_print(f"Download error: {str(e)}")
        bot.send_message(message.chat.id, "Failed to send the file. Please contact support.")

# --- BOT EXECUTION ---
if __name__ == "__main__":
    init_database()
    debug_print("Bot starting up...")
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        debug_print(f"An error occurred in the polling loop: {e}")
