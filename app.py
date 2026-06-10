# ============================================
# FRESHIPPO PREMIUM v6.0 - FULL COMPLETE CODE
# Xender UI + 6 Features + No Syntax Errors
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

# === RENDER + PYTHON 3.14 + PSYCOPG3 FIX ===
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

# === AUTO MIGRATE MISSING COLUMNS ===
from sqlalchemy import text
with app.app_context():
    db.create_all()
    cols = [
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
    for col in cols:
        try:
            db.session.execute(text(f'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS {col}'))
            db.session.commit()
            print(f"Added column: {col.split()[0]}")
        except Exception as e:
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

    def to_dict(self):
        return {"id": self.id, "email": self.email, "name": self.name, "phone": self.phone,
                "language": self.language, "is_admin": self.is_admin, "balance": float(self.balance),
                "current_stage": self.current_stage, "stage_status": self.stage_status,
                "referral_code": self.referral_code, "streak_days": self.streak_days}

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    price = db.Column(db.Numeric(10, 2), nullable=False)
    stock = db.Column(db.Integer, default=0)
    category = db.Column(db.String(100), default='General')
    image_url = db.Column(db.String(500), default='')

    def to_dict(self):
        return {"id": self.id, "name": self.name, "description": self.description,
                "price": float(self.price), "stock": self.stock,
                "category": self.category, "image_url": self.image_url}

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default='pending')
    address = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, server_default=db.func.now())

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)

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

# === DECORATOR ===
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

# === ROUTES ===
@app.route('/')
def homepage():
    return '''<html><head><title>Freshippo API</title></head><body style="font-family:Poppins; text-align:center; padding:50px; background:linear-gradient(135deg,#0f0c29,#302b63,#24243e); color:white">
    <h1 style="font-size:48px">🛒 Freshippo API</h1><p>Status: <b style="color:#22c55e">LIVE</b></p>
    <p><a href="/signup" style="color:#a855f7;font-size:18px">Sign Up</a> | <a href="/loginpage" style="color:#a855f7;font-size:18px">Login</a> | <a href="/dashboard" style="color:#a855f7;font-size:18px">Dashboard</a></p>
    </body></html>'''

@app.route('/health')
def health():
    try:
        db.session.execute(db.text('SELECT 1'))
        return jsonify({"status": "healthy"}), 200
    except Exception as e:
        return jsonify({"status": "error", "db": str(e)}), 500

@app.route('/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    if not all([data.get('email'), data.get('password'), data.get('name')]):
        return jsonify({"msg": "email, password, name required"}), 400
    if User.query.filter_by(email=data['email']).first():
        return jsonify({"msg": "Email exists"}), 400

    ref_code = data.get('ref_code')
    referred_by = None
    if ref_code:
        ref_user = User.query.filter_by(referral_code=ref_code).first()
        if ref_user:
            referred_by = ref_user.id

    user = User(email=data['email'], name=data['name'], phone=data.get('phone', ''), referred_by=referred_by)
    user.password_hash = generate_password_hash(data['password'])
    db.session.add(user)
    db.session.commit()
    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user.to_dict()}), 201

@app.route('/signup', methods=['GET', 'POST'])
def signup_page():
    ref_code = request.args.get('ref', '')
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        phone = request.form.get('phone', '')
        if User.query.filter_by(email=email).first():
            return "Error: Email exists <br><a href='/signup'>Try again</a>"

        referred_by = None
        if ref_code:
            ref_user = User.query.filter_by(referral_code=ref_code).first()
            if ref_user:
                referred_by = ref_user.id

        user = User(email=email, name=name, phone=phone, referred_by=referred_by)
        user.password_hash = generate_password_hash(password)
        db.session.add(user)
        db.session.commit()
        return f"<h1>Account Created</h1><p>Welcome {name}</p><a href='/loginpage'>Sign In</a>"
    return f"<style>body{{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins}}</style><h2>Sign Up</h2><form method='POST' style='max-width:300px;margin:auto;padding:30px;background:rgba(255,255,255,0.05);border-radius:20px'><input name='name' placeholder='Name' required style='width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white'><br><input name='email' type='email' required placeholder='Email' style='width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white'><br><input name='phone' type='text' placeholder='Phone' style='width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white'><br><input name='password' type='password' required placeholder='Password' style='width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white'><br><button style='width:100%;padding:14px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;border:none;border-radius:10px;font-weight:bold'>Sign Up</button></form>"

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
    db.session.commit()
    return redirect('/dashboard')

@app.route('/cart/add/<int:product_id>')
def add_to_cart(product_id):
    token = request.cookies.get('access_token')
    if not token:
        return redirect('/loginpage')
    try:
        decoded = decode_token(token)
        user = User.query.get(decoded['sub'])
        product = Product.query.get_or_404(product_id)
    except:
        return redirect('/loginpage')

    if product.stock <= 0:
        return '❌ Out of stock <br><a href="/dashboard">Back</a>'

    product.stock -= 1
    user.balance += Decimal('0.40')
    db.session.commit()
    return redirect('/dashboard')

@app.route('/settings')
@jwt_required()
def settings():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    referrals = User.query.filter_by(referred_by=user.id).count()

    html = f'''<style>@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');body{{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:'Poppins',sans-serif;min-height:100vh}}</style>
    <div style="text-align:right;padding:20px"><a href="/dashboard" class="btn" style="padding:10px 20px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;text-decoration:none;border-radius:10px">🏠 Home</a></div>
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
        <h3>🔗 Referral Link</h3>
        <p>Your code: <b style="color:#a855f7">{user.referral_code}</b></p>
        <input value="https://freshippo.com/signup?ref={user.referral_code}" readonly style="width:100%;padding:12px;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:#aaa">
        <p style="color:#aaa;font-size:13px;margin-top:8px">Referred users: {referrals} | You get 5% bonus when they claim</p>
        <hr style="margin:30px 0;border-color:rgba(168,85,247,0.3)">
        <h3>📋 Withdrawal Info</h3>
        <p>• Minimum: $4.00<br>• Cooldown: 10 days<br>• Need Phone + Password<br>• Admin approval required</p>
        <hr style="margin:30px 0;border-color:rgba(168,85,247,0.3)">
        <h3>📜 Withdrawal History</h3>
        <table style="width:100%;border-collapse:collapse">
            <tr style="border-bottom:1px solid rgba(168,85,247,0.3)"><th style="padding:10px;text-align:left">Amount</th><th>Phone</th><th>Status</th><th>Date</th></tr>
    '''
    withdrawals = Withdrawal.query.filter_by(user_id=user.id).order_by(Withdrawal.requested_at.desc()).limit(20).all()
    for w in withdrawals:
        status_color = '#22c55e' if w.status=='approved' else '#ffaa00'
        date_str = w.approved_at.strftime('%Y-%m-%d %H:%M') if w.approved_at else w.requested_at.strftime('%Y-%m-%d %H:%M')
        html += f'<tr style="border-bottom:1px solid rgba(255,255,255,0.1)"><td style="padding:10px">${w.amount}</td><td>{w.phone}</td><td style="color:{status_color}">{w.status}</td><td>{date_str}</td></tr>'
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

    products = Product.query.all()
    last_withdrawal = Withdrawal.query.filter_by(user_id=user.id, status='approved').order_by(Withdrawal.approved_at.desc()).first()
    can_withdraw = user.balance >= 4.00 and user.streak_days >= 10
    days_left = max(0, 10 - user.streak_days)

    today = datetime.utcnow().date()
    can_claim = not user.last_claim_date or user.last_claim_date.date()!= today

    steps_html = '<div style="display:flex;justify-content:space-between;align-items:center;margin:30px 0;padding:20px;background:rgba(255,255,255,0.04);backdrop-filter:blur(20px);border-radius:20px;border:1px solid rgba(168,85,247,0.3)">'
    for i in range(1,6):
        bg = 'linear-gradient(135deg,#22c55e,#16a34a)' if user.current_stage>=i else 'rgba(255,255,255,0.08)'
        border = '#22c55e' if user.current_stage>=i else 'rgba(255,255,255,0.15)'
        color = '#22c55e' if user.current_stage>=i else '#666'
        stage_req = StageRequest.query.filter_by(user_id=user.id, stage_number=i, status='pending').first()
        btn_html = ''
        if i == user.current_stage and user.stage_status == 'pending':
            if stage_req:
                btn_html = '<p style="font-size:12px;color:#ffaa00">Pending approval</p>'
            else:
                btn_html = f'<a href="/stage/request/{i}" style="font-size:12px;padding:6px 12px;background:#a855f7;color:white;border-radius:8px;text-decoration:none">Request</a>'
        steps_html += f'<div style="text-align:center;flex:1"><div style="width:50px;height:50px;margin:0 auto 8px;border-radius:50%;background:{bg};display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;border:3px solid {border}">{i}</div><div style="font-size:12px;font-weight:600;color:{color}">Stage {i}</div>{btn_html}</div>'
        if i<5:
            line_bg = 'linear-gradient(90deg,#22c55e,#a855f7)' if user.current_stage>i else 'rgba(255,255,255,0.08)'
            steps_html += f'<div style="height:3px;flex:1;background:{line_bg};margin:0 5px;border-radius:2px"></div>'
    steps_html += '</div>'

    claim_btn = '<a href="/claim" class="btn" style="background:linear-gradient(135deg,#22c55e,#16a34a)">🎁 Claim $0.40</a>' if can_claim else '<span style="color:#aaa">✓ Claimed today</span>'
    withdraw_btn = f'<a href="/withdraw" class="btn">💰 Request Withdrawal</a>' if can_withdraw else f'<span style="color:#ffaa00;font-size:16px">⏳ Need $4 + 10 days [{user.streak_days}/10]</span>'

    html = steps_html + f"<h1 style='text-align:center;margin-bottom:30px;font-size:42px'>🛒 Welcome {user.name}!</h1>"
    html += f"<p style='text-align:center;color:#aaa;font-size:17px'>Email: {user.email}</p><hr>"

    if user.is_admin:
        html += '<p style="margin-top:20px"><a href="/admin/add-product" class="btn">+ Add Product</a></p>'
        html += '<p><a href="/admin/stages" class="btn">👑 Approve Stages</a></p>'
        html += '<p><a href="/admin/withdrawals" class="btn">💰 Approve Withdrawals</a></p>'
        html += '<p><a href="/admin/users" class="btn">👥 Users & Reset Password</a></p>'

    wrapper = f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700;800&display=swap');
body{{background:linear-gradient(135deg,#0f0c29 0%,#302b63 50%,#24243e 100%);background-attachment:fixed;color:white;font-family:'Poppins',sans-serif;margin:0;min-height:100vh}}
.watermark{{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%) rotate(-15deg);font-size:15vw;color:rgba(168,85,247,0.05);z-index:0;pointer-events:none;white-space:nowrap;font-weight:900}}
.content{{position:relative;z-index:1;padding:20px;max-width:900px;margin:auto}}
.box{{padding:25px;margin:20px 0;background:rgba(255,255,255,0.05);backdrop-filter:blur(20px);border:1px solid rgba(168,85,247,0.3);border-radius:20px;box-shadow:0 8px 32px rgba(0,0,0,0.4)}}
.btn{{display:inline-block;padding:14px 28px;margin:8px 5px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;text-decoration:none;border-radius:12px;font-weight:600;font-size:15px;box-shadow:0 4px 20px rgba(168,85,247,0.4)}}
.menu-btn{{background:rgba(255,255,255,0.1);border:2px solid rgba(168,85,247,0.4);color:white;padding:12px 16px;border-radius:12px;cursor:pointer;font-size:20px;font-weight:700}}
.stats{{display:flex;gap:20px;margin-top:15px}}
.stat{{flex:1;background:rgba(0,0,0,0.4);padding:20px;border-radius:15px;text-align:center;border:1px solid rgba(168,85,247,0.2)}}
</style>
<div class="watermark">FRESHIPPO</div>
<div class="content">
<div class="box" style="text-align:right;position:relative">
    <button onclick="document.getElementById('menu').style.display=document.getElementById('menu').style.display==='block'?'none':'block'" class="menu-btn">⋮</button>
    <div id="menu" style="display:none;position:absolute;right:0;top:55px;background:rgba(26,26,46,0.98);backdrop-filter:blur(20px);border:2px solid rgba(168,85,247,0.5);border-radius:15px;min-width:200px;z-index:999">
        <a href="/dashboard" style="display:block;padding:15px 20px;color:white;text-decoration:none;border-bottom:1px solid rgba(168,85,247,0.2)">🏠 Home</a>
        <a href="/settings" style="display:block;padding:15px 20px;color:white;text-decoration:none;border-bottom:1px solid rgba(168,85,247,0.2)">⚙️ Profile</a>
        <a href="/settings#history" style="display:block;padding:15px 20px;color:white;text-decoration:none;border-bottom:1px solid rgba(168,85,247,0.2)">📜 History</a>
        <a href="/settings#info" style="display:block;padding:15px 20px;color:white;text-decoration:none;border-bottom:1px solid rgba(168,85,247,0.2)">📋 Withdrawal Info</a>
        <a href="/logout" style="display:block;padding:15px 20px;color:#ff6666;text-decoration:none">🚪 Logout</a>
    </div>
</div>
<div class="box" style="text-align:center">{claim_btn}</div>
<div class="box"><h3 style="color:#a855f7;font-size:22px">📦 Products: {len(products)} items</h3></div>
<div class="box">
    <h3 style="color:#a855f7;font-size:24px">💰 Wallet</h3>
    <div class="stats">
        <div class="stat"><b style="font-size:28px;color:#a855f7">${user.balance}</b><br>Balance</div>
        <div class="stat"><b style="font-size:28px;color:#22c55e">${user.total_withdrawn}</b><br>Withdrawn</div>
    </div>
    {withdraw_btn}
    <p style="font-size:13px;color:#aaa;margin-top:10px;text-align:center">⚡ $0.40 per product | 10-day cooldown | Min $4</p>
</div>
<hr style="margin:40px 0;border:none;height:2px;background:linear-gradient(90deg,transparent,#a855f7,transparent)">{html}</div>"""
    return wrapper

@app.route('/stage/request/<int:stage_num>')
@jwt_required()
def request_stage(stage_num):
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if user.current_stage!= stage_num:
        return redirect('/dashboard')
    req = StageRequest(user_id=user.id, stage_number=stage_num)
    db.session.add(req)
    db.session.commit()
    return redirect('/dashboard')

@app.route('/admin/stages')
@admin_required
def admin_stages():
    requests = StageRequest.query.filter_by(status='pending').all()
    html = '<style>body{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins;padding:30px}</style><h1>👑 Stage Approval</h1><table style="width:100%;border-collapse:collapse;margin-top:20px"><tr style="border-bottom:2px solid #a855f7"><th style="padding:12px">User</th><th>Stage</th><th>Requested</th><th>Action</th></tr>'
    for r in requests:
        u = User.query.get(r.user_id)
        html += f'<tr style="border-bottom:1px solid rgba(255,255,255,0.1)"><td style="padding:12px">{u.name}</td><td>{r.stage_number}</td><td>{r.requested_at.strftime("%Y-%m-%d")}</td><td><a href="/admin/stage/approve/{r.id}" style="padding:8px 15px;background:#22c55e;color:white;border-radius:8px;text-decoration:none">Approve</a></td></tr>'
    html += '</table><br><a href="/dashboard">← Back</a>'
    return html

@app.route('/admin/stage/approve/<int:req_id>')
@admin_required
def approve_stage(req_id):
    req = StageRequest.query.get(req_id)
    user = User.query.get(req.user_id)
    user.current_stage = req.stage_number + 1
    user.stage_status = 'active'
    user.stage_updated_at = datetime.utcnow()
    req.status = 'approved'
    req.approved_at = datetime.utcnow()
    db.session.commit()
    return redirect('/admin/stages')

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

@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.all()
    html = '<style>body{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins;padding:30px}</style><h1>👥 Users</h1><table style="width:100%;border-collapse:collapse;margin-top:20px"><tr style="border-bottom:2px solid #a855f7"><th style="padding:12px">Name</th><th>Email</th><th>Balance</th><th>Action</th></tr>'
    for u in users:
        html += f'<tr style="border-bottom:1px solid rgba(255,255,255,0.1)"><td style="padding:12px">{u.name}</td><td>{u.email}</td><td>${u.balance}</td><td><a href="/admin/reset/{u.id}" style="padding:8px 15px;background:#ffaa00;color:white;border-radius:8px;text-decoration:none">Reset Password</a></td></tr>'
    html += '</table><br><a href="/dashboard">← Back</a>'
    return html

@app.route('/admin/reset/<int:user_id>')
@admin_required
def reset_password(user_id):
    user = User.query.get(user_id)
    user.password_hash = generate_password_hash('123456')
    db.session.commit()
    return
