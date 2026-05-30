from flask import Flask, render_template, request, jsonify
import os
import csv
from dotenv import load_dotenv
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

load_dotenv()

app = Flask(__name__)

# Bot va Gemini sozlamalari
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

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

# ============ WEB PAGES ============

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/people', methods=['GET'])
def get_people():
    data = read_csv()
    return jsonify(data)

@app.route('/api/add', methods=['POST'])
def add_person():
    data = request.json
    people = read_csv()
    next_id = len(people) + 1
    
    new_person = {
        'id': str(next_id),
        'ism': data.get('ism'),
        'familya': data.get('familya'),
        'vazn': data.get('vazn'),
        'maqsad': data.get('maqsad'),
        'kunlik_kaloriya': ''
    }
    
    people.append(new_person)
    write_csv(people)
    return jsonify({'success': True, 'id': next_id})

@app.route('/api/delete/<id>', methods=['DELETE'])
def delete_person(id):
    people = read_csv()
    new_people = [p for p in people if p['id'] != id]
    write_csv(new_people)
    return jsonify({'success': True})

@app.route('/api/calorie', methods=['POST'])
def calculate_calorie():
    food = request.json.get('food')
    try:
        response = model.generate_content(f"{food} kaloriyasi nechta? Faqat raqam va kcal.")
        return jsonify({'success': True, 'calorie': response.text})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ============ TELEGRAM BOT ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Mini App tugmasi
    keyboard = [[
        InlineKeyboardButton("📊 Mini Appni ochish", web_app=WebAppInfo(url="https://sizning-app.railway.app"))
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Salom! Kaloriya botiga xush kelibsiz!\n\n"
        "Quyidagi tugmani bosib Mini Appni oching:",
        reply_markup=reply_markup
    )

async def webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Mini App dan kelgan ma'lumot
    data = update.message.web_app_data.data
    await update.message.reply_text(f"Ma'lumot qabul qilindi: {data}")

def main():
    init_csv()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(webapp_data, pattern='webapp'))
    
    application.run_polling()

if __name__ == '__main__':
    # Flask serverini ishga tushirish
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
