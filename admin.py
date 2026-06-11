"""
Admin Panel - NimaYedimBot
User management, statistics, permissions
"""

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
import csv
import os
from datetime import datetime
from functools import wraps

admin_bp = Blueprint('admin', __name__)

# Admin users (environment variable dan olish)
ADMIN_USERS = os.getenv('ADMIN_USERS', '8402126042,6313378082').split(',')

USERS_FILE = 'data/users.csv'
FOOD_LOG_FILE = 'data/food_log.csv'

def admin_required(f):
    """Admin huquqini tekshirish"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = request.args.get('user_id') or session.get('user_id')
        if user_id not in ADMIN_USERS:
            return jsonify({'error': 'Admin huquqi yo\'q'}), 403
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/admin')
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    return render_template('admin.html')

@admin_bp.route('/api/admin/users')
@admin_required
def get_all_users():
    """Barcha foydalanuvchilar"""
    users = []
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            users = list(reader)
    
    # Statistika
    total_users = len(users)
    
    # Bugungi faol foydalanuvchilar
    today = datetime.now().strftime('%Y-%m-%d')
    food_log = []
    if os.path.exists(FOOD_LOG_FILE):
        with open(FOOD_LOG_FILE, 'r', encoding='utf-8') as f:
            food_log = list(csv.DictReader(f))
    
    active_today = len(set([f['user_id'] for f in food_log if f['timestamp'].startswith(today)]))
    
    return jsonify({
        'users': users,
        'total_users': total_users,
        'active_today': active_today
    })

@admin_bp.route('/api/admin/user/<user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """Foydalanuvchini o'chirish"""
    users = []
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            users = list(csv.DictReader(f))
    
    users = [u for u in users if u['user_id'] != user_id]
    
    with open(USERS_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['user_id', 'name', 'weight', 'height', 'age', 'gender', 'goal', 'daily_calorie_norm', 'profile_pic'])
        writer.writeheader()
        writer.writerows(users)
    
    return jsonify({'success': True})

@admin_bp.route('/api/admin/user/<user_id>/block', methods=['POST'])
@admin_required
def block_user(user_id):
    """Foydalanuvchini bloklash"""
    # Blocked users faylga yozish
    with open('data/blocked_users.txt', 'a') as f:
        f.write(f"{user_id}\n")
    return jsonify({'success': True})

@admin_bp.route('/api/admin/statistics')
@admin_required
def get_statistics():
    """Umumiy statistika"""
    users = []
    food_log = []
    weight_log = []
    
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            users = list(csv.DictReader(f))
    
    if os.path.exists(FOOD_LOG_FILE):
        with open(FOOD_LOG_FILE, 'r', encoding='utf-8') as f:
            food_log = list(csv.DictReader(f))
    
    # Umumiy kaloriya
    total_calories = sum(int(f['calories']) for f in food_log)
    
    # Eng ko'p yeyilgan ovqatlar
    food_count = {}
    for f in food_log:
        food_count[f['food_name']] = food_count.get(f['food_name'], 0) + 1
    
    top_foods = sorted(food_count.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return jsonify({
        'total_users': len(users),
        'total_food_logs': len(food_log),
        'total_calories': total_calories,
        'top_foods': top_foods
    })
