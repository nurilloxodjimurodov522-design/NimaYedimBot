import os
import csv
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
from openai import OpenAI

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
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Setup OpenAI (NEW VERSION)
client = OpenAI(api_key=OPENAI_API_KEY)

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

# Bot commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Salom! Men kaloriya hisoblovchi botman.\n\n"
        "📝 Buyruqlar:\n"
        "/add ism familya vazn maqsad - Yangi odam qo'shish\n"
        "/calorie <ovqat> - Kaloriya hisoblash\n"
        "/list - Ro'yxat\n"
        "/delete <id> - O'chirish"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Yordam:\n"
        "/add ism familya vazn maqsad\n"
        "/calorie ovqat nomi\n"
        "/list - Barcha odamlar\n"
        "/delete <id>"
    )

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

async def calculate_calorie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Ovqat nomini kiriting!")
        return
    
    food = ' '.join(context.args)
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Kaloriya hisoblovchi bot. Faqat raqam va kcal bilan javob bering."},
                {"role": "user", "content": f"{food} da nechta kaloriya bor?"}
            ]
        )
        calorie = response.choices[0].message.content.strip()
        await update.message.reply_text(f"🍽️ {food}\n🔥 {calorie}")
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {str(e)}")

async def list_people(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = read_csv()
    if not data:
        await update.message.reply_text("📋 Hozircha hech kim yo'q")
        return
    
    message = "📋 Barcha odamlar:\n\n"
    for person in data:
        message += f"🆔 {person['id']} - {person['ism']} {person['familya']}, {person['vazn']}kg\n"
        message += f"   Maqsad: {person['maqsad']}\n\n"
    
    await update.message.reply_text(message)

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

def main():
    init_csv()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_person))
    application.add_handler(CommandHandler("calorie", calculate_calorie))
    application.add_handler(CommandHandler("list", list_people))
    application.add_handler(CommandHandler("delete", delete_person))
    
    logger.info("✅ Bot ishga tushdi...")
    application.run_polling()

if __name__ == '__main__':
    main()
