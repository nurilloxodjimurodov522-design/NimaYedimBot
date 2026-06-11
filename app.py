"""
NimaYedimBot - Kaloriya Tracker Mini App
Professional Flask + Telegram Bot Integration
Gemini 2.0 Flash AI (3.5 Flash)
"""

import os
import csv
import json
import uuid
import logging
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import google.generativeai as genai

# Telegram kutubxonalari
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Logging sozlash
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment yuklash
load_dotenv()

# ================= FLASK APP SOZLAMALARI =================

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key')

# ================= GEMINI 2.0 FLASH (3.5 Flash) =================

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    logger.error("❌ GEMINI_API_KEY not set!")
    raise ValueError("GEMINI_API_KEY required")

genai.configure(api_key=GEMINI_API_KEY)

# Gemini 2.0 Flash - eng tez va samarali (3.5 Flash ekvivalenti)
try:
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
    logger.info("✅ Gemini 2.0 Flash AI initialized")
except Exception as e:
    logger.warning(f"Gemini 2.0 not available, using gemini-1.5-flash: {e}")
    model = genai.GenerativeModel('gemini-1.5-flash')

# ================= FAYL YO'LLARI =================

USERS_FILE = 'data/users.csv'
FOOD_LOG_FILE = 'data/food_log.csv'
WEIGHT_LOG_FILE = 'data/weight_log.csv'

os.makedirs('data', exist_ok=True)

# ================= CSV FUNKSIYALARI =================

def init_files():
    """CSV fayllarni yaratadi"""
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
    
    logger.info("✅ CSV files initialized")

def read_csv(filepath):
    """CSV o'qiydi"""
    if not os.path.exists(filepath): 
        return []
    try:
        with open(filepath, 'r', encoding='utf-8') as f: 
            return list(csv.DictReader(f))
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")
        return []

def write_csv(filepath, data, fieldnames):
    """CSV yozadi"""
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
    """Kunlik kaloriya normasini hisoblaydi"""
    try:
        w, h, a = float(weight), float(height), float(age)
        
        if gender == 'male':
            bmr = (10 * w) + (6.25 * h) - (5 * a) + 5
        else:
            bmr = (10 * w) + (6.25 * h) - (5 * a) - 161
        
        bmr *= 1.2  # Faollik
        
        if goal == 'lose': 
            bmr -= 500
        elif goal == 'gain': 
            bmr += 500
        
        return int(bmr)
    except Exception as e:
        logger.error(f"Error calculating norm: {e}")
        return 2000

# ================= WEB ROUTES =================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/user/<user_id>', methods=['GET'])
def get_user(user_id):
    try:
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
    except Exception as e:
        logger.error(f"Error in get_user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/user', methods=['POST'])
def create_user():
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': 'No data'}), 400
        
        users = read_csv(USERS_FILE)
        
        if any(u['user_id'] == data.get('user_id') for u in users): 
            return jsonify({'success': False, 'error': 'User exists'})
        
        daily_norm = calculate_daily_norm(
            data.get('weight'), 
            data.get('height'), 
            data.get('age'), 
            data.get('gender'), 
            data.get('goal')
        )
        
        new_user = {
            'user_id': data.get('user_id'), 
            'name': data.get('name', ''), 
            'weight': data.get('weight'), 
            'height': data.get('height'), 
            'age': data.get('age'), 
            'gender': data.get('gender'), 
            'goal': data.get('goal'), 
            'daily_calorie_norm': str(daily_norm), 
            'profile_pic': ''
        }
        
        users.append(new_user)
        
        if write_csv(USERS_FILE, users, ['user_id', 'name', 'weight', 'height', 'age', 'gender', 'goal', 'daily_calorie_norm', 'profile_pic']):
            return jsonify({'success': True, 'daily_norm': daily_norm})
        else:
            return jsonify({'success': False, 'error': 'Save failed'}), 500
            
    except Exception as e:
        logger.error(f"Error in create_user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/food/log', methods=['POST'])
def log_food():
    try:
        data = request.json
        food_name = data.get('food_name')
        user_id = data.get('user_id')
        
        if not food_name or not user_id:
            return jsonify({'success': False, 'error': 'Missing fields'}), 400
        
        # Gemini AI bilan kaloriya hisoblash
        calorie_prompt = f"{food_name} kaloriyasi nechta? Faqat raqam yoz."
        calorie_resp = model.generate_content(calorie_prompt)
        calories_text = ''.join(filter(str.isdigit, calorie_resp.text))
        calories = int(calories_text) if calories_text else 100
        
        # Tafsilotlar
        details_prompt = f"{food_name} haqida qisqa ma'lumot (1 gap)."
        details_resp = model.generate_content(details_prompt)
        details = details_resp.text.strip()
        
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
        
        if write_csv(FOOD_LOG_FILE, food_log, ['log_id', 'user_id', 'food_name', 'calories', 'details', 'photo', 'status', 'timestamp']):
            logger.info(f"Food logged: {food_name} - {calories} kcal")
            return jsonify({'success': True, 'calories': calories, 'details': details})
        else:
            return jsonify({'success': False, 'error': 'Save failed'}), 500
            
    except Exception as e:
        logger.error(f"Error in log_food: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/food/today/<user_id>', methods=['GET'])
def get_today_food(user_id):
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        food_log = read_csv(FOOD_LOG_FILE)
        today_food = [f for f in food_log if f['user_id'] == user_id and f['timestamp'].startswith(today) and f['status'] == 'approved']
        total = sum(int(f['calories']) for f in today_food)
        
        return jsonify({'food': today_food, 'total_calories': total})
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/weight/log', methods=['POST'])
def log_weight():
    try:
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
        else:
            return jsonify({'success': False, 'error': 'Save failed'}), 500
            
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/weight/history/<user_id>', methods=['GET'])
def get_weight_history(user_id):
    try:
        weight_log = read_csv(WEIGHT_LOG_FILE)
        history = [w for w in weight_log if w['user_id'] == user_id]
        history.sort(key=lambda x: x['timestamp'], reverse=True)
        return jsonify(history)
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/recommendations/<user_id>', methods=['GET'])
def get_recommendations(user_id):
    try:
        users = read_csv(USERS_FILE)
        user = next((u for u in users if u['user_id'] == user_id), None)
        
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        today = datetime.now().strftime('%Y-%m-%d')
        food_log = read_csv(FOOD_LOG_FILE)
        today_food = [f for f in food_log if f['user_id'] == user_id and f['timestamp'].startswith(today) and f['status'] == 'approved']
        total_calories = sum(int(f['calories']) for f in today_food)
        daily_norm = int(user['daily_calorie_norm'])
        
        prompt = f"""
        Foydalanuvchi: {user.get('name', 'User')}, vazn: {user['weight']}kg, maqsad: {user['goal']}.
        Kunlik norma: {daily_norm} kcal, bugun yegan: {total_calories} kcal.
        Qisqa tavsiya bering (2-3 gap, o'zbekcha).
        """
        response = model.generate_content(prompt)
        
        return jsonify({
            'success': True,
            'recommendation': response.text.strip(),
            'daily_norm': daily_norm,
            'consumed': total_calories,
            'remaining': daily_norm - total_calories
        })
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ================= TELEGRAM BOT =================

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN not set!")
    raise ValueError("TELEGRAM_BOT_TOKEN required")

WEB_APP_URL = os.getenv('WEB_APP_URL', 'https://nimayedimbot-pro-production.up.railway.app')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        keyboard = [[InlineKeyboardButton("📱 Ilovani Ochish", web_app={"url": WEB_APP_URL})]]
        await update.message.reply_text(
            "👋 *Salom! NimaYedimBot*\n\n"
            "🍏 Kaloriya hisoblash uchun tugmani bosing:\n\n"
            "✨ Gemini 2.0 Flash AI",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info(f"User {update.effective_user.id} started bot")
    except Exception as e:
        logger.error(f"Error in start: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        help_text = """
🤖 *NimaYedimBot - Kaloriya Tracker*

📱 Mini App - ovqat va vazn
🍔 AI kaloriya hisoblash
⚖️ Vazn kuzatish
📊 Statistika

/start - Boshlash
/help - Yordam
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in help: {e}")

# ================= ASOSIY ISHGA TUSHIRISH =================

def run_flask():
    """Flask server"""
    try:
        port = int(os.environ.get('PORT', 5000))
        logger.info(f"🚀 Flask on port {port}")
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Flask error: {e}")

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🍏 NimaYedimBot - Kaloriya Tracker")
    logger.info("✨ Gemini 2.0 Flash (3.5 Flash)")
    logger.info("=" * 50)
    
    init_files()
    
    # Flask thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask started")
    
    # Telegram bot
    logger.info("🤖 Starting Telegram Bot...")
    logger.info(f"🌐 Web App: {WEB_APP_URL}")
    
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        
        logger.info("🤖 Bot polling started...")
        # MUHIM: read_timeout/connect_timeout YO'Q!
        application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
        raise
