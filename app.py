from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import create_access_token, JWTManager, jwt_required, get_jwt_identity
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import os
import random
import string

app = Flask(__name__)
CORS(app)

# Config - Fixed for Render Postgres
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY')

# Crash early if env vars missing so you get clear error
if not database_url:
    raise RuntimeError("DATABASE_URL is not set. Add it in Render Environment tab")
if not app.config['JWT_SECRET_KEY']:
    raise RuntimeError("JWT_SECRET_KEY is not set. Add it in Render Environment tab")

db = SQLAlchemy(app)
jwt = JWTManager(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    referral_code = db.Column(db.String(10), unique=True, nullable=False)
    referred_by = db.Column(db.String(10))
    wallet_balance = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.now)
    is_admin = db.Column(db.Boolean, default=False)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    earnings = db.Column(db.Float, default=0.0)

class Withdrawal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(50), nullable=False)
    account = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.now)

# Helper
def generate_referral_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# Routes
@app.route('/')
def home():
    return jsonify({"status": "Freshippo API running", "version": "2.3"})

@app.route('/setup', methods=['GET'])
def setup_db():
    db.create_all()
    return jsonify({"message": "Database tables created successfully", "tables": ["user", "task", "withdrawal"]})

@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    
    if not data or not data.get('phone') or not data.get('password') or not data.get('name'):
        return jsonify({"error": "Missing required fields: name, phone, password"}), 400
    
    if User.query.filter_by(phone=data['phone']).first():
        return jsonify({"error": "Phone already registered"}), 400
    
    referral_code = generate_referral_code()
    while User.query.filter_by(referral_code=referral_code).first():
        referral_code = generate_referral_code()
    
    new_user = User(
        name=data['name'],
        phone=data['phone'],
        password_hash=generate_password_hash(data['password']),
        referral_code=referral_code,
        referred_by=data.get('referral_code')
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    if new_user.referred_by:
        referrer = User.query.filter_by(referral_code=new_user.referred_by).first()
        if referrer:
            referrer.wallet_balance += 20.0
            db.session.commit()
    
    token = create_access_token(identity=str(new_user.id))
    return jsonify({
        "message": "User created successfully",
        "token": token,
        "referral_code": referral_code,
        "user_id": new_user.id,
        "wallet_balance": new_user.wallet_balance
    }), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(phone=data.get('phone')).first()
    
    if not user or not check_password_hash(user.password_hash, data.get('password')):
        return jsonify({"error": "Invalid credentials"}), 401
    
    token = create_access_token(identity=str(user.id))
    return jsonify({
        "token": token, 
        "user_id": user.id, 
        "name": user.name,
        "wallet_balance": user.wallet_balance,
        "referral_code": user.referral_code
    })

@app.route('/dashboard', methods=['GET'])
@jwt_required()
def dashboard():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    today = date.today()
    today_task = Task.query.filter_by(user_id=user_id, date=today).first()
    
    return jsonify({
        "name": user.name,
        "wallet_balance": user.wallet_balance,
        "referral_code": user.referral_code,
        "phone": user.phone,
        "today_task_completed": today_task.completed if today_task else False,
        "today_earnings": today_task.earnings if today_task else 0
    })

@app.route('/complete-task', methods=['POST'])
@jwt_required()
def complete_task():
    user_id = get_jwt_identity()
    today = date.today()
    
    existing = Task.query.filter_by(user_id=user_id, date=today).first()
    if existing and existing.completed:
        return jsonify({"error": "Task already completed today"}), 400
    
    if not existing:
        existing = Task(user_id=user_id, date=today)
        db.session.add(existing)
    
    existing.completed = True
    existing.earnings = 10.0
    
    user = User.query.get(user_id)
    user.wallet_balance += 10.0
    
    db.session.commit()
    return jsonify({"message": "Task completed", "earned": 10.0, "new_balance": user.wallet_balance})

@app.route('/withdraw', methods=['POST'])
@jwt_required()
def withdraw():
    user_id = get_jwt_identity()
    data = request.get_json()
    amount = float(data.get('amount', 0))
    
    user = User.query.get(user_id)
    if user.wallet_balance < amount:
        return jsonify({"error": "Insufficient balance"}), 400
    if amount < 100:
        return jsonify({"error": "Minimum withdrawal is 100 KES"}), 400
    
    withdrawal = Withdrawal(
        user_id=user_id,
        amount=amount,
        method=data.get('method'),
        account=data.get('account')
    )
    
    user.wallet_balance -= amount
    db.session.add(withdrawal)
    db.session.commit()
    
    return jsonify({"message": "Withdrawal request submitted", "status": "pending", "withdrawal_id": withdrawal.id})
