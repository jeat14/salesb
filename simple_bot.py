import telebot
from telebot import types
import os
import sqlite3
import uuid
import json
from datetime import datetime

# Initialize bot with your token
TOKEN = '8060770660:AAHh2Y1YH0GR2F6hIhC3Ip3r5RIN1xtcgcE'
bot = telebot.TeleBot(TOKEN)

# Admin user IDs
ADMIN_IDS = [7481885595]  # @packoa's ID

# Debug mode
DEBUG = True

# File storage
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Database setup
def init_database():
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    
    # Products table
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
    
    # Purchases table
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

# User states for multi-step processes
user_states = {}

def debug_print(message):
    if DEBUG:
        print(f"DEBUG: {message}")

def format_price(price):
    return f"${price:.2f}"

def save_file(file_content, original_filename):
    """Save uploaded file"""
    file_ext = os.path.splitext(original_filename)[1].lower()
    if file_ext not in ['.txt', '.pdf', '.doc', '.docx']:
        return None, "Only .txt, .pdf, .doc, .docx files allowed"
    
    secure_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(UPLOAD_FOLDER, secure_filename)
    
    with open(file_path, 'wb') as f:
        f.write(file_content)
    
    return file_path, None

def add_product_to_db(name, description, price, file_path, file_name):
    """Add product to database"""
    conn = sqlite3.connect('shop.db')
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
    """Get all active products"""
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE active = 1 ORDER BY created_at DESC')
    products = cursor.fetchall()
    conn.close()
    return products

def get_product(product_id):
    """Get specific product"""
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    conn.close()
    return product

def create_purchase(user_id, username, product_id, payment_method, amount):
    """Create purchase with pending status and return payment ID"""
    payment_id = str(uuid.uuid4())
    access_token = str(uuid.uuid4())
    conn = sqlite3.connect('shop.db')
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
    """Confirm payment and update status"""
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE purchases 
        SET payment_status = 'completed'
        WHERE payment_id = ?
    ''', (payment_id,))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0

def get_purchase_by_payment_id(payment_id):
    """Get purchase details by payment ID"""
    conn = sqlite3.connect('shop.db')
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
    """Get file path by access token - only if payment is completed"""
    conn = sqlite3.connect('shop.db')
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

# Start command handler
@bot.message_handler(commands=['start'])
def send_welcome(message):
    debug_print(f"Start command from user {message.from_user.id}")
    
    # Check if downloading file
    if len(message.text.split()) > 1:
        token = message.text.split()[1]
        if token.startswith('download_'):
            handle_download(message, token.replace('download_', ''))
            return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('Browse Products', 'My Purchases')
    markup.row('Support')
    
    # Add admin button if user is admin
    if message.from_user.id in ADMIN_IDS:
        markup.row('Admin Panel')
    
    bot.reply_to(message, 
                 f"Welcome to the Digital Shop, {message.from_user.first_name}!\n\n"
                 "Browse products and buy instantly with CashApp or Crypto!",
                 reply_markup=markup)

# Admin Panel
@bot.message_handler(func=lambda message: message.text == 'Admin Panel')
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "Access denied.")
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('Add Product', 'View Orders')
    markup.row('🧪 Test Mode', 'Back to Shop')
    
    user_states[message.from_user.id] = None  # Clear any existing state
    
    bot.send_message(message.chat.id, 
                     "Admin Panel\n\nSelect an option:",
                     reply_markup=markup)

# Add Product
@bot.message_handler(func=lambda message: message.text == 'Add Product')
def add_product(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user_states[message.from_user.id] = 'waiting_file'
    
    bot.send_message(message.chat.id,
                     "Upload a .txt file to sell.\n\n"
                     "Supported formats: .txt, .pdf, .doc, .docx")

# Browse Products
@bot.message_handler(func=lambda message: message.text == 'Browse Products')
def browse_products(message):
    products = get_products()
    
    if not products:
        bot.send_message(message.chat.id, "No products available.")
        return
    
    markup = types.InlineKeyboardMarkup()
    
    for product in products:
        product_id, name, description, price, file_path, file_name, created_at, active = product
        button_text = f"{name} - {format_price(price)}"
        markup.row(types.InlineKeyboardButton(button_text, callback_data=f"product_{product_id}"))
    
    bot.send_message(message.chat.id, "Available Products:", reply_markup=markup)

# My Purchases
@bot.message_handler(func=lambda message: message.text == 'My Purchases')
def my_purchases(message):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.name, pu.amount, pu.purchase_date, pu.access_token, p.file_name, pu.payment_status, pu.payment_id
        FROM purchases pu
        JOIN products p ON pu.product_id = p.id
        WHERE pu.user_id = ?
        ORDER BY pu.purchase_date DESC
    ''', (message.from_user.id,))
    purchases = cursor.fetchall()
    conn.close()
    
    if not purchases:
        bot.send_message(message.chat.id, "No purchases found.")
        return
    
    text = "📋 Your Purchases:\n\n"
    markup = types.InlineKeyboardMarkup()
    
    for purchase in purchases:
        name, amount, date, token, filename, payment_status, payment_id = purchase
        
        status_emoji = {
            'pending': '⏳',
            'completed': '✅'
        }
        
        text += f"📄 {name}\n"
        text += f"💰 {format_price(amount)}\n"
        text += f"💳 Status: {status_emoji.get(payment_status, '❓')} {payment_status.title()}\n"
        text += f"📅 {date}\n"
        
        if payment_status == 'completed':
            markup.row(types.InlineKeyboardButton(f"📥 Download {name[:20]}", callback_data=f"download_{token}"))
            text += "✅ Ready for download\n\n"
        else:
            text += f"⏳ Awaiting payment confirmation\n"
            text += f"Order ID: {payment_id[:8]}\n\n"
    
    bot.send_message(message.chat.id, text, reply_markup=markup)

# Support
@bot.message_handler(func=lambda message: message.text == 'Support')
def support(message):
    bot.send_message(message.chat.id,
                     "💬 Customer Support\n\n"
                     "📱 Telegram: @xenslol\n"
                     "⏰ Available for assistance\n\n"
                     "For any questions or issues, contact the admin above.")

# Back to Shop
@bot.message_handler(func=lambda message: message.text == 'Back to Shop')
def back_to_shop(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('Browse Products', 'My Purchases')
    markup.row('Support')
    
    if message.from_user.id in ADMIN_IDS:
        markup.row('Admin Panel')
    
    bot.send_message(message.chat.id, "Back to main menu", reply_markup=markup)

# View Orders (Admin)
@bot.message_handler(func=lambda message: message.text == 'View Orders')
def view_orders(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pu.id, pu.username, p.name, pu.amount, pu.payment_status, pu.payment_id, pu.payment_method, pu.purchase_date
        FROM purchases pu
        JOIN products p ON pu.product_id = p.id
        ORDER BY pu.purchase_date DESC
    ''')
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        bot.send_message(message.chat.id, "No orders found.")
        return
    
    # Show pending orders first
    pending_orders = [o for o in orders if o[4] == 'pending']
    completed_orders = [o for o in orders if o[4] == 'completed']
    
    text = "📊 Orders Overview\n\n"
    
    if pending_orders:
        text += "⏳ PENDING PAYMENTS:\n\n"
        markup = types.InlineKeyboardMarkup()
        
        for order in pending_orders:
            order_id, username, product_name, amount, status, payment_id, method, date = order
            text += f"#{order_id} - {username or 'Unknown'}\n"
            text += f"📄 {product_name}\n"
            text += f"💰 {format_price(amount)} ({method})\n"
            text += f"🆔 Payment ID: {payment_id[:8]}\n"
            text += f"📅 {date}\n\n"
            
            markup.row(types.InlineKeyboardButton(f"✅ Confirm #{order_id}", callback_data=f"confirm_{payment_id}"))
        
        bot.send_message(message.chat.id, text, reply_markup=markup)
    
    if completed_orders:
        text = "\n✅ COMPLETED ORDERS:\n\n"
        total = 0
        
        for order in completed_orders[:10]:  # Show last 10 completed
            order_id, username, product_name, amount, status, payment_id, method, date = order
            total += amount
            text += f"#{order_id} - {username or 'Unknown'}\n"
            text += f"📄 {product_name}\n"
            text += f"💰 {format_price(amount)} ({method})\n"
            text += f"📅 {date}\n\n"
        
        text += f"💵 Total Revenue: {format_price(total)}"
        bot.send_message(message.chat.id, text)
    
    if not pending_orders and not completed_orders:
        bot.send_message(message.chat.id, "No orders found.")

# Test Mode (Admin)
@bot.message_handler(func=lambda message: message.text == '🧪 Test Mode')
def test_mode(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    products = get_products()
    
    if not products:
        bot.send_message(message.chat.id, "❌ No products available. Add a product first.")
        return
    
    markup = types.InlineKeyboardMarkup()
    
    text = "🧪 Test Mode - Create Test Purchase\n\n"
    text += "Select a product to create a test purchase for @packoa:\n\n"
    
    for product in products:
        product_id, name, description, price, file_path, file_name, created_at, active = product
        button_text = f"Test: {name} - {format_price(price)}"
        markup.row(types.InlineKeyboardButton(button_text, callback_data=f"test_{product_id}"))
    
    markup.row(types.InlineKeyboardButton("🔙 Back to Admin", callback_data="back_admin"))
    
    bot.send_message(message.chat.id, text, reply_markup=markup)

# File upload handler
@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "Only admins can upload files.")
        return
    
    if user_states.get(message.from_user.id) != 'waiting_file':
        bot.send_message(message.chat.id, "Use 'Add Product' first.")
        return
    
    try:
        file_info = bot.get_file(message.document.file_id)
        if file_info.file_path:
            file_content = bot.download_file(file_info.file_path)
        else:
            bot.send_message(message.chat.id, "Could not get file information.")
            return
        
        file_path, error = save_file(file_content, message.document.file_name)
        
        if error:
            bot.send_message(message.chat.id, f"Error: {error}")
            return
        
        # Store file info and wait for product details
        user_states[message.from_user.id] = {
            'state': 'waiting_product_info',
            'file_path': file_path,
            'file_name': message.document.file_name
        }
        
        bot.send_message(message.chat.id,
                         f"File uploaded: {message.document.file_name}\n\n"
                         "Now send product info:\n"
                         "Name | Price | Description\n\n"
                         "Example:\n"
                         "Python Guide | 19.99 | Complete tutorial")
        
    except Exception as e:
        debug_print(f"File upload error: {str(e)}")
        bot.send_message(message.chat.id, "Upload failed. Try again.")
        user_states.pop(message.from_user.id, None)

# Text message handler
@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    user_id = message.from_user.id
    text = message.text
    
    # Handle product info entry
    if isinstance(user_states.get(user_id), dict) and user_states[user_id].get('state') == 'waiting_product_info':
        parts = text.split('|')
        
        if len(parts) != 3:
            bot.send_message(message.chat.id, "Invalid format. Use:\nName | Price | Description")
            return
        
        name = parts[0].strip()
        price_str = parts[1].strip()
        description = parts[2].strip()
        
        try:
            price = float(price_str)
            if price <= 0:
                bot.send_message(message.chat.id, "Price must be positive")
                return
        except ValueError:
            bot.send_message(message.chat.id, "Invalid price format")
            return
        
        try:
            product_id = add_product_to_db(
                name=name,
                description=description,
                price=price,
                file_path=user_states[user_id]['file_path'],
                file_name=user_states[user_id]['file_name']
            )
            
            bot.send_message(message.chat.id,
                             f"✅ Product added!\n\n"
                             f"📄 {name}\n"
                             f"💰 {format_price(price)}\n"
                             f"📝 {description}\n"
                             f"📁 {user_states[user_id]['file_name']}")
            
            user_states.pop(user_id, None)
            
        except Exception as e:
            debug_print(f"Product creation error: {str(e)}")
            bot.send_message(message.chat.id, "Failed to create product. Try again.")
    
    else:
        bot.send_message(message.chat.id, "Use the menu buttons or commands.")

# Callback query handler
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    debug_print(f"Callback: {call.data}")
    
    try:
        if call.data.startswith('product_'):
            product_id = int(call.data.split('_')[1])
            product = get_product(product_id)
            
            if not product:
                bot.edit_message_text("Product not found.", call.message.chat.id, call.message.message_id)
                return
            
            name, description, price = product[1], product[2], product[3]
            
            product_text = f"📄 {name}\n\n💰 Price: {format_price(price)}\n📝 {description or 'No description'}\n\nChoose payment method:"
            
            markup = types.InlineKeyboardMarkup()
            markup.row(
                types.InlineKeyboardButton("💳 CashApp", callback_data=f"buy_cashapp_{product_id}"),
                types.InlineKeyboardButton("₿ Crypto", callback_data=f"buy_crypto_{product_id}")
            )
            markup.row(types.InlineKeyboardButton("🔙 Back", callback_data="back_products"))
            
            bot.edit_message_text(product_text, call.message.chat.id, call.message.message_id, reply_markup=markup)
        
        elif call.data.startswith('buy_'):
            parts = call.data.split('_')
            payment_method = parts[1]  # cashapp or crypto
            product_id = int(parts[2])
            
            product = get_product(product_id)
            if not product:
                bot.answer_callback_query(call.id, "Product not found")
                return
            
            # Create purchase with pending status
            payment_id, access_token, purchase_id = create_purchase(
                user_id=call.from_user.id,
                username=call.from_user.username,
                product_id=product_id,
                payment_method=payment_method,
                amount=product[3]
            )
            
            # Send payment instructions without download link
            payment_text = f"💳 Payment Required\n\n"
            payment_text += f"📄 Product: {product[1]}\n"
            payment_text += f"💰 Amount: {format_price(product[3])}\n"
            payment_text += f"💳 Method: {payment_method.title()}\n\n"
            
            if payment_method == 'cashapp':
                payment_text += "💳 CashApp Payment Instructions:\n"
                payment_text += "1. Send payment to: $shonwithcash\n"
                payment_text += f"2. Amount: {format_price(product[3])}\n"
                payment_text += f"3. Note: {payment_id[:8]}\n\n"
                payment_text += "⚠️ IMPORTANT: Include the note exactly as shown above!\n\n"
            else:
                payment_text += "₿ Crypto Payment Options:\n\n"
                payment_text += f"💰 Amount: {format_price(product[3])}\n"
                payment_text += f"📋 Payment ID: {payment_id[:8]}\n\n"
                payment_text += "Choose your preferred crypto:\n\n"
                payment_text += "🟡 **Bitcoin (BTC):**\n"
                payment_text += "`bc1q9nc2clammklw8jtvmzfqxg4e9exlcc7ww7e64e`\n\n"
                payment_text += "🔵 **Litecoin (LTC):**\n"
                payment_text += "`LZXDSYuxo2XZroFMgdQPRxfi2vjV3ncq3r`\n\n"
                payment_text += "🟣 **Ethereum (ETH):**\n"
                payment_text += "`0xf812b0466ea671B3FadC75E9624dFeFd507F22C8`\n\n"
                payment_text += "⚠️ Include Payment ID in transaction memo!\n\n"
            
            payment_text += "After payment, admin will confirm and you'll get download access.\n"
            payment_text += f"Order ID: {payment_id[:8]}"
            
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("🔙 Back to Products", callback_data="back_products"))
            
            bot.edit_message_text(payment_text, call.message.chat.id, call.message.message_id, reply_markup=markup)
        
        elif call.data.startswith('download_'):
            access_token = call.data.replace('download_', '')
            handle_download_callback(call, access_token)
        
        elif call.data.startswith('confirm_'):
            payment_id = call.data.replace('confirm_', '')
            handle_payment_confirmation(call, payment_id)
        
        elif call.data.startswith('test_'):
            product_id = int(call.data.replace('test_', ''))
            handle_test_purchase(call, product_id)
        
        elif call.data == "back_admin":
            admin_panel(call.message)
        
        elif call.data == "back_products":
            browse_products(call.message)
        
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        debug_print(f"Callback error: {str(e)}")
        bot.answer_callback_query(call.id, "Error occurred")

def handle_download_callback(call, access_token):
    """Handle download via callback"""
    file_info = get_file_by_token(access_token)
    
    if not file_info:
        bot.answer_callback_query(call.id, "File not found or access denied")
        return
    
    file_path, file_name = file_info
    
    try:
        with open(file_path, 'rb') as f:
            bot.send_document(call.message.chat.id, f, caption=f"📁 {file_name}")
        bot.answer_callback_query(call.id, "File sent!")
    except Exception as e:
        debug_print(f"Download error: {str(e)}")
        bot.answer_callback_query(call.id, "Download failed")

def handle_test_purchase(call, product_id):
    """Handle test purchase creation for @packoa"""
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "Access denied")
        return
    
    product = get_product(product_id)
    if not product:
        bot.answer_callback_query(call.id, "Product not found")
        return
    
    # Create a completed test purchase for @packoa (user_id: 7481885595)
    test_user_id = 7481885595
    test_username = "packoa"
    
    payment_id, access_token, purchase_id = create_purchase(
        user_id=test_user_id,
        username=test_username,
        product_id=product_id,
        payment_method="test",
        amount=product[3]
    )
    
    # Immediately confirm the test payment
    confirm_payment(payment_id)
    
    # Notify admin
    bot.answer_callback_query(call.id, "✅ Test purchase created!")
    
    # Send notification to @packoa
    try:
        notification_text = f"🧪 Test Purchase Created!\n\n"
        notification_text += f"📄 Product: {product[1]}\n"
        notification_text += f"💰 Amount: {format_price(product[3])}\n"
        notification_text += f"✅ Ready for download (test mode)\n"
        notification_text += f"📋 Order ID: {payment_id[:8]}"
        
        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("📥 Download Test File", callback_data=f"download_{access_token}"))
        
        bot.send_message(test_user_id, notification_text, reply_markup=markup)
        
        # Update admin message
        updated_text = f"✅ Test purchase created for @packoa:\n\n"
        updated_text += f"📄 {product[1]}\n"
        updated_text += f"💰 {format_price(product[3])}\n"
        updated_text += f"📋 Order ID: {payment_id[:8]}\n"
        updated_text += f"👤 User: @{test_username} (ID: {test_user_id})"
        
        bot.edit_message_text(updated_text, call.message.chat.id, call.message.message_id)
        
    except Exception as e:
        debug_print(f"Failed to notify test user: {str(e)}")
        bot.answer_callback_query(call.id, "Test purchase created but notification failed")

def handle_payment_confirmation(call, payment_id):
    """Handle admin payment confirmation"""
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "Access denied")
        return
    
    purchase = get_purchase_by_payment_id(payment_id)
    if not purchase:
        bot.answer_callback_query(call.id, "Purchase not found")
        return
    
    purchase_id, user_id, payment_status, access_token, product_name, file_name = purchase
    
    if payment_status == 'completed':
        bot.answer_callback_query(call.id, "Already confirmed")
        return
    
    # Confirm the payment
    if confirm_payment(payment_id):
        bot.answer_callback_query(call.id, "✅ Payment confirmed!")
        
        # Notify the customer
        try:
            notification_text = f"🎉 Payment Confirmed!\n\n"
            notification_text += f"📄 {product_name}\n"
            notification_text += f"✅ Your file is now ready for download!"
            
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("📥 Download Now", callback_data=f"download_{access_token}"))
            
            bot.send_message(user_id, notification_text, reply_markup=markup)
            
        except Exception as e:
            debug_print(f"Failed to notify customer: {str(e)}")
        
        # Update the admin message
        try:
            updated_text = f"✅ Payment confirmed for:\n"
            updated_text += f"📄 {product_name}\n"
            updated_text += f"👤 User ID: {user_id}\n"
            updated_text += f"💰 Payment ID: {payment_id[:8]}"
            
            bot.edit_message_text(updated_text, call.message.chat.id, call.message.message_id)
        except:
            pass
    else:
        bot.answer_callback_query(call.id, "❌ Failed to confirm payment")

def handle_download(message, access_token):
    """Handle download via start command"""
    file_info = get_file_by_token(access_token)
    
    if not file_info:
        bot.send_message(message.chat.id, "File not found or payment not confirmed yet")
        return
    
    file_path, file_name = file_info
    
    try:
        with open(file_path, 'rb') as f:
            bot.send_document(message.chat.id, f, caption=f"📁 {file_name}")
    except Exception as e:
        debug_print(f"Download error: {str(e)}")
        bot.send_message(message.chat.id, "Download failed")

if __name__ == "__main__":
    init_database()
    debug_print("Bot starting...")
    bot.infinity_polling()
