"""
NimaYedimBot - Professional Kaloriya Tracker
Features: AI, Multi-language, Water Tracker, Workouts, Reports, Admin Panel
Gemini 2.0 Flash AI
"""

import os
import csv
import json
import uuid
import logging
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
import google.generativeai as genai

# Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

# Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'secret-key-change-me')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Gemini AI
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)
try:
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
except:
    model = genai.GenerativeModel('gemini-1.5-flash')

logger.info("✅ Gemini AI initialized")

# Fayl yo'llari
DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)

USERS_FILE = f'{DATA_DIR}/users.csv'
FOOD_LOG_FILE = f'{DATA_DIR}/food_log.csv'
WEIGHT_LOG_FILE = f'{DATA_DIR}/weight_log.csv'
WATER_LOG_FILE = f'{DATA_DIR}/water_log.csv'
WORKOUT_FILE = f'{DATA_DIR}/workouts.csv'
BLOCKED_USERS_FILE = f'{DATA_DIR}/blocked_users.txt'

# Admin users
ADMIN_USERS = os.getenv('ADMIN_USERS', '').split(',')

# ================= CSV FUNKSIYALARI =================

def init_files():
    """Barcha CSV fayllarni yaratadi"""
    files_config = {
        USERS_FILE: ['user_id', 'name', 'weight', 'height', 'age', 'gender', 'goal', 'daily_calorie_norm', 'profile_pic', 'language', 'created_at'],
        FOOD_LOG_FILE: ['log_id', 'user_id', 'food_name', 'calories', 'details', 'photo', 'status', 'timestamp'],
        WEIGHT_LOG_FILE: ['log_id', 'user_id', 'weight', 'timestamp'],
        WATER_LOG_FILE: ['log_id', 'user_id', 'amount_ml', 'timestamp'],
        WORKOUT_FILE: ['log_id', 'user_id', 'workout_name', 'duration_min', 'calories_burned', 'timestamp']
    }
    
    for filepath, fieldnames in files_config.items():
        if not os.path.exists(filepath):
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
    
    logger.info("✅ All CSV files initialized")

def read_csv(filepath):
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return list(csv.DictReader(f))
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")
        return []

def write_csv(filepath, data, fieldnames):
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        return True
    except Exception as e:
        logger.error(f"Error writing {filepath}: {e}")
        return False

def calculate_daily_norm(weight, height, age, gender, goal):
    try:
        w, h, a = float(weight), float(height), float(age)
        bmr = (10 * w + 6.25 * h - 5 * a + 5) if gender == 'male' else (10 * w + 6.25 * h - 5 * a - 161)
        bmr *= 1.2
        if goal == 'lose': bmr -= 500
        elif goal == 'gain': bmr += 500
        return int(bmr)
    except:
        return 2000

def is_user_blocked(user_id):
    if not os.path.exists(BLOCKED_USERS_FILE):
        return False
    with open(BLOCKED_USERS_FILE, 'r') as f:
        return user_id in f.read().splitlines()

# ================= WEB ROUTES =================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin_panel():
    return render_template('admin.html')

@app.route('/api/user/<user_id>', methods=['GET'])
def get_user(user_id):
    if is_user_blocked(user_id):
        return jsonify({'blocked': True}), 403
    
    users = read_csv(USERS_FILE)
    user = next((u for u in users if u['user_id'] == user_id), None)
    
    if not user:
        return jsonify({'exists': False})
    
    today = datetime.now().strftime('%Y-%m-%d')
    food_log = read_csv(FOOD_LOG_FILE)
    today_food = [f for f in food_log if f['user_id'] == user_id and f['timestamp'].startswith(today)]
    total_calories = sum(int(f['calories']) for f in today_food)
    
    water_log = read_csv(WATER_LOG_FILE)
    today_water = [w for w in water_log if w['user_id'] == user_id and w['timestamp'].startswith(today)]
    total_water = sum(int(w['amount_ml']) for w in today_water)
    
    return jsonify({
        'exists': True,
        'user': user,
        'today_calories': total_calories,
        'today_water': total_water,
        'food_count': len(today_food)
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
        'profile_pic': '',
        'language': data.get('language', 'uz'),
        'created_at': datetime.now().isoformat()
    })
    
    if write_csv(USERS_FILE, users, ['user_id', 'name', 'weight', 'height', 'age', 'gender', 'goal', 'daily_calorie_norm', 'profile_pic', 'language', 'created_at']):
        return jsonify({'success': True, 'daily_norm': daily_norm})
    return jsonify({'success': False}), 500

@app.route('/api/user/<user_id>', methods=['PUT'])
def update_user(user_id):
    data = request.json
    users = read_csv(USERS_FILE)
    
    for i, user in enumerate(users):
        if user['user_id'] == user_id:
            for key in ['name', 'weight', 'height', 'age', 'gender', 'goal', 'language']:
                if key in data:
                    users[i][key] = data[key]
            
            if all(k in data for k in ['weight', 'height', 'age', 'gender', 'goal']):
                users[i]['daily_calorie_norm'] = str(calculate_daily_norm(data['weight'], data['height'], data['age'], data['gender'], data['goal']))
            
            if write_csv(USERS_FILE, users, ['user_id', 'name', 'weight', 'height', 'age', 'gender', 'goal', 'daily_calorie_norm', 'profile_pic', 'language', 'created_at']):
                return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'User not found'}), 404

@app.route('/api/food/log', methods=['POST'])
def log_food():
    data = request.json
    food_name = data.get('food_name')
    user_id = data.get('user_id')
    
    if not food_name or not user_id:
        return jsonify({'success': False, 'error': 'Missing fields'}), 400
    
    try:
        calorie_prompt = f"{food_name} kaloriyasi nechta? Faqat raqam yoz."
        calorie_resp = model.generate_content(calorie_prompt)
        calories = int(''.join(filter(str.isdigit, calorie_resp.text)) or '100')
        
        details_prompt = f"{food_name} haqida qisqa ma'lumot (1 gap)."
        details = model.generate_content(details_prompt).text.strip()
        
        food_log = read_csv(FOOD_LOG_FILE)
        food_log.append({
            'log_id': str(uuid.uuid4()),
            'user_id': user_id,
            'food_name': food_name,
            'calories': str(calories),
            'details': details,
            'photo': '',
            'status': 'approved',
            'timestamp': datetime.now().isoformat()
        })
        
        if write_csv(FOOD_LOG_FILE, food_log, ['log_id', 'user_id', 'food_name', 'calories', 'details', 'photo', 'status', 'timestamp']):
            return jsonify({'success': True, 'calories': calories, 'details': details})
    except Exception as e:
        logger.error(f"Food log error: {e}")
    
    return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/food/today/<user_id>', methods=['GET'])
def get_today_food(user_id):
    today = datetime.now().strftime('%Y-%m-%d')
    food_log = read_csv(FOOD_LOG_FILE)
    today_food = [f for f in food_log if f['user_id'] == user_id and f['timestamp'].startswith(today)]
    total = sum(int(f['calories']) for f in today_food)
    return jsonify({'food': today_food, 'total_calories': total})

@app.route('/api/food/history/<user_id>', methods=['GET'])
def get_food_history(user_id):
    food_log = read_csv(FOOD_LOG_FILE)
    history = [f for f in food_log if f['user_id'] == user_id]
    history.sort(key=lambda x: x['timestamp'], reverse=True)
    return jsonify(history)

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
    
    if write_csv(WEIGHT_LOG_FILE, weight_log, ['log_id', 'user_id', 'weight', 'timestamp']):
        return jsonify({'success': True})
    return jsonify({'success': False}), 500

@app.route('/api/weight/history/<user_id>', methods=['GET'])
def get_weight_history(user_id):
    weight_log = read_csv(WEIGHT_LOG_FILE)
    history = [w for w in weight_log if w['user_id'] == user_id]
    history.sort(key=lambda x: x['timestamp'], reverse=True)
    return jsonify(history)

@app.route('/api/water/log', methods=['POST'])
def log_water():
    data = request.json
    water_log = read_csv(WATER_LOG_FILE)
    water_log.append({
        'log_id': str(uuid.uuid4()),
        'user_id': data.get('user_id'),
        'amount_ml': data.get('amount_ml', 250),
        'timestamp': datetime.now().isoformat()
    })
    
    if write_csv(WATER_LOG_FILE, water_log, ['log_id', 'user_id', 'amount_ml', 'timestamp']):
        return jsonify({'success': True})
    return jsonify({'success': False}), 500

@app.route('/api/water/today/<user_id>', methods=['GET'])
def get_today_water(user_id):
    today = datetime.now().strftime('%Y-%m-%d')
    water_log = read_csv(WATER_LOG_FILE)
    today_water = [w for w in water_log if w['user_id'] == user_id and w['timestamp'].startswith(today)]
    total = sum(int(w['amount_ml']) for w in today_water)
    return jsonify({'water': today_water, 'total_ml': total})

@app.route('/api/workout/log', methods=['POST'])
def log_workout():
    data = request.json
    workout_name = data.get('workout_name')
    duration = data.get('duration_min', 30)
    user_id = data.get('user_id')
    
    try:
        calories_prompt = f"{workout_name} {duration} daqiqa davomida nechta kaloriya yoqiladi? Faqat raqam."
        calories_resp = model.generate_content(calories_prompt)
        calories_burned = int(''.join(filter(str.isdigit, calories_resp.text)) or '200')
    except:
        calories_burned = 200
    
    workout_log = read_csv(WORKOUT_FILE)
    workout_log.append({
        'log_id': str(uuid.uuid4()),
        'user_id': user_id,
        'workout_name': workout_name,
        'duration_min': str(duration),
        'calories_burned': str(calories_burned),
        'timestamp': datetime.now().isoformat()
    })
    
    if write_csv(WORKOUT_FILE, workout_log, ['log_id', 'user_id', 'workout_name', 'duration_min', 'calories_burned', 'timestamp']):
        return jsonify({'success': True, 'calories_burned': calories_burned})
    return jsonify({'success': False}), 500

@app.route('/api/workout/history/<user_id>', methods=['GET'])
def get_workout_history(user_id):
    workout_log = read_csv(WORKOUT_FILE)
    history = [w for w in workout_log if w['user_id'] == user_id]
    history.sort(key=lambda x: x['timestamp'], reverse=True)
    return jsonify(history)

@app.route('/api/recommendations/<user_id>', methods=['GET'])
def get_recommendations(user_id):
    users = read_csv(USERS_FILE)
    user = next((u for u in users if u['user_id'] == user_id), None)
    
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    today = datetime.now().strftime('%Y-%m-%d')
    food_log = read_csv(FOOD_LOG_FILE)
    today_food = [f for f in food_log if f['user_id'] == user_id and f['timestamp'].startswith(today)]
    total_calories = sum(int(f['calories']) for f in today_food)
    daily_norm = int(user['daily_calorie_norm'])
    
    weight_log = read_csv(WEIGHT_LOG_FILE)
    user_weights = [w for w in weight_log if w['user_id'] == user_id]
    weight_trend = "barqaror"
    if len(user_weights) >= 2:
        diff = float(user_weights[0]['weight']) - float(user_weights[-1]['weight'])
        if diff > 0.5:
            weight_trend = "vazn tushmoqda"
        elif diff < -0.5:
            weight_trend = "vazn oshmoqda"
    
    lang = user.get('language', 'uz')
    lang_name = "o'zbek" if lang == 'uz' else "rus"
    
    prompt = f"""
    Foydalanuvchi: {user.get('name', 'User')}, vazn: {user['weight']}kg, maqsad: {user['goal']}.
    Kunlik norma: {daily_norm} kcal, bugun yegan: {total_calories} kcal.
    Vazn tendensiyasi: {weight_trend}.
    
    Tavsiya bering (2-3 gap, {lang_name} tilida).
    """
    
    try:
        response = model.generate_content(prompt)
        return jsonify({
            'success': True,
            'recommendation': response.text.strip(),
            'daily_norm': daily_norm,
            'consumed': total_calories,
            'remaining': daily_norm - total_calories
        })
    except Exception as e:
        logger.error(f"Recommendation error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/statistics/<user_id>', methods=['GET'])
def get_statistics(user_id):
    period = request.args.get('period', 'week')
    
    if period == 'week':
        days = 7
    else:
        days = 30
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    food_log = read_csv(FOOD_LOG_FILE)
    weight_log = read_csv(WEIGHT_LOG_FILE)
    workout_log = read_csv(WORKOUT_FILE)
    
    user_food = [f for f in food_log if f['user_id'] == user_id and 
                 start_date <= datetime.fromisoformat(f['timestamp']) <= end_date]
    user_weight = [w for w in weight_log if w['user_id'] == user_id and 
                   start_date <= datetime.fromisoformat(w['timestamp']) <= end_date]
    user_workout = [w for w in workout_log if w['user_id'] == user_id and 
                    start_date <= datetime.fromisoformat(w['timestamp']) <= end_date]
    
    daily_stats = {}
    for f in user_food:
        date = f['timestamp'][:10]
        daily_stats[date] = daily_stats.get(date, 0) + int(f['calories'])
    
    return jsonify({
        'total_calories': sum(int(f['calories']) for f in user_food),
        'total_workouts': len(user_workout),
        'total_calories_burned': sum(int(w['calories_burned']) for w in user_workout),
        'weight_changes': user_weight,
        'daily_calories': daily_stats,
        'period_days': days
    })

# ================= ADMIN PANEL API =================

@app.route('/api/admin/users', methods=['GET'])
def admin_get_users():
    admin_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    expected_token = os.getenv('ADMIN_TOKEN', 'admin123')
    
    if admin_token != expected_token:
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = read_csv(USERS_FILE)
    return jsonify({
        'users': users,
        'total': len(users)
    })

@app.route('/api/admin/user/<user_id>', methods=['DELETE'])
def admin_delete_user(user_id):
    admin_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    expected_token = os.getenv('ADMIN_TOKEN', 'admin123')
    
    if admin_token != expected_token:
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = [u for u in read_csv(USERS_FILE) if u['user_id'] != user_id]
    write_csv(USERS_FILE, users, ['user_id', 'name', 'weight', 'height', 'age', 'gender', 'goal', 'daily_calorie_norm', 'profile_pic', 'language', 'created_at'])
    
    return jsonify({'success': True})

@app.route('/api/admin/user/<user_id>/block', methods=['POST'])
def admin_block_user(user_id):
    admin_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    expected_token = os.getenv('ADMIN_TOKEN', 'admin123')
    
    if admin_token != expected_token:
        return jsonify({'error': 'Unauthorized'}), 403
    
    with open(BLOCKED_USERS_FILE, 'a') as f:
        f.write(f"{user_id}\n")
    
    return jsonify({'success': True})

@app.route('/api/admin/statistics', methods=['GET'])
def admin_statistics():
    admin_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    expected_token = os.getenv('ADMIN_TOKEN', 'admin123')
    
    if admin_token != expected_token:
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = read_csv(USERS_FILE)
    food_log = read_csv(FOOD_LOG_FILE)
    
    today = datetime.now().strftime('%Y-%m-%d')
    active_today = len(set([f['user_id'] for f in food_log if f['timestamp'].startswith(today)]))
    
    total_calories = sum(int(f['calories']) for f in food_log)
    
    return jsonify({
        'total_users': len(users),
        'active_today': active_today,
        'total_food_logs': len(food_log),
        'total_calories': total_calories
    })

# ================= TELEGRAM BOT =================

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEB_APP_URL = os.getenv('WEB_APP_URL', 'https://nimayedimbot-pro-production.up.railway.app')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if is_user_blocked(user_id):
        await update.message.reply_text("Siz bloklangan foydalanuvchisiz.")
        return
    
    keyboard = [[InlineKeyboardButton("📱 Ilovani Ochish", web_app={"url": WEB_APP_URL})]]
    
    lang = 'uz'
    users = read_csv(USERS_FILE)
    user = next((u for u in users if u['user_id'] == user_id), None)
    if user:
        lang = user.get('language', 'uz')
    
    if lang == 'ru':
        text = "👋 *Добро пожаловать!*\n\n🍏 Трекер калорий\n✨ Gemini AI\n\nНажмите кнопку ниже:"
    else:
        text = "👋 *Xush kelibsiz!*\n\n🍏 Kaloriya trekeri\n✨ Gemini AI\n\nTugmani bosing:"
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - Boshlash\n"
        "/help - Yordam\n"
        "/settings - Sozlamalar"
    )

# ================= MAIN =================

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Flask on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🍏 NimaYedimBot - Professional Kaloriya Tracker")
    logger.info("✨ Gemini 2.0 Flash AI")
    logger.info("🌍 Multi-language: Uzbek/Russian")
    logger.info("=" * 60)
    
    init_files()
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask started")
    
    logger.info("🤖 Starting Telegram Bot...")
    
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        
        logger.info("🤖 Bot running...")
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise
