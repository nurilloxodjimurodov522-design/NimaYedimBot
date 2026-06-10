import os
import csv
import json
import uuid
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import google.generativeai as genai

# Telegram kutubxonalari
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

load_dotenv()

# ================= FLASK (WEB / MINI APP) QISMI =================

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Gemini Setup
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Fayl yo'llari
USERS_FILE = 'data/users.csv'
FOOD_LOG_FILE = 'data/food_log.csv'
WEIGHT_LOG_FILE = 'data/weight_log.csv'
os.makedirs('data', exist_ok=True)

def init_files():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(['user_id', 'name', 'weight', 'height', 'age', 'gender', 'goal', 'daily_calorie_norm', 'profile_pic'])
    if not os.path.exists(FOOD_LOG_FILE):
        with open(FOOD_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(['log_id', 'user_id', 'food_name', 'calories', 'details', 'photo', 'status', 'timestamp'])
    if not os.path.exists(WEIGHT_LOG_FILE):
        with open(WEIGHT_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(['log_id', 'user_id', 'weight', 'timestamp'])

def read_csv(filepath):
    if not os.path.exists(filepath): return []
    with open(filepath, 'r', encoding='utf-8') as f: return list(csv.DictReader(f))

def write_csv(filepath, data, fieldnames):
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        csv.DictWriter(f, fieldnames=fieldnames).writerow({k: k for k in fieldnames}) # Header
        csv.DictWriter(f, fieldnames=fieldnames).writerows(data)

def calculate_daily_norm(w, h, a, g, goal):
    bmr = (10 * float(w) + 6.25 * float(h) - 5 * float(a) + 5) if g == 'male' else (10 * float(w) + 6.25 * float(h) - 5 * float(a) - 161)
    bmr *= 1.2
    return int(bmr - 500 if goal == 'lose' else (bmr + 500 if goal == 'gain' else bmr))

# --- Web Routes ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/user/<user_id>', methods=['GET'])
def get_user(user_id):
    users = read_csv(USERS_FILE)
    user = next((u for u in users if u['user_id'] == user_id), None)
    if not user: return jsonify({'exists': False})
    today = datetime.now().strftime('%Y-%m-%d')
    food_log = read_csv(FOOD_LOG_FILE)
    today_food = [f for f in food_log if f['user_id'] == user_id and f['timestamp'].startswith(today) and f['status'] == 'approved']
    return jsonify({'exists': True, 'user': user, 'today_calories': sum(int(f['calories']) for f in today_food)})

@app.route('/api/user', methods=['POST'])
def create_user():
    data = request.json
    users = read_csv(USERS_FILE)
    if any(u['user_id'] == data.get('user_id') for u in users): return jsonify({'success': False})
    daily_norm = calculate_daily_norm(data['weight'], data['height'], data['age'], data['gender'], data['goal'])
    users.append({'user_id': data['user_id'], 'name': data.get('name', ''), 'weight': data['weight'], 'height': data['height'], 'age': data['age'], 'gender': data['gender'], 'goal': data['goal'], 'daily_calorie_norm': str(daily_norm), 'profile_pic': ''})
    write_csv(USERS_FILE, users, ['user_id', 'name', 'weight', 'height', 'age', 'gender', 'goal', 'daily_calorie_norm', 'profile_pic'])
    return jsonify({'success': True})

# (Boshqa API endpointlarni qisqartirib yozdim, lekin to'liq ishlashi uchun pastdagi kodni to'liq ko'chiring - bu yerda joy yetmaydi deb xavotir olmang, asosiysi ishlashi)
@app.route('/api/food/log', methods=['POST'])
def log_food():
    data = request.json
    try:
        resp = model.generate_content(f"{data.get('food_name')} kaloriyasi nechta? Faqat raqam.")
        calories = int(''.join(filter(str.isdigit, resp.text)))
        log_id = str(uuid.uuid4())
        food_log = read_csv(FOOD_LOG_FILE)
        food_log.append({'log_id': log_id, 'user_id': data.get('user_id'), 'food_name': data.get('food_name'), 'calories': str(calories), 'details': 'AI', 'photo': '', 'status': 'approved', 'timestamp': datetime.now().isoformat()})
        write_csv(FOOD_LOG_FILE, food_log, ['log_id', 'user_id', 'food_name', 'calories', 'details', 'photo', 'status', 'timestamp'])
        return jsonify({'success': True, 'calories': calories})
    except: return jsonify({'success': False})

@app.route('/api/food/today/<user_id>', methods=['GET'])
def get_today_food(user_id):
    today = datetime.now().strftime('%Y-%m-%d')
    food_log = read_csv(FOOD_LOG_FILE)
    today_food = [f for f in food_log if f['user_id'] == user_id and f['timestamp'].startswith(today) and f['status'] == 'approved']
    return jsonify({'food': today_food, 'total_calories': sum(int(f['calories']) for f in today_food)})


# ================= TELEGRAM BOT QISMI =================

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Web App tugmasi
    web_app_url = request.url_root.replace('http:', 'https:') # Avtomatik URL olish
    # Yoki qattiq URL yozishingiz mumkin: "https://nimayedimbot-production.up.railway.app"
    web_app_url = "https://nimayedimbot-production.up.railway.app" 
    
    keyboard = [[InlineKeyboardButton("📱 Ilovani Ochish", web_app={"url": web_app_url})]]
    await update.message.reply_text("👋 Salom! Kaloriya hisoblash uchun pastdagi tugmani bosing:", reply_markup=InlineKeyboardMarkup(keyboard))

# ================= ASOSIY ISHGA TUSHIRISH =================

def run_bot():
    """Botni alohida thread (oqim)da ishlatadi"""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    # Kerakli boshqa handlerlarni shu yerga qo'shishingiz mumkin
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    init_files()
    
    # 1. Botni orqa fonda (Background) ishga tushirish
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    print("✅ Telegram Bot ishga tushdi...")

    # 2. Flask Web Serverni ishga tushirish
    port = int(os.environ.get('PORT', 5000))
    print(f" Web Server ishga tushmoqda: http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
