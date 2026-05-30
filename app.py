from flask import Flask, render_template, request, jsonify
import os
import csv
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

app = Flask(__name__)

# Gemini sozlamalari
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-3.5-flash')
else:
    model = None

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/people', methods=['GET'])
def get_people():
    try:
        data = read_csv()
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/add', methods=['POST'])
def add_person():
    try:
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
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/delete/<id>', methods=['DELETE'])
def delete_person(id):
    try:
        people = read_csv()
        new_people = [p for p in people if p['id'] != id]
        write_csv(new_people)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/calorie', methods=['POST'])
def calculate_calorie():
    try:
        food = request.json.get('food')
        if not model:
            return jsonify({'success': False, 'error': 'Gemini API key not set'}), 500
        
        response = model.generate_content(f"{food} kaloriyasi nechta? Faqat raqam va kcal.")
        return jsonify({'success': True, 'calorie': response.text})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    init_csv()
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Server ishga tushmoqda: http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)
