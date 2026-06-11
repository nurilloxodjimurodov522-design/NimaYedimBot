"""
NimaYedimBot - Professional Kaloriya Tracker
Database: PostgreSQL | AI: Gemini 3.5 Flash
"""

import os
import logging
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import google.generativeai as genai

# Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# SQLAlchemy
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

# Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'secret-key-change-me')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# PostgreSQL
database_url = os.getenv('DATABASE_URL')
if database_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db = SQLAlchemy(app)
    logger.info("✅ PostgreSQL connected")
else:
    logger.error("❌ DATABASE_URL not set!")
    raise ValueError("DATABASE_URL required")

# Gemini AI (hamma vazifalar uchun)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)
try:
    model = genai.GenerativeModel('gemini-3.5-flash')
except:
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
logger.info("✅ Gemini 3.5 Flash AI initialized")

# Admin users
ADMIN_USERS = os.getenv('ADMIN_USERS', '').split(',')
ADMIN_USERS = [u.strip() for u in ADMIN_USERS if u.strip()]

# ================= DATABASE MODELS =================

class User(db.Model):
    __tablename__ = 'users'
    
    user_id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100))
    weight = db.Column(db.Float)
    height = db.Column(db.Float)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    goal = db.Column(db.String(20))
    daily_calorie_norm = db.Column(db.Integer)
    profile_pic = db.Column(db.String(200))
    language = db.Column(db.String(10), default='uz')
    created_at = db.Column(db.DateTime, default=datetime.now)
    is_blocked = db.Column(db.Boolean, default=False)
    
    food_logs = db.relationship('FoodLog', backref='user', lazy=True, cascade='all, delete-orphan')
    weight_logs = db.relationship('WeightLog', backref='user', lazy=True, cascade='all, delete-orphan')
    water_logs = db.relationship('WaterLog', backref='user', lazy=True, cascade='all, delete-orphan')
    workouts = db.relationship('Workout', backref='user', lazy=True, cascade='all, delete-orphan')

class FoodLog(db.Model):
    __tablename__ = 'food_logs'
    
    log_id = db.Column(db.String(50), primary_key=True)
    user_id = db.Column(db.String(50), db.ForeignKey('users.user_id'), nullable=False)
    food_name = db.Column(db.String(200))
    calories = db.Column(db.Integer)
    details = db.Column(db.Text)
    photo = db.Column(db.String(200))
    status = db.Column(db.String(20), default='approved')
    timestamp = db.Column(db.DateTime, default=datetime.now)

class WeightLog(db.Model):
    __tablename__ = 'weight_logs'
    
    log_id = db.Column(db.String(50), primary_key=True)
    user_id = db.Column(db.String(50), db.ForeignKey('users.user_id'), nullable=False)
    weight = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.now)

class WaterLog(db.Model):
    __tablename__ = 'water_logs'
    
    log_id = db.Column(db.String(50), primary_key=True)
    user_id = db.Column(db.String(50), db.ForeignKey('users.user_id'), nullable=False)
    amount_ml = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.now)

class Workout(db.Model):
    __tablename__ = 'workouts'
    
    log_id = db.Column(db.String(50), primary_key=True)
    user_id = db.Column(db.String(50), db.ForeignKey('users.user_id'), nullable=False)
    workout_name = db.Column(db.String(200))
    duration_min = db.Column(db.Integer)
    calories_burned = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.now)

# ================= FUNKSIYALAR =================

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
    with app.app_context():
        user = User.query.get(user_id)
        return user.is_blocked if user else False

def is_admin(user_id):
    return user_id in ADMIN_USERS

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
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'exists': False})
    
    today = datetime.now().date()
    today_food = FoodLog.query.filter(
        FoodLog.user_id == user_id,
        func.date(FoodLog.timestamp) == today
    ).all()
    total_calories = sum(f.calories for f in today_food)
    
    today_water = WaterLog.query.filter(
        WaterLog.user_id == user_id,
        func.date(WaterLog.timestamp) == today
    ).all()
    total_water = sum(w.amount_ml for w in today_water)
    
    return jsonify({
        'exists': True,
        'user': {
            'user_id': user.user_id,
            'name': user.name,
            'weight': user.weight,
            'height': user.height,
            'age': user.age,
            'gender': user.gender,
            'goal': user.goal,
            'daily_calorie_norm': user.daily_calorie_norm,
            'language': user.language
        },
        'today_calories': total_calories,
        'today_water': total_water,
        'food_count': len(today_food)
    })

@app.route('/api/user', methods=['POST'])
def create_user():
    data = request.json
    
    if User.query.get(data.get('user_id')):
        return jsonify({'success': False, 'error': 'User exists'})
    
    daily_norm = calculate_daily_norm(data['weight'], data['height'], data['age'], data['gender'], data['goal'])
    
    new_user = User(
        user_id=data['user_id'],
        name=data.get('name', ''),
        weight=data['weight'],
        height=data['height'],
        age=data['age'],
        gender=data['gender'],
        goal=data['goal'],
        daily_calorie_norm=daily_norm,
        language=data.get('language', 'uz')
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({'success': True, 'daily_norm': daily_norm})

@app.route('/api/user/<user_id>', methods=['PUT'])
def update_user(user_id):
    data = request.json
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    if 'name' in data: user.name = data['name']
    if 'weight' in data: user.weight = data['weight']
    if 'height' in data: user.height = data['height']
    if 'age' in data: user.age = data['age']
    if 'gender' in data: user.gender = data['gender']
    if 'goal' in data: user.goal = data['goal']
    if 'language' in data: user.language = data['language']
    
    if all(k in data for k in ['weight', 'height', 'age', 'gender', 'goal']):
        user.daily_calorie_norm = calculate_daily_norm(data['weight'], data['height'], data['age'], data['gender'], data['goal'])
    
    db.session.commit()
    
    return jsonify({'success': True})

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
        
        new_log = FoodLog(
            log_id=str(os.urandom(24).hex()),
            user_id=user_id,
            food_name=food_name,
            calories=calories,
            details=details
        )
        
        db.session.add(new_log)
        db.session.commit()
        
        return jsonify({'success': True, 'calories': calories, 'details': details})
    except Exception as e:
        logger.error(f"Food log error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/food/today/<user_id>', methods=['GET'])
def get_today_food(user_id):
    today = datetime.now().date()
    today_food = FoodLog.query.filter(
        FoodLog.user_id == user_id,
        func.date(FoodLog.timestamp) == today
    ).all()
    total = sum(f.calories for f in today_food)
    
    return jsonify({
        'food': [{
            'log_id': f.log_id,
            'food_name': f.food_name,
            'calories': f.calories,
            'details': f.details,
            'timestamp': f.timestamp.isoformat()
        } for f in today_food],
        'total_calories': total
    })

@app.route('/api/food/<log_id>', methods=['DELETE'])
def delete_food(log_id):
    food = FoodLog.query.get(log_id)
    if food:
        db.session.delete(food)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Not found'}), 404

@app.route('/api/weight/log', methods=['POST'])
def log_weight():
    data = request.json
    
    new_log = WeightLog(
        log_id=str(os.urandom(24).hex()),
        user_id=data.get('user_id'),
        weight=data.get('weight')
    )
    
    db.session.add(new_log)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/weight/history/<user_id>', methods=['GET'])
def get_weight_history(user_id):
    weight_logs = WeightLog.query.filter_by(user_id=user_id).order_by(WeightLog.timestamp.desc()).all()
    return jsonify([{
        'log_id': w.log_id,
        'weight': w.weight,
        'timestamp': w.timestamp.isoformat()
    } for w in weight_logs])

@app.route('/api/water/log', methods=['POST'])
def log_water():
    data = request.json
    
    new_log = WaterLog(
        log_id=str(os.urandom(24).hex()),
        user_id=data.get('user_id'),
        amount_ml=data.get('amount_ml', 250)
    )
    
    db.session.add(new_log)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/water/today/<user_id>', methods=['GET'])
def get_today_water(user_id):
    today = datetime.now().date()
    today_water = WaterLog.query.filter(
        WaterLog.user_id == user_id,
        func.date(WaterLog.timestamp) == today
    ).all()
    total = sum(w.amount_ml for w in today_water)
    
    return jsonify({
        'water': [{
            'log_id': w.log_id,
            'amount_ml': w.amount_ml,
            'timestamp': w.timestamp.isoformat()
        } for w in today_water],
        'total_ml': total
    })

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
    
    new_log = Workout(
        log_id=str(os.urandom(24).hex()),
        user_id=user_id,
        workout_name=workout_name,
        duration_min=duration,
        calories_burned=calories_burned
    )
    
    db.session.add(new_log)
    db.session.commit()
    
    return jsonify({'success': True, 'calories_burned': calories_burned})

@app.route('/api/workout/history/<user_id>', methods=['GET'])
def get_workout_history(user_id):
    workouts = Workout.query.filter_by(user_id=user_id).order_by(Workout.timestamp.desc()).all()
    return jsonify([{
        'log_id': w.log_id,
        'workout_name': w.workout_name,
        'duration_min': w.duration_min,
        'calories_burned': w.calories_burned,
        'timestamp': w.timestamp.isoformat()
    } for w in workouts])

@app.route('/api/workout/<log_id>', methods=['DELETE'])
def delete_workout(log_id):
    workout = Workout.query.get(log_id)
    if workout:
        db.session.delete(workout)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Not found'}), 404

@app.route('/api/recommendations/<user_id>', methods=['GET'])
def get_recommendations(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    today = datetime.now().date()
    today_food = FoodLog.query.filter(
        FoodLog.user_id == user_id,
        func.date(FoodLog.timestamp) == today
    ).all()
    total_calories = sum(f.calories for f in today_food)
    daily_norm = user.daily_calorie_norm
    
    weight_logs = WeightLog.query.filter_by(user_id=user_id).order_by(WeightLog.timestamp.desc()).all()
    weight_trend = "barqaror"
    if len(weight_logs) >= 2:
        diff = weight_logs[0].weight - weight_logs[-1].weight
        if diff > 0.5:
            weight_trend = "vazn tushmoqda"
        elif diff < -0.5:
            weight_trend = "vazn oshmoqda"
    
    lang_name = "o'zbek" if user.language == 'uz' else "rus"
    
    prompt = f"""
    Foydalanuvchi: {user.name}, vazn: {user.weight}kg, maqsad: {user.goal}.
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
    days = int(request.args.get('days', 7))
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    food_logs = FoodLog.query.filter(
        FoodLog.user_id == user_id,
        FoodLog.timestamp >= start_date,
        FoodLog.timestamp <= end_date
    ).all()
    
    daily_stats = {}
    for f in food_logs:
        date = f.timestamp.strftime('%Y-%m-%d')
        daily_stats[date] = daily_stats.get(date, 0) + f.calories
    
    for i in range(days):
        date = (end_date - timedelta(days=i)).strftime('%Y-%m-%d')
        if date not in daily_stats:
            daily_stats[date] = 0
    
    return jsonify({
        'total_calories': sum(f.calories for f in food_logs),
        'daily_calories': daily_stats,
        'period_days': days
    })

# ================= AI CHAT (Gemini) =================

@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    """AI Dietolog - Gemini modeli bilan"""
    data = request.json
    message = data.get('message')
    user_id = data.get('user_id')
    context = data.get('context', {})
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    # Foydalanuvchi ma'lumotlari
    user_info = f"""
Foydalanuvchi ma'lumotlari:
- Ism: {user.name}
- Vazn: {user.weight}kg
- Boy: {user.height}cm
- Yosh: {user.age}
- Maqsad: {user.goal}
- Kunlik norma: {context.get('daily_norm', user.daily_calorie_norm)} kcal
- Bugun yegan: {context.get('consumed', 0)} kcal
- Qolgan: {context.get('remaining', 0)} kcal
"""
    
    # Tizim prompti (faqat dietologiya)
    system_prompt = """Siz professional dietologsiz. Faqat quyidagi mavzularda javob bering:
- Kaloriya hisoblash va parhez
- Suv iste'moli va suv rejimi
- Vazn yo'qotish va vazn to'plash
- Sog'lom ovqatlanish
- Mashg'ulot va kaloriya yo'qotish
- Vitaminlar va minerallar
- O'zbek va rus taomlari haqida maslahatlar

Agar foydalanuvchi boshqa mavzuda so'rasa, nazokat bilan bu mavzuda gapira olmasligingizni ayting va dietologiya mavzulariga qayting.

Javob qisqa, aniq va foydali bo'lsin (3-5 gap). Emojilardan foydalaning.
"""
    
    try:
        full_prompt = f"{system_prompt}\n\n{user_info}\n\nSavol: {message}"
        response = model.generate_content(full_prompt)
        
        return jsonify({
            'success': True,
            'response': response.text.strip()
        })
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ================= ADMIN API =================

@app.route('/api/admin/users', methods=['GET'])
def admin_get_users():
    admin_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    expected_token = os.getenv('ADMIN_TOKEN', 'admin123')
    
    if admin_token != expected_token:
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = User.query.all()
    return jsonify({
        'users': [{
            'user_id': u.user_id,
            'name': u.name,
            'weight': u.weight,
            'goal': u.goal,
            'language': u.language,
            'daily_calorie_norm': u.daily_calorie_norm,
            'created_at': u.created_at.isoformat(),
            'is_blocked': u.is_blocked
        } for u in users],
        'total': len(users)
    })

@app.route('/api/admin/statistics', methods=['GET'])
def admin_statistics():
    admin_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    expected_token = os.getenv('ADMIN_TOKEN', 'admin123')
    
    if admin_token != expected_token:
        return jsonify({'error': 'Unauthorized'}), 403
    
    total_users = User.query.count()
    today = datetime.now().date()
    active_today = db.session.query(func.count(func.distinct(FoodLog.user_id))).filter(
        func.date(FoodLog.timestamp) == today
    ).scalar()
    
    total_calories = db.session.query(func.sum(FoodLog.calories)).scalar() or 0
    
    return jsonify({
        'total_users': total_users,
        'active_today': active_today,
        'total_calories': int(total_calories)
    })

# ================= TELEGRAM BOT =================

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEB_APP_URL = os.getenv('WEB_APP_URL', 'https://nimayedimbot-pro-production.up.railway.app')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    
    logger.info(f"User {user_id} started the bot")
    
    with app.app_context():
        if is_user_blocked(user_id):
            await update.message.reply_text("❌ Siz bloklangan foydalanuvchisiz.")
            return
        
        user = User.query.get(user_id)
        lang = user.language if user else 'uz'
    
    keyboard = [[InlineKeyboardButton("📱 Ilovani Ochish", web_app={"url": WEB_APP_URL})]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if lang == 'ru':
        text = f"""
👋 *Добро пожаловать, {user_name}!*

🍏 *Kaloriya Tracker Pro*
🤖 Powered by Gemini 3.5 Flash

📊 *Возможности:*
• 🍔 AI подсчет калорий
• 💧 Трекер воды
• 🏃 Учет тренировок
• 📈 Статистика
• 💡 AI диетолог

Нажмите кнопку ниже, чтобы начать:
        """
    else:
        text = f"""
👋 *Xush kelibsiz, {user_name}!*

🔥 *Kaloriya Tracker Pro*
✨ Powered by Gemini 3.5 Flash

📊 *Imkoniyatlar:*
• 🍔 AI bilan kaloriya hisoblash
• 💧 Suv ichish trackeri
•  Mashg'ulotlarni kuzatish
• 📈 Chiroyli statistika
• 💡 AI dietolog maslahatlari
• ⚖️ Vazn monitoringi

🎯 *Maqsadingiz sari birinchi qadam!*

Quyidagi tugmani bosing va boshlang:
        """
    
    await update.message.reply_text(
        text, 
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    
    logger.info(f"Start message sent to {user_id}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if is_admin(user_id):
        text = """
📱 *Foydalanuvchi buyruqlar:*
/start - Boshlash
/help - Yordam

👨‍💼 *Admin buyruqlar:*
/admin - Admin panel
/users - Foydalanuvchilar ro'yxati
/block <id> - Bloklash
/unblock <id> - Blokdan chiqarish
/broadcast <xabar> - Hammaga xabar yuborish
        """
    else:
        text = """
 *Buyruqlar:*
/start - Boshlash
/help - Yordam
        """
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not is_admin(user_id):
        await update.message.reply_text(" Siz admin emassiz!")
        return
    
    with app.app_context():
        total_users = User.query.count()
        food_count = FoodLog.query.count()
    
    text = f"""
👨💼 *Admin Panel*

📊 *Statistika:*
• Jami foydalanuvchilar: {total_users}
• Jami ovqatlar: {food_count}

 *Web Admin Panel:*
{WEB_APP_URL}/admin
    """
    
    keyboard = [[InlineKeyboardButton("📊 Admin Panel", url=f"{WEB_APP_URL}/admin")]]
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Siz admin emassiz!")
        return
    
    with app.app_context():
        users = User.query.limit(20).all()
    
    text = "👥 *Foydalanuvchilar:*\n\n"
    for i, user in enumerate(users, 1):
        text += f"{i}. {user.name} ({user.user_id})\n"
        text += f"   Vazn: {user.weight}kg | Maqsad: {user.goal}\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Siz admin emassiz!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Foydalanuvchi ID sini kiriting!")
        return
    
    with app.app_context():
        target_user = User.query.get(context.args[0])
        if target_user:
            target_user.is_blocked = True
            db.session.commit()
            await update.message.reply_text(f"✅ Foydalanuvchi {context.args[0]} bloklandi!")
        else:
            await update.message.reply_text("❌ Foydalanuvchi topilmadi!")

async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Siz admin emassiz!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Foydalanuvchi ID sini kiriting!")
        return
    
    with app.app_context():
        target_user = User.query.get(context.args[0])
        if target_user:
            target_user.is_blocked = False
            db.session.commit()
            await update.message.reply_text(f"✅ Foydalanuvchi {context.args[0]} blokdan chiqarildi!")
        else:
            await update.message.reply_text("❌ Foydalanuvchi topilmadi!")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Siz admin emassiz!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Xabar matnini kiriting!")
        return
    
    message = ' '.join(context.args)
    
    with app.app_context():
        users = User.query.all()
    
    sent_count = 0
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user.user_id,
                text=f" *Admin xabari:*\n\n{message}",
                parse_mode='Markdown'
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send to {user.user_id}: {e}")
    
    await update.message.reply_text(f"✅ {sent_count}/{len(users)} foydalanuvchiga yuborildi!")

# ================= MAIN =================

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    logger.info(f" Flask on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info(" NimaYedimBot - Professional Kaloriya Tracker")
    logger.info("🗄️  Database: PostgreSQL")
    logger.info("✨ Gemini 3.5 Flash AI")
    logger.info("=" * 60)
    
    with app.app_context():
        db.create_all()
        logger.info("✅ Database tables created")
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask started")
    
    logger.info("🤖 Starting Telegram Bot...")
    
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("admin", admin_command))
        application.add_handler(CommandHandler("users", users_command))
        application.add_handler(CommandHandler("block", block_command))
        application.add_handler(CommandHandler("unblock", unblock_command))
        application.add_handler(CommandHandler("broadcast", broadcast_command))
        
        logger.info("🤖 Bot running...")
        logger.info(f"👨‍ Admin users: {ADMIN_USERS}")
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise
