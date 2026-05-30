import os
import csv
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get tokens from environment
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Setup Google Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.5-flash')

# CSV File setup
CSV_FILE = 'data.csv'
FIELDNAMES = ['id', 'ism', 'familya', 'vazn', 'maqsad', 'kunlik_kaloriya']

def init_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
            writer.writeheader()

def read_csv():
    init_csv()
    data = []
    with open(CSV_FILE, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            data.append(row)
    return data

def write_csv(data_list):
    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(data_list)

def add_to_csv(ism, familya, vazn, maqsad):
    data = read_csv()
    next_id = len(data) + 1
    new_person = {
        'id': str(next_id),
        'ism': ism,
        'familya': familya,
        'vazn': vazn,
        'maqsad': maqsad,
        'kunlik_kaloriya': ''
    }
    data.append(new_person)
    write_csv(data)
    return next_id

# /start - Inline keyboard bilan
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ Yangi odam qo'shish", callback_data='add')],
        [InlineKeyboardButton("📋 Ro'yxatni ko'rish", callback_data='list')],
        [InlineKeyboardButton("🔥 Kaloriya hisoblash", callback_data='calorie')],
        [InlineKeyboardButton("🗑️ O'chirish", callback_data='delete')],
        [InlineKeyboardButton("📱 Mini App", web_app_url="https://nimayedimbot-production.up.railway.app")],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Salom! Men kaloriya hisoblovchi botman.\n\n"
        "Quyidagi tugmalardan birini tanlang:",
        reply_markup=reply_markup
    )

# Inline keyboard bosilganda
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'add':
        await query.message.reply_text(
            "➕ Yangi odam qo'shish uchun quyidagi formatda yozing:\n\n"
            "/add ism familya vazn maqsad\n\n"
            "Masalan:\n"
            "/add Ali Valiyev 70 yog'yo'qotish"
        )
    
    elif query.data == 'list':
        data = read_csv()
        if not data:
            await query.message.reply_text("📋 Hozircha hech kim yo'q")
            return
        
        message = "📋 Barcha odamlar:\n\n"
        for person in data:
            message += f"🆔 {person['id']} - {person['ism']} {person['familya']}, {person['vazn']}kg\n"
            message += f"   Maqsad: {person['maqsad']}\n\n"
        
        await query.message.reply_text(message)
    
    elif query.data == 'calorie':
        await query.message.reply_text(
            "🔥 Kaloriya hisoblash uchun ovqat nomini yozing:\n\n"
            "Masalan:\n"
            "non 2 bo'lak\n"
            "osh 1 porsiyasi\n"
            "olma 1 dona"
        )
    
    elif query.data == 'delete':
        await query.message.reply_text(
            "🗑️ O'chirish uchun ID ni yozing:\n\n"
            "Masalan:\n"
            "/delete 1"
        )

# Oddiy matnli xabarlar (kaloriya hisoblash uchun)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    # Agar bu buyruq bo'lmasa, kaloriya hisoblaymiz
    if not text.startswith('/'):
        try:
            food = text
            response = model.generate_content(f"{food} kaloriyasi nechta? Faqat raqam va kcal bilan javob bering.")
            calorie = response.text.strip()
            await update.message.reply_text(f"🍽️ {food}\n🔥 {calorie}")
        except Exception as e:
            await update.message.reply_text(f"❌ Xatolik: {str(e)}")

# /add buyrug'i
async def add_person(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 4:
        await update.message.reply_text("❌ Format: /add ism familya vazn maqsad")
        return
    
    ism, familya, vazn = args[0], args[1], args[2]
    maqsad = ' '.join(args[3:])
    
    try:
        next_id = add_to_csv(ism, familya, vazn, maqsad)
        await update.message.reply_text(f"✅ Qo'shildi!\nID: {next_id}\n{ism} {familya}, {vazn}kg")
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {str(e)}")

# /delete buyrug'i
async def delete_person(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ ID kiriting!")
        return
    
    delete_id = context.args[0]
    data = read_csv()
    new_data = [p for p in data if p['id'] != delete_id]
    
    if len(new_data) == len(data):
        await update.message.reply_text(f"❌ ID {delete_id} topilmadi")
        return
    
    write_csv(new_data)
    await update.message.reply_text(f"✅ ID {delete_id} o'chirildi")

# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ Yangi odam qo'shish", callback_data='add')],
        [InlineKeyboardButton("📋 Ro'yxatni ko'rish", callback_data='list')],
        [InlineKeyboardButton("🔥 Kaloriya hisoblash", callback_data='calorie')],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📖 Yordam:\n\n"
        "Quyidagi tugmalardan birini tanlang:",
        reply_markup=reply_markup
    )

def main():
    init_csv()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_person))
    application.add_handler(CommandHandler("delete", delete_person))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CallbackQueryHandler(lambda u, c: None, pattern='^(add|list|calorie|delete)$'))
    
    # Oddiy xabarlar (kaloriya uchun)
    application.add_handler(CallbackQueryHandler(lambda u, c: None))  # Bu barcha callbacklarni qayta ishlash uchun
    
    logger.info("✅ Bot ishga tushdi...")
    application.run_polling()

if __name__ == '__main__':
    main()
