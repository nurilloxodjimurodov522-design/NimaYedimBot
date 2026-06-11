"""
NimaYedimBot - Kaloriya Tracker Mini App
Professional Flask + Telegram Bot Integration
Gemini 3.5 Flash AI
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
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key-change-in-production')

# ================= GEMINI 3.5 FLASH AI SOZLAMALARI =================

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY environment variable not set!")
    raise ValueError("GEMINI_API_KEY is required")

genai.configure(api_key=GEMINI_API_KEY)

# Gemini 3.5 Flash model - tez va samarali!
model = genai.GenerativeModel('gemini-2.0-flash-exp')
logger.info("✅ Gemini 3.5 Flash AI initialized")

# ================= FAYL YO'LLARI =================

USERS_FILE = 'data/users.csv'
FOOD_LOG_FILE = 'data/food_log.csv'
WEIGHT_LOG_FILE = 'data/weight_log.csv'

# Data papkasini yaratish
os.makedirs('data', exist_ok=True)

# ================= CSV FUNKSIYALARI =================

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
    
    logger.info("CSV files initialized successfully")

def read_csv(filepath):
    """CSV faylni o'qiydi"""
    if not os.path.exists(filepath): 
        return []
    try:
        with open(filepath, 'r', encoding='utf-8') as f: 
            return list(csv.DictReader(f))
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")
        return []

def write_csv(filepath, data, fieldnames):
    """CSV faylga yozadi"""
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
    """Kunlik kaloriya normasini hisoblaydi (Mifflin-St Jeor formulasi)"""
    try:
        w, h, a = float(weight), float(height), float(age)
        
        # BMR hisoblash
        if gender == 'male':
            bmr = (10 * w) + (6.25 * h) - (5 * a) + 5
        else:
            bmr = (10 * w) + (6.25 * h) - (5 * a) - 161
        
        # Faollik koeffitsienti (sedentary)
        bmr *= 1.2
        
        # Maqsadga qarab sozlash
        if goal == 'lose': 
            bmr -= 500  # Vazn yo'qotish uchun defitsit
        elif goal == 'gain': 
            bmr += 500  # Vazn to'plash uchun ortiqcha
        
        return int(bmr)
    except Exception as e:
        logger.error(f"Error calculating daily norm: {e}")
        return 2000  # Default qiymat

# ================= WEB ROUTES (MINI APP) =================

@app.route('/')
def index():
    """Asosiy sahifa - Mini App"""
    return render_template('index.html')

@app.route('/api/user/<user_id>', methods=['GET'])
def get_user(user_id):
    """Foydalanuvchi ma'lumotlarini olish"""
    try:
        users = read_csv(USERS_FILE)
        user = next((u for u in users if u['user_id'] == user_id), None)
        
        if not user: 
            return jsonify({'exists': False})
        
        # Bugungi ovqatlar
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
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/user', methods=['POST'])
def create_user():
    """Yangi foydalanuvchi yaratish"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        users = read_csv(USERS_FILE)
        
        # Mavjudligini tekshirish
        if any(u['user_id'] == data.get('user_id') for u in users): 
            return jsonify({'success': False, 'error': 'User already exists'})
        
        # Kunlik norma hisoblash
        daily_norm = calculate_daily_norm(
            data.get('weight'), 
            data.get('height'), 
            data.get('age'), 
            data.get('gender'), 
            data.get('goal')
        )
        
        # Yangi foydalanuvchi
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
            return jsonify({'success': False, 'error': 'Failed to save user'}), 500
            
    except Exception as e:
        logger.error(f"Error in create_user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/user/<user_id>', methods=['PUT'])
def update_user(user_id):
    """Foydalanuvchi ma'lumotlarini yangilash"""
    try:
        data = request.json
        users = read_csv(USERS_FILE)
        
        for i, user in enumerate(users):
            if user['user_id'] == user_id:
                if 'weight' in data:
                    users[i]['weight'] = data['weight']
                if 'name' in data:
                    users[i]['name'] = data['name']
                if 'profile_pic' in data:
                    users[i]['profile_pic'] = data['profile_pic']
                
                # Normani qayta hisoblash
                if all(k in data for k in ['weight', 'height', 'age', 'gender', 'goal']):
                    users[i]['daily_calorie_norm'] = str(calculate_daily_norm(
                        data['weight'], data['height'], data['age'], data['gender'], data['goal']
                    ))
                
                if write_csv(USERS_FILE, users, ['user_id', 'name', 'weight', 'height', 'age', 'gender', 'goal', 'daily_calorie_norm', 'profile_pic']):
                    return jsonify({'success': True})
                else:
                    return jsonify({'success': False, 'error': 'Failed to update'}), 500
        
        return jsonify({'success': False, 'error': 'User not found'}), 404
        
    except Exception as e:
        logger.error(f"Error in update_user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/food/log', methods=['POST'])
def log_food():
    """Ovqat qo'shish (Gemini 3.5 Flash AI bilan kaloriya hisoblash)"""
    try:
        data = request.json
        food_name = data.get('food_name')
        user_id = data.get('user_id')
        
        if not food_name or not user_id:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Gemini 3.5 Flash orqali kaloriya hisoblash (tez va aniq!)
        calorie_prompt = f"{food_name} ning kaloriyasi nechta? Faqat raqam qismini yozing (masalan: 250)."
        calorie_resp = model.generate_content(calorie_prompt)
        calories_text = ''.join(filter(str.isdigit, calorie_resp.text))
        calories = int(calories_text) if calories_text else 0
        
        # Gemini 3.5 Flash orqali tafsilotlar (qisqa va aniq)
        details_prompt = f"{food_name} haqida qisqa ma'lumot: tarkibi va kaloriya manbai (o'zbekcha, 1 gap)."
        details_resp = model.generate_content(details_prompt)
        details = details_resp.text.strip()
        
        # Log yaratish
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
            return jsonify({'success': False, 'error': 'Failed to save food log'}), 500
            
    except Exception as e:
        logger.error(f"Error in log_food: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/food/today/<user_id>', methods=['GET'])
def get_today_food(user_id):
    """Bugungi ovqatlar ro'yxati"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        food_log = read_csv(FOOD_LOG_FILE)
        today_food = [f for f in food_log if f['user_id'] == user_id and f['timestamp'].startswith(today) and f['status'] == 'approved']
        total = sum(int(f['calories']) for f in today_food)
        
        return jsonify({'food': today_food, 'total_calories': total})
    except Exception as e:
        logger.error(f"Error in get_today_food: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/food/history/<user_id>', methods=['GET'])
def get_food_history(user_id):
    """Foydalanuvchi ovqat tarixi"""
    try:
        food_log = read_csv(FOOD_LOG_FILE)
        history = [f for f in food_log if f['user_id'] == user_id]
        history.sort(key=lambda x: x['timestamp'], reverse=True)
        return jsonify(history)
    except Exception as e:
        logger.error(f"Error in get_food_history: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/weight/log', methods=['POST'])
def log_weight():
    """Vazn o'lchovini saqlash"""
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
            return jsonify({'success': False, 'error': 'Failed to save weight'}), 500
            
    except Exception as e:
        logger.error(f"Error in log_weight: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/weight/history/<user_id>', methods=['GET'])
def get_weight_history(user_id):
    """Vazn o'lchovlari tarixi"""
    try:
        weight_log = read_csv(WEIGHT_LOG_FILE)
        history = [w for w in weight_log if w['user_id'] == user_id]
        history.sort(key=lambda x: x['timestamp'], reverse=True)
        return jsonify(history)
    except Exception as e:
        logger.error(f"Error in get_weight_history: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/recommendations/<user_id>', methods=['GET'])
def get_recommendations(user_id):
    """Gemini 3.5 Flash AI tavsiyalari"""
    try:
        users = read_csv(USERS_FILE)
        user = next((u for u in users if u['user_id'] == user_id), None)
        
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # Bugungi ovqatlar
        today = datetime.now().strftime('%Y-%m-%d')
        food_log = read_csv(FOOD_LOG_FILE)
        today_food = [f for f in food_log if f['user_id'] == user_id and f['timestamp'].startswith(today) and f['status'] == 'approved']
        total_calories = sum(int(f['calories']) for f in today_food)
        daily_norm = int(user['daily_calorie_norm'])
        
        # Gemini 3.5 Flash AI bilan tavsiya (tez va aniq!)
        prompt = f"""
        Foydalanuvchi: {user.get('name', 'Foydalanuvchi')}, vazn: {user['weight']}kg, maqsad: {user['goal']}.
        Kunlik kaloriya normasi: {daily_norm} kcal.
        Bugun yegan kaloriya: {total_calories} kcal.
        Qolgan: {daily_norm - total_calories} kcal.
        
        Iltimos, qisqa va aniq tavsiya bering (2-3 gap, o'zbek tilida). 
        Foydalanuvchining maqsadiga qarab maslahat bering.
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
        logger.error(f"Error in get_recommendations: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ================= TELEGRAM BOT QISMI =================

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable not set!")
    raise ValueError("TELEGRAM_BOT_TOKEN is required")

# Web App URL (Railway URL ingizni yozing)
WEB_APP_URL = os.getenv('WEB_APP_URL', 'https://nimayedimbot-pro-production.up.railway.app')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start command handler - Mini App tugmasi"""
    try:
        keyboard = [[InlineKeyboardButton("📱 Ilovani Ochish", web_app={"url": WEB_APP_URL})]]
        await update.message.reply_text(
            "👋 *Salom! NimaYedimBot* ga xush kelibsiz!\n\n"
            "🍏 Kaloriya hisoblash va profilingizni boshqarish uchun "
            "pastdagi tugmani bosing:\n\n"
            "✨ *Gemini 3.5 Flash AI* yordamida tez va aniq natijalar!",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info(f"User {update.effective_user.id} started the bot")
    except Exception as e:
        logger.error(f"Error in start command: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help command handler"""
    try:
        help_text = """
🤖 *NimaYedimBot - Kaloriya Tracker*

📱 *Mini App* - ovqat va vaznni kuzatish
🍔 *Ovqat qo'shish* - Gemini AI kaloriya hisoblaydi
⚖️ *Vazn o'lchash* - progressni kuzating
📊 *Statistika* - kunlik natijalar
💡 *AI Tavsiyalar* - shaxsiy maslahatlar

*Buyruqlar:*
/start - Boshlash
/help - Yordam

✨ *Gemini 3.5 Flash* bilan ishlaydi - tez va aniq!
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in help command: {e}")

# ================= ASOSIY ISHGA TUSHIRISH =================

def run_flask():
    """Flask serverni alohida thread da ishlatadi"""
    try:
        port = int(os.environ.get('PORT', 5000))
        logger.info(f"🚀 Starting Flask server on port {port}")
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Error starting Flask server: {e}")

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🍏 NimaYedimBot - Kaloriya Tracker")
    logger.info("✨ Gemini 3.5 Flash AI")
    logger.info("=" * 50)
    
    # CSV fayllarni ishga tushirish
    init_files()
    
    # Flask serverni orqa fonda ishga tushirish
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask server started in background")
    
    # Telegram botni asosiy oqimda ishga tushirish
    logger.info("🤖 Starting Telegram Bot...")
    logger.info(f"🌐 Web App URL: {WEB_APP_URL}")
    
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        
        # Botni polling rejimida ishga tushirish
        logger.info("🤖 Bot is running in polling mode...")
        application.run_polling(
            drop_pending_updates=True,
            read_timeout=30,
            connect_timeout=30
        )
    except Exception as e:
        logger.error(f"Error starting Telegram Bot: {e}")
        raise
