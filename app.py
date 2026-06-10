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
from telegram.ext import Application, CommandHandler, ContextTypes

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
    """CSV fayllarni tekshiradi va yo'q bo'lsa yaratadi"""
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['user_id', 'name', 'weight', 'height', 'age', 'gender', 'goal', 'daily_calorie_norm', 'profile_pic'])
    
    if not os.path.exists(FOOD_LOG_FILE):
        with open(FOOD_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['log_id', 'user_id', 'food_name', 'calories', 'details', 'photo', 'status', 'timestamp'])
            
    if not os.path.exists(WEIGHT_LOG_FILE):
        with open(WEIGHT_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['log_id', 'user_id', 'weight', 'timestamp'])

def read_csv(filepath):
    if not os.path.exists(filepath): 
        return []
    with open(filepath, 'r', encoding='utf-8') as f: 
        return list(csv.DictReader(f))

def write_csv(filepath, data, fieldnames):
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

def calculate_daily_norm(w, h, a, g, goal):
    try:
        w, h, a = float(w), float(h), float(a)
        bmr = (10 * w + 6.25 * h - 5 * a + 5) if g == 'male' else (10 * w + 6.25 * h - 5 * a - 161)
        bmr *= 1.2  # Faollik koeffitsienti
        if goal == 'lose': 
            bmr -= 500
        elif goal == 'gain': 
            bmr += 500
        return int(bmr)
    except: 
        return 2000

# ================= WEB ROUTES =================

@app.route('/')
def index(): 
    return render_template('index.html')

@app.route('/api/user/<user_id>', methods=['GET'])
def get_user(user_id):
    users = read_csv(USERS_FILE)
    user = next((u for u in users if u['user_id'] == user_id), None)
    if not user: 
        return jsonify({'exists': False})
    
    today = datetime.now().strftime('%Y-%m-%d')
    food_log = read_csv(FOOD_LOG_FILE)
    today_food = [f for f in food_log if f['user_id'] == user_id and f['timestamp'].startswith(today) and f['status'] == 'approved']
    total_cal = sum(int(f['calories']) for f in today_food)
    
    return jsonify({
        'exists': True, 
        'user': user, 
        'today_calories': total_cal, 
        'today_food_count': len(today_food)
    })

@app.route('/api/user', methods=['POST'])
def create_user():
    data = request.json
    users = read_csv(USERS_FILE)
    if any(u['user_id'] == data.get('user_id') for u in users): 
        return jsonify({'success': False, 'error': 'User exists'})
    
    daily_norm = calculate_daily_norm(data['weight'], data['height'], data['age'], data['gender'], data['goal'])
    users.append({
        'user_id': data['user_id'], 
        'name': data.get('name', ''), 
        'weight': data['weight'], 
        'height': data['height'], 
        'age': data['age'], 
        'gender': data['gender'], 
        'goal': data['goal'], 
        'daily_calorie_norm': str(daily_norm), 
        'profile_pic': ''
    })
    write_csv(USERS_FILE, users, ['user_id', 'name', 'weight', 'height', 'age', 'gender', 'goal', 'daily_calorie_norm', 'profile_pic'])
    return jsonify({'success': True, 'daily_norm': daily_norm})

@app.route('/api/food/log', methods=['POST'])
def log_food():
    data = request.json
    try:
        food_name = data.get('food_name')
        user_id = data.get('user_id')
        
        # Get calories from AI
        resp = model.generate_content(f"{food_name} kaloriyasi nechta? Faqat raqam yoz (masalan: 250).")
        calories = int(''.join(filter(str.isdigit, resp.text)))
        
        # Get details from AI
        details_resp = model.generate_content(f"{food_name} haqida qisqa ma'lumot va kaloriya manbai (o'zbekcha, 1 gap).")
        details = details_resp.text
        
        log_id = str(uuid.uuid4())
        food_log = read_csv(FOOD_LOG_FILE)
        food_log.append({
            'log_id': log_id, 
            'user_id': user_id, 
            'food_name': food_name, 
            'calories': str(calories), 
            'details': details, 
            'photo': '', 
            'status': 'approved', 
            'timestamp': datetime.now().isoformat()
        })
        write_csv(FOOD_LOG_FILE, food_log, ['log_id', 'user_id', 'food_name', 'calories', 'details', 'photo', 'status', 'timestamp'])
        return jsonify({'success': True, 'calories': calories, 'details': details})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/food/today/<user_id>', methods=['GET'])
def get_today_food(user_id):
    today = datetime.now().strftime('%Y-%m-%d')
    food_log = read_csv(FOOD_LOG_FILE)
    today_food = [f for f in food_log if f['user_id'] == user_id and f['timestamp'].startswith(today) and f['status'] == 'approved']
    total = sum(int(f['calories']) for f in today_food)
    return jsonify({'food': today_food, 'total_calories': total})

@app.route('/api/weight/log', methods=['POST'])
def log_weight():
    data = request.json
    weight_log = read_csv(WEIGHT_LOG_FILE)
    weight_log.append({
        'log_id': str(uuid.uuid4()), 
        'user_id': data.get('user_id'), 
        'weight': data.get('weight'), 
        'timestamp': datetime.now().isoformat()
    })
    write_csv(WEIGHT_LOG_FILE, weight_log, ['log_id', 'user_id', 'weight', 'timestamp'])
    return jsonify({'success': True})

@app.route('/api/weight/history/<user_id>', methods=['GET'])
def get_weight_history(user_id):
    weight_log = read_csv(WEIGHT_LOG_FILE)
    history = [w for w in weight_log if w['user_id'] == user_id]
    return jsonify(sorted(history, key=lambda k: k['timestamp'], reverse=True))

@app.route('/api/recommendations/<user_id>', methods=['GET'])
def get_recommendations(user_id):
    users = read_csv(USERS_FILE)
    user = next((u for u in users if u['user_id'] == user_id), None)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})
    
    today = datetime.now().strftime('%Y-%m-%d')
    food_log = read_csv(FOOD_LOG_FILE)
    today_food = [f for f in food_log if f['user_id'] == user_id and f['timestamp'].startswith(today) and f['status'] == 'approved']
    total_calories = sum(int(f['calories']) for f in today_food)
    daily_norm = int(user['daily_calorie_norm'])
    
    try:
        prompt = f"""
        Foydalanuvchi: {user['name']}, vazn: {user['weight']}kg, maqsad: {user['goal']}.
        Kunlik norma: {daily_norm} kcal, bugun yegan: {total_calories} kcal.
        Qisqa tavsiya bering (2-3 gap, o'zbek tilida).
        """
        response = model.generate_content(prompt)
        return jsonify({
            'success': True,
            'recommendation': response.text,
            'daily_norm': daily_norm,
            'consumed': total_calories,
            'remaining': daily_norm - total_calories
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ================= TELEGRAM BOT QISMI =================

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    web_app_url = "https://nimayedimbot-production.up.railway.app"  # O'z URL ingizni yozing
    keyboard = [[InlineKeyboardButton("📱 Ilovani Ochish", web_app={"url": web_app_url})]]
    await update.message.reply_text(
        "👋 Salom! Kaloriya hisoblash va profilingizni boshqarish uchun pastdagi tugmani bosing:", 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= ASOSIY ISHGA TUSHIRISH =================

def run_flask():
    """Flask serverni alohida thread da ishlatadi"""
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    init_files()
    
    # 1. Flask serverni ORQA FONDA ishga tushirish
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("✅ Flask server ishga tushdi!")
    
    # 2. Botni ASOSIY OQIMDA ishga tushirish (signal handler uchun muhim!)
    print("🤖 Telegram Bot ishga tushmoqda...")
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    # Botni polling rejimida ishga tushirish (asosiy oqimda)
    application.run_polling(drop_pending_updates=True)
