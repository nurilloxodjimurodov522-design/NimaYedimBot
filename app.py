from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import csv
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import google.generativeai as genai
from werkzeug.utils import secure_filename
import uuid

load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Gemini setup
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Files
USERS_FILE = 'data/users.csv'
FOOD_LOG_FILE = 'data/food_log.csv'
WEIGHT_LOG_FILE = 'data/weight_log.csv'

# Ensure data folders exist
os.makedirs('data', exist_ok=True)

def init_files():
    """Initialize CSV files"""
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
    """Read CSV file"""
    if not os.path.exists(filepath):
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)

def write_csv(filepath, data, fieldnames):
    """Write to CSV file"""
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

def calculate_daily_norm(weight, height, age, gender, goal):
    """Calculate daily calorie norm using Mifflin-St Jeor Equation"""
    if gender == 'male':
        bmr = 10 * float(weight) + 6.25 * float(height) - 5 * float(age) + 5
    else:
        bmr = 10 * float(weight) + 6.25 * float(height) - 5 * float(age) - 161
    
    # Activity multiplier (sedentary)
    bmr *= 1.2
    
    # Goal adjustment
    if goal == 'lose':
        bmr -= 500  # Deficit for weight loss
    elif goal == 'gain':
        bmr += 500  # Surplus for weight gain
    
    return int(bmr)

# ============ API ENDPOINTS ============

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/user/<user_id>', methods=['GET'])
def get_user(user_id):
    """Get user profile"""
    users = read_csv(USERS_FILE)
    user = next((u for u in users if u['user_id'] == user_id), None)
    
    if not user:
        return jsonify({'exists': False})
    
    # Get today's food log
    today = datetime.now().strftime('%Y-%m-%d')
    food_log = read_csv(FOOD_LOG_FILE)
    today_food = [f for f in food_log if f['user_id'] == user_id and f['timestamp'].startswith(today) and f['status'] == 'approved']
    
    total_calories = sum(int(f['calories']) for f in today_food)
    
    return jsonify({
        'exists': True,
        'user': user,
        'today_calories': total_calories,
        'today_food_count': len(today_food)
    })

@app.route('/api/user', methods=['POST'])
def create_user():
    """Create new user"""
    data = request.json
    user_id = data.get('user_id')
    
    users = read_csv(USERS_FILE)
    
    # Check if user exists
    if any(u['user_id'] == user_id for u in users):
        return jsonify({'success': False, 'error': 'User already exists'})
    
    # Calculate daily norm
    daily_norm = calculate_daily_norm(
        data['weight'],
        data['height'],
        data['age'],
        data['gender'],
        data['goal']
    )
    
    new_user = {
        'user_id': user_id,
        'name': data.get('name', ''),
        'weight': data['weight'],
        'height': data['height'],
        'age': data['age'],
        'gender': data['gender'],
        'goal': data['goal'],
        'daily_calorie_norm': str(daily_norm),
        'profile_pic': data.get('profile_pic', '')
    }
    
    users.append(new_user)
    write_csv(USERS_FILE, users, ['user_id', 'name', 'weight', 'height', 'age', 'gender', 'goal', 'daily_calorie_norm', 'profile_pic'])
    
    return jsonify({'success': True, 'daily_norm': daily_norm})

@app.route('/api/user/<user_id>', methods=['PUT'])
def update_user(user_id):
    """Update user profile"""
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
            
            # Recalculate norm if needed
            if all(k in data for k in ['weight', 'height', 'age', 'gender', 'goal']):
                users[i]['daily_calorie_norm'] = str(calculate_daily_norm(
                    data['weight'], data['height'], data['age'], data['gender'], data['goal']
                ))
            
            write_csv(USERS_FILE, users, ['user_id', 'name', 'weight', 'height', 'age', 'gender', 'goal', 'daily_calorie_norm', 'profile_pic'])
            return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'User not found'})

@app.route('/api/food/check', methods=['POST'])
def check_food():
    """Check food calories without saving"""
    data = request.json
    food = data.get('food')
    
    try:
        response = model.generate_content(f"{food} ning kaloriyasi nechta? Faqat raqam va kcal bilan javob bering. Masalan: '250 kcal'")
        return jsonify({'success': True, 'calorie': response.text})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/food/log', methods=['POST'])
def log_food():
    """Log food with photo"""
    data = request.json
    user_id = data.get('user_id')
    food_name = data.get('food_name')
    photo = data.get('photo', '')
    
    try:
        # Get calories from AI
        prompt = f"{food_name} ning kaloriyasi nechta? Faqat raqam qismini yozing (masalan: 250)."
        response = model.generate_content(prompt)
        calories = int(''.join(filter(str.isdigit, response.text)))
        
        # Get details from AI
        details_response = model.generate_content(f"{food_name} tarkibi va kaloriya manbaini tushuntiring (qisqa).")
        details = details_response.text
        
        # Create log
        food_log = read_csv(FOOD_LOG_FILE)
        log_id = str(uuid.uuid4())
        
        new_log = {
            'log_id': log_id,
            'user_id': user_id,
            'food_name': food_name,
            'calories': str(calories),
            'details': details,
            'photo': photo,
            'status': 'pending',  # pending, approved, rejected
            'timestamp': datetime.now().isoformat()
        }
        
        food_log.append(new_log)
        write_csv(FOOD_LOG_FILE, food_log, ['log_id', 'user_id', 'food_name', 'calories', 'details', 'photo', 'status', 'timestamp'])
        
        return jsonify({'success': True, 'log_id': log_id, 'calories': calories, 'details': details})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/food/approve/<log_id>', methods=['POST'])
def approve_food(log_id):
    """Approve food log"""
    food_log = read_csv(FOOD_LOG_FILE)
    
    for i, log in enumerate(food_log):
        if log['log_id'] == log_id:
            food_log[i]['status'] = 'approved'
            write_csv(FOOD_LOG_FILE, food_log, ['log_id', 'user_id', 'food_name', 'calories', 'details', 'photo', 'status', 'timestamp'])
            return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Log not found'})

@app.route('/api/food/reject/<log_id>', methods=['POST'])
def reject_food(log_id):
    """Reject food log"""
    food_log = read_csv(FOOD_LOG_FILE)
    
    for i, log in enumerate(food_log):
        if log['log_id'] == log_id:
            food_log[i]['status'] = 'rejected'
            write_csv(FOOD_LOG_FILE, food_log, ['log_id', 'user_id', 'food_name', 'calories', 'details', 'photo', 'status', 'timestamp'])
            return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Log not found'})

@app.route('/api/food/history/<user_id>', methods=['GET'])
def get_food_history(user_id):
    """Get user's food history"""
    food_log = read_csv(FOOD_LOG_FILE)
    user_logs = [log for log in food_log if log['user_id'] == user_id]
    
    # Sort by timestamp descending
    user_logs.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return jsonify(user_logs)

@app.route('/api/food/today/<user_id>', methods=['GET'])
def get_today_food(user_id):
    """Get today's approved food"""
    today = datetime.now().strftime('%Y-%m-%d')
    food_log = read_csv(FOOD_LOG_FILE)
    
    today_food = [
        log for log in food_log 
        if log['user_id'] == user_id and log['timestamp'].startswith(today) and log['status'] == 'approved'
    ]
    
    total_calories = sum(int(log['calories']) for log in today_food)
    
    return jsonify({
        'food': today_food,
        'total_calories': total_calories,
        'count': len(today_food)
    })

@app.route('/api/weight/log', methods=['POST'])
def log_weight():
    """Log weight measurement"""
    data = request.json
    user_id = data.get('user_id')
    weight = data.get('weight')
    
    weight_log = read_csv(WEIGHT_LOG_FILE)
    log_id = str(uuid.uuid4())
    
    new_log = {
        'log_id': log_id,
        'user_id': user_id,
        'weight': weight,
        'timestamp': datetime.now().isoformat()
    }
    
    weight_log.append(new_log)
    write_csv(WEIGHT_LOG_FILE, weight_log, ['log_id', 'user_id', 'weight', 'timestamp'])
    
    # Get previous weight
    user_logs = [log for log in weight_log if log['user_id'] == user_id]
    user_logs.sort(key=lambda x: x['timestamp'], reverse=True)
    
    change = None
    if len(user_logs) > 1:
        prev_weight = float(user_logs[1]['weight'])
        change = float(weight) - prev_weight
    
    return jsonify({
        'success': True,
        'change': change,
        'previous_weight': user_logs[1]['weight'] if len(user_logs) > 1 else None
    })

@app.route('/api/weight/history/<user_id>', methods=['GET'])
def get_weight_history(user_id):
    """Get user's weight history"""
    weight_log = read_csv(WEIGHT_LOG_FILE)
    user_logs = [log for log in weight_log if log['user_id'] == user_id]
    
    user_logs.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return jsonify(user_logs)

@app.route('/api/recommendations/<user_id>', methods=['GET'])
def get_recommendations(user_id):
    """Get AI-powered recommendations"""
    users = read_csv(USERS_FILE)
    user = next((u for u in users if u['user_id'] == user_id), None)
    
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})
    
    # Get weight history
    weight_log = read_csv(WEIGHT_LOG_FILE)
    user_weights = [log for log in weight_log if log['user_id'] == user_id]
    user_weights.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Get today's food
    today = datetime.now().strftime('%Y-%m-%d')
    food_log = read_csv(FOOD_LOG_FILE)
    today_food = [
        log for log in food_log 
        if log['user_id'] == user_id and log['timestamp'].startswith(today) and log['status'] == 'approved'
    ]
    
    total_calories = sum(int(log['calories']) for log in today_food)
    daily_norm = int(user['daily_calorie_norm'])
    
    # Generate recommendation
    try:
        weight_change = ""
        if len(user_weights) >= 2:
            diff = float(user_weights[0]['weight']) - float(user_weights[1]['weight'])
            if diff > 0:
                weight_change = f"Oxirgi o'lchovda {abs(diff):.1f} kg kamaydingiz. "
            elif diff < 0:
                weight_change = f"Oxirgi o'lchovda {abs(diff):.1f} kg ko'paydingiz. "
        
        prompt = f"""
        Foydalanuvchi ma'lumotlari:
        - Vazn: {user['weight']} kg
        - Bo'y: {user['height']} cm
        - Yosh: {user['age']}
        - Maqsad: {user['goal']} (lose=gain weight, gain=lose weight)
        - Kunlik norma: {daily_norm} kcal
        - Bugun yegan: {total_calories} kcal
        - {weight_change}
        
        Qisqa tavsiya bering (2-3 gap). O'zbek tilida.
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

if __name__ == '__main__':
    init_files()  # ✅ Tuzatildi: init_csv() emas, init_files()
    
    # Railway bergan portni olish, agar bo'lmasa 5000 dan foydalanish
    port = int(os.environ.get('PORT', 5000))
    
    print(f"🚀 Server ishga tushmoqda: http://0.0.0.0:{port}")
    
    # Muhim: host='0.0.0.0' bo'lishi shart!
    app.run(host='0.0.0.0', port=port, debug=False)
