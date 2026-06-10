# ============================================
# FRESHIPPO PREMIUM v6.2 - FULL COMPLETE
# All 6 Features + Fixed withdraw route
# ============================================

STAGE_TARGETS = {1: 0, 2: 50, 3: 200, 4: 500, 5: 1000}

from flask_jwt_extended import JWTManager, create_access_token, decode_token, jwt_required, get_jwt_identity
from flask import Flask, request, jsonify, make_response, session, redirect
import os
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import timedelta, datetime
from decimal import Decimal
from functools import wraps

load_dotenv()

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'change-this-secret')

db_url = os.getenv('DATABASE_URL', '')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
if not db_url:
    db_url = "sqlite:///freshippo.db"

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'change-this-secret')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)

db = SQLAlchemy(app)
jwt = JWTManager(app)

# === AUTO MIGRATE ===
from sqlalchemy import text
with app.app_context():
    db.create_all()
    user_cols = [
        'balance NUMERIC(10,2) DEFAULT 0.00',
        'total_withdrawn NUMERIC(10,2) DEFAULT 0.00',
        'current_stage INTEGER DEFAULT 1',
        'stage_status VARCHAR(20) DEFAULT \'pending\'',
        'stage_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
        'language VARCHAR(10) DEFAULT \'en\'',
        'referral_code VARCHAR(20) UNIQUE',
        'referred_by INTEGER',
        'last_claim_date TIMESTAMP',
        'streak_days INTEGER DEFAULT 0'
    ]
    for col in user_cols:
        try:
            db.session.execute(text(f'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS {col}'))
            db.session.commit()
        except:
            db.session.rollback()
    
    try:
        db.session.execute(text('ALTER TABLE withdrawal ADD COLUMN IF NOT EXISTS phone VARCHAR(20)'))
        db.session.commit()
    except:
        db.session.rollback()
    
    try:
        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS stage_request (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES "user"(id),
                stage_number INTEGER NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP
            )
        '''))
        db.session.commit()
    except:
        db.session.rollback()

# === MODELS ===
import random, string

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), default='')
    language = db.Column(db.String(10), default='en')
    is_admin = db.Column(db.Boolean, default=False)
    balance = db.Column(db.Numeric(10, 2), default=0.00)
    total_withdrawn = db.Column(db.Numeric(10, 2), default=0.00)
    current_stage = db.Column(db.Integer, default=1)
    stage_status = db.Column(db.String(20), default='pending')
    stage_updated_at = db.Column(db.DateTime, server_default=db.func.now())
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    referral_code = db.Column(db.String(20), unique=True)
    referred_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    last_claim_date = db.Column(db.DateTime, nullable=True)
    streak_days = db.Column(db.Integer, default=0)

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if not self.referral_code:
            self.referral_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    price = db.Column(db.Numeric(10, 2), nullable=False)
    stock = db.Column(db.Integer, default=0)
    category = db.Column(db.String(100), default='General')
    image_url = db.Column(db.String(500), default='')

class Withdrawal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    phone = db.Column(db.String(20))
    status = db.Column(db.String(20), default='pending')
    requested_at = db.Column(db.DateTime, server_default=db.func.now())
    approved_at = db.Column(db.DateTime, nullable=True)

class StageRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    stage_number = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')
    requested_at = db.Column(db.DateTime, server_default=db.func.now())
    approved_at = db.Column(db.DateTime, nullable=True)

def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user or not user.is_admin:
            return jsonify({"msg": "Admin required"}), 403
        return fn(*args, **kwargs)
    return wrapper

with app.app_context():
    db.create_all()

@app.route('/')
def homepage():
    return '''<html><head><title>Freshippo API</title></head><body style="font-family:Poppins; text-align:center; padding:50px; background:linear-gradient(135deg,#0f0c29,#302b63,#24243e); color:white">
    <h1 style="font-size:48px">🛒 Freshippo API</h1><p>Status: <b style="color:#22c55e">LIVE</b></p>
    <p><a href="/loginpage" style="color:#a855f7;font-size:18px">Login</a> | <a href="/dashboard" style="color:#a855f7;font-size:18px">Dashboard</a></p>
    </body></html>'''

@app.route('/loginpage', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            token = create_access_token(identity=str(user.id))
            resp = make_response('<style>body{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins;text-align:center;padding:50px}</style><h1>Welcome Back!</h1><p><a href="/dashboard" style="color:#a855f7;font-size:18px">Go to Dashboard</a></p>')
            resp.set_cookie('access_token', token, httponly=True)
            return resp
        return "Error: Wrong credentials <br><a href='/loginpage'>Try again</a>"
    return "<style>body{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins}</style><h2>Login</h2><form method='POST' style='max-width:300px;margin:auto;padding:30px;background:rgba(255,255,255,0.05);border-radius:20px'><input name='email' type='email' required placeholder='Email' style='width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white'><br><input name='password' type='password' required placeholder='Password' style='width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white'><br><button style='width:100%;padding:14px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;border:none;border-radius:10px;font-weight:bold'>Sign In</button></form>"

@app.route('/logout')
def logout():
    resp = make_response(redirect('/loginpage'))
    resp.set_cookie('access_token', '', expires=0)
    return resp

@app.route('/claim')
def claim():
    token = request.cookies.get('access_token')
    if not token:
        return redirect('/loginpage')
    try:
        decoded = decode_token(token)
        user = User.query.get(decoded['sub'])
    except:
        return redirect('/loginpage')

    today = datetime.utcnow().date()
    if user.last_claim_date and user.last_claim_date.date() == today:
        return redirect('/dashboard')

    user.balance += Decimal('0.40')
    user.streak_days += 1
    user.last_claim_date = datetime.utcnow()
    
    if user.referred_by:
        ref_user = User.query.get(user.referred_by)
        if ref_user:
            ref_user.balance += Decimal('0.02')
    
    db.session.commit()
    return redirect('/dashboard')

@app.route('/settings')
@jwt_required()
def settings():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    withdrawals = Withdrawal.query.filter_by(user_id=user.id).order_by(Withdrawal.requested_at.desc()).limit(20).all()
    
    html = f'''<style>@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');body{{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:'Poppins',sans-serif;min-height:100vh}}</style>
    <div style="text-align:right;padding:20px"><a href="/dashboard" style="padding:10px 20px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;text-decoration:none;border-radius:10px">🏠 Home</a></div>
    <h2 style="text-align:center;margin:30px 0;font-size:32px">⚙️ Settings</h2>
    <div style="max-width:600px;margin:auto;padding:30px;background:rgba(255,255,255,0.05);backdrop-filter:blur(20px);border-radius:20px;border:1px solid rgba(168,85,247,0.4)">
        <h3>👤 Profile</h3>
        <form method="POST" action="/settings/update">
            <input name="name" value="{user.name}" required style="width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white">
            <input name="email" value="{user.email}" required style="width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white">
            <input name="phone" value="{user.phone}" placeholder="Phone" style="width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white">
            <button style="width:100%;padding:14px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;border:none;border-radius:10px;font-weight:bold;margin-top:10px">Update Profile</button>
        </form>
        <hr style="margin:30px 0;border-color:rgba(168,85,247,0.3)">
        <h3 id="info">📋 Withdrawal Info</h3>
        <p>• Minimum: $4.00<br>• Cooldown: 10 days<br>• Need Phone + Password<br>• Admin approval required</p>
        <hr style="margin:30px 0;border-color:rgba(168,85,247,0.3)">
        <h3 id="history">📜 Withdrawal History</h3>
        <table style="width:100%;border-collapse:collapse">
            <tr style="border-bottom:1px solid rgba(168,85,247,0.3)"><th style="padding:10px;text-align:left">Amount</th><th>Phone</th><th>Status</th><th>Date</th></tr>
    '''
    for w in withdrawals:
        status_color = '#22c55e' if w.status=='approved' else '#ffaa00'
        date_str = w.approved_at.strftime('%Y-%m-%d %H:%M') if w.approved_at else w.requested_at.strftime('%Y-%m-%d %H:%M')
        html += f'<tr style="border-bottom:1px solid rgba(255,255,255,0.1)"><td style="padding:10px">${w.amount}</td><td>{w.phone or "-"}</td><td style="color:{status_color}">{w.status}</td><td>{date_str}</td></tr>'
    html += '</table></div>'
    return html

@app.route('/settings/update', methods=['POST'])
@jwt_required()
def update_profile():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    user.name = request.form.get('name')
    user.email = request.form.get('email')
    user.phone = request.form.get('phone', '')
    db.session.commit()
    return redirect('/settings')

@app.route('/dashboard')
def dashboard():
    token = request.cookies.get('access_token')
    if not token:
        return '<h1>Please login first</h1><a href="/loginpage">Login</a>'
    try:
        decoded = decode_token(token)
        user = User.query.get(decoded['sub'])
    except:
        return '<h1>Invalid token</h1><a href="/loginpage">Login again</a>'

    last_withdrawal = Withdrawal.query.filter_by(user_id=user.id, status='approved').order_by(Withdrawal.approved_at.desc()).first()
    can_withdraw = user.balance >= 4.00 and user.streak_days >= 10

    today = datetime.utcnow().date()
    can_claim = not user.last_claim_date or user.last_claim_date.date()!= today

    claim_btn = '<a href="/claim" style="padding:14px 28px;background:linear-gradient(135deg,#22c55e,#16a34a);color:white;text-decoration:none;border-radius:12px;font-weight:600">🎁 Claim $0.40</a>' if can_claim else '<span style="color:#aaa">✓ Claimed today</span>'
    withdraw_btn = f'<a href="/withdraw" style="padding:14px 28px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;text-decoration:none;border-radius:12px;font-weight:600">💰 Request Withdrawal</a>' if can_withdraw else f'<span style="color:#ffaa00;font-size:16px">⏳ Need $4 + 10 days [{user.streak_days}/10]</span>'

    admin_btns = ''
    if user.is_admin:
        admin_btns = '<p><a href="/admin/withdrawals" style="padding:12px 20px;background:#ffaa00;color:white;text-decoration:none;border-radius:10px">💰 Approve Withdrawals</a></p><p><a href="/admin/users" style="padding:12px 20px;background:#ef4444;color:white;text-decoration:none;border-radius:10px">👥 Reset Password</a></p>'

    menu = f'''<div style="text-align:right;position:relative">
    <button onclick="document.getElementById('menu').style.display=document.getElementById('menu').style.display==='block'?'none':'block'" style="background:rgba(255,255,255,0.1);border:2px solid rgba(168,85,247,0.4);color:white;padding:12px 16px;border-radius:12px;cursor:pointer;font-size:20px">⋮</button>
    <div id="menu" style="display:none;position:absolute;right:0;top:55px;background:rgba(26,26,46,0.98);backdrop-filter:blur(20px);border:2px solid rgba(168,85,247,0.5);border-radius:15px;min-width:200px;z-index:999">
        <a href="/dashboard" style="display:block;padding:15px 20px;color:white;text-decoration:none;border-bottom:1px solid rgba(168,85,247,0.2)">🏠 Home</a>
        <a href="/settings" style="display:block;padding:15px 20px;color:white;text-decoration:none;border-bottom:1px solid rgba(168,85,247,0.2)">⚙️ Profile</a>
        <a href="/settings#history" style="display:block;padding:15px 20px;color:white;text-decoration:none;border-bottom:1px solid rgba(168,85,247,0.2)">📜 History</a>
        <a href="/settings#info" style="display:block;padding:15px 20px;color:white;text-decoration:none;border-bottom:1px solid rgba(168,85,247,0.2)">📋 Withdrawal Info</a>
        <a href="/logout" style="display:block;padding:15px 20px;color:#ff6666;text-decoration:none">🚪 Logout</a>
    </div>
    </div>'''

    return f'''<style>body{{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins;margin:0;min-height:100vh}}</style>
    <div style="max-width:900px;margin:auto;padding:20px">
    {menu}
    <div style="padding:25px;margin:20px 0;background:rgba(255,255,255,0.05);backdrop-filter:blur(20px);border-radius:20px;text-align:center">{claim_btn}</div>
    <div style="padding:25px;margin:20px 0;background:rgba(255,255,255,0.05);backdrop-filter:blur(20px);border-radius:20px">
        <h3 style="color:#a855f7">💰 Wallet</h3>
        <p>Balance: <b style="font-size:28px;color:#a855f7">${user.balance}</b></p>
        <p>Withdrawn: <b style="font-size:28px;color:#22c55e">${user.total_withdrawn}</b></p>
        {withdraw_btn}
        {admin_btns}
    </div>
    </div>'''

@app.route('/withdraw', methods=['GET', 'POST'])
@jwt_required()
def withdraw():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if request.method == 'POST':
        amount = Decimal(request.form.get('amount', '0'))
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')

        if not check_password_hash(user.password_hash, password):
            return '❌ Wrong password <br><a href="/withdraw">Try again</a>'
        if phone != user.phone:
            return '❌ Phone must match account <br><a href="/withdraw">Try again</a>'
        if amount <= 0 or amount > user.balance or amount < 4:
            return '❌ Invalid amount Min $4 <br><a href="/dashboard">Back</a>'

        withdrawal = Withdrawal(user_id=user.id, amount=amount, phone=phone)
        db.session.add(withdrawal)
        user.balance -= amount
        db.session.commit()
        return '<style>body{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins;text-align:center;padding:50px}</style><h1>✅ Request sent!</h1><p>Admin will review ${amount}</p><a href="/dashboard">Back</a>'

    return f'''<style>body{{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins}}</style>
    <div style="text-align:right;padding:20px"><a href="/dashboard" style="padding:10px 20px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;text-decoration:none;border-radius:10px">🏠 Home</a></div>
    <h2 style="text-align:center;margin:30px 0;font-size:32px">💰 Request Withdrawal</h2>
    <form method="POST" style="max-width:380px;margin:auto;padding:35px;background:rgba(255,255,255,0.05);backdrop-filter:blur(20px);border-radius:20px;border:1px solid rgba(168,85,247,0.4)">
        <p style="text-align:center;font-size:18px">Balance: <b style="color:#a855f7;font-size:24px">${user.balance}</b></p>
        <input name="amount" type="number" step="0.01" min="4" placeholder="Amount $ Min 4" required style="width:100%;padding:14px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white">
        <input name="phone" type="text" value="{user.phone}" placeholder="Confirm Phone" required style="width:100%;padding:14px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white">
        <input name="password" type="password" placeholder="Confirm Password" required style="width:100%;padding:14px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white">
        <button style="width:100%;padding:15px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;border:none;border-radius:10px;font-weight:bold;margin-top:10px">Submit Request</button>
    </form>'''

@app.route('/admin/withdrawals')
@admin_required
def admin_withdrawals():
    requests = Withdrawal.query.filter_by(status='pending').all()
    html = '<style>body{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins;padding:30px}</style><h1>💰 Withdrawal Approval</h1><table style="width:100%;border-collapse:collapse;margin-top:20px"><tr style="border-bottom:2px solid #a855f7"><th style="padding:12px">User</th><th>Amount</th><th>Phone</th><th>Requested</th><th>Action</th></tr>'
    for w in requests:
        u = User.query.get(w.user_id)
        html += f'<tr style="border-bottom:1px solid rgba(255,255,255,0.1)"><td style="padding:12px">{u.name}</td><td>${w.amount}</td><td>{w.phone}</td><td>{w.requested_at.strftime("%Y-%m-%d")}</td><td><a href="/admin/withdraw/approve/{w.id}" style="padding:8px 15px;background:#22c55e;color:white;border-radius:8px;text-decoration:none;margin-right:5px">Approve</a><a href="/admin/withdraw/reject/{w.id}" style="padding:8px 15px;background:#ef4444;color:white;border-radius:8px;text-decoration:none">Reject</a></td></tr>'
    html += '</table><br><a href="/dashboard">← Back</a>'
    return html

@app.route('/admin/withdraw/approve/<int:w_id>')
@admin_required
def approve_withdraw(w_id):
    w = Withdrawal.query.get(w_id)
    w.status = 'approved'
    w.approved_at = datetime.utcnow()
    user = User.query.get(w.user_id)
    user.total_withdrawn += w.amount
    db.session.commit()
    return redirect('/admin/withdrawals')

@app.route('/admin/withdraw/reject/<int:w_id>')
@admin_required
def reject_withdraw(w_id):
    w = Withdrawal.query.get(w_id)
    user = User.query.get(w.user_id)
    user.balance += w.amount
    w.status = 'rejected'
    db.session.commit()
    return redirect('/admin/withdrawals')

# === FEATURE 4: ADMIN RESET PASSWORD ===
@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.all()
    html = '<style>body{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins;padding:30px}</style><h1>👥 Users - Reset Password</h1><table style="width:100%;border-collapse:collapse;margin-top:20px"><tr style="border-bottom:2px solid #a855f7"><th style="padding:12px">Name</th><th>Email</th><th>Balance</th><th>Action</th></tr>'
    for u in users:
        html += f'<tr style="border-bottom:1px solid rgba(255,255,255,0.1)"><td style="padding:12px">{u.name}</td><td>{u.email}</td><td>${u.balance}</td><td><a href="/admin/reset/{u.id}" style="padding:8px 15px;background:#ffaa00;color:white;border-radius:8px;text-decoration:none">Reset to 123456</a></td></tr>'
    html += '</table><br><a href="/dashboard">← Back</a>'
    return html

@app.route('/admin/reset/<int:user_id>')
@admin_required
def reset_password(user_id):
    user = User.query.get(user_id)
    user.password_hash = generate_password_hash('123456')
    db.session.commit()
    return f'<style>body{{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins;text-align:center;padding:50px}}</style><h1>✅ Password Reset</h1><p>{user.name} password = 123456</p><a href="/admin/users">Back</a>'

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
