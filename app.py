# ============================================
# FRESHIPPO PREMIUM v6.5 - FIXED 100% COMPLETE
# Settings Tabs + Withdraw Form + History + Tappable Stages + Admin Dashboard
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
    return "<style>body{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins}</style><h2>Login</h2><form method='POST' style='max-width:300px;margin:auto;padding:30px;background:rgba(255,255,255,0.05);border-radius:20px'><input name='email' type='email' required placeholder='Email' style='width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white'><br><input name='password' type='password' required placeholder='Password' style='width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white'><br><button style='width:100%;padding:14px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;border:none;border-radius:10px;font-weight:bold'>Sign In</button><p style='text-align:center;margin-top:15px'>Don't have account? <a href='/signup' style='color:#a855f7'>Sign Up</a></p></form>"

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        ref_code = request.form.get('referral_code', '')

        if User.query.filter_by(email=email).first():
            return "Email exists <br><a href='/signup'>Try again</a>"

        referred_by = None
        if ref_code:
            ref_user = User.query.filter_by(referral_code=ref_code).first()
            if ref_user: referred_by = ref_user.id

        user = User(email=email, name=name, password_hash=generate_password_hash(password), referred_by=referred_by)
        db.session.add(user)
        db.session.commit()
        return f'<h1>✅ Account Created!</h1><p>Code: {user.referral_code}</p><a href="/loginpage">Login</a>'

    return f'''<style>body{{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins}}</style>
    <div style="max-width:400px;margin:50px auto;padding:30px;background:rgba(255,255,255,0.05);border-radius:20px">
    <h2>Sign Up</h2>
    <form method="POST">
        <input name="name" placeholder="Full Name" required style="width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white">
        <input name="email" type="email" placeholder="Email" required style="width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white">
        <input name="password" type="password" placeholder="Password" required style="width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white">
        <input name="referral_code" value="{request.args.get('ref', '')}" placeholder="Referral Code - Optional" style="width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white">
        <button style="width:100%;padding:14px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;border:none;border-radius:10px">Create Account</button>
    </form>
    </div>'''

@app.route('/logout')
def logout():
    resp = make_response(redirect('/loginpage'))
    resp.set_cookie('access_token', '', expires=0)
    return resp

@app.route('/claim')
def claim():
    token = request.cookies.get('access_token')
    if not token: return redirect('/loginpage')
    try:
        decoded = decode_token(token)
        user = User.query.get(decoded['sub'])
    except: return redirect('/loginpage')

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

# === FIXED SETTINGS WITH TABS + WITHDRAW + HISTORY + STAGES ===
@app.route('/settings', methods=['GET', 'POST'])
def settings():
    token = request.cookies.get('access_token')
    if not token: return redirect('/loginpage')
    try:
        decoded = decode_token(token)
        user = User.query.get(decoded['sub'])
    except: return redirect('/loginpage')

    withdrawals = Withdrawal.query.filter_by(user_id=user.id).order_by(Withdrawal.requested_at.desc()).limit(50).all()
    stage_requests = StageRequest.query.filter_by(user_id=user.id).order_by(StageRequest.requested_at.desc()).limit(20).all()

    if request.method == 'POST':
        user.name = request.form.get('name')
        user.email = request.form.get('email')
        user.phone = request.form.get('phone', '')
        db.session.commit()
        return redirect('/settings')

    html = f'''<style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');
    body{{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:'Poppins',sans-serif;min-height:100vh;margin:0;padding:20px}}
  .container{{max-width:700px;margin:auto}}
  .tabs{{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap}}
  .tab{{flex:1;min-width:120px;padding:12px;text-align:center;background:rgba(255,255,255,0.05);border:1px solid #333;border-radius:10px;cursor:pointer;transition:0.3s;font-weight:600}}
  .tab.active{{background:linear-gradient(135deg,#a855f7,#7c3aed);border-color:#a855f7}}
  .tab-content{{display:none}}
  .tab-content.active{{display:block}}
  .box{{background:rgba(255,255,255,0.05);backdrop-filter:blur(20px);padding:25px;border-radius:20px;border:1px solid rgba(168,85,247,0.4);margin-bottom:20px}}
    input{{width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white}}
    button{{width:100%;padding:14px;background:linear-gradient(135deg,#22c55e,#16a34a);color:white;border:none;border-radius:10px;font-weight:bold;cursor:pointer}}
    table{{width:100%;border-collapse:collapse;margin-top:15px;font-size:14px}}
    th,td{{padding:10px;border-bottom:1px solid rgba(255,255,255,0.1);text-align:left}}
    th{{background:rgba(168,85,247,0.2)}}
  .stage{{background:rgba(0,0,0,0.3);margin:10px 0;border-radius:10px;overflow:hidden;border:1px solid #333;cursor:pointer}}
  .stage-header{{padding:15px;display:flex;justify-content:space-between;align-items:center}}
  .stage-header:hover{{background:rgba(168,85,247,0.1)}}
  .stage-body{{padding:0 15px;max-height:0;overflow:hidden;transition:max-height 0.3s ease}}
  .stage.active.stage-body{{padding:15px;max-height:500px}}
  .arrow{{transition:0.3s;font-size:20px}}
  .stage.active.arrow{{transform:rotate(180deg)}}
    </style>

    <div class="container">
    <div style="text-align:right;margin-bottom:20px">
        <a href="/dashboard" style="padding:10px 20px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;text-decoration:none;border-radius:10px">🏠 Home</a>
    </div>

    <div class="tabs">
        <div class="tab active" onclick="showTab(0)">👤 Profile</div>
        <div class="tab" onclick="showTab(1)">💰 Withdraw</div>
        <div class="tab" onclick="showTab(2)">📋 History</div>
        <div class="tab" onclick="showTab(3)">ℹ️ Stages</div>
    </div>

    <div class="tab-content active">
        <div class="box">
        <h3>👤 Edit Profile</h3>
        <form method="POST">
            <input name="name" value="{user.name}" required placeholder="Full Name">
            <input name="email" value="{user.email}" required type="email">
            <input name="phone" value="{user.phone}" placeholder="Phone Number" required>
            <button>Save Changes</button>
        </form>
        </div>
    </div>

    <div class="tab-content">
        <div class="box">
        <h3>💰 Request Withdrawal</h3>
        <p><b>Balance:</b> ${user.balance:.2f} | <b>Streak:</b> {user.streak_days}/10 days</p>
        <p style="font-size:13px;color:#888;margin-bottom:15px">• Minimum: $4.00<br>• Cooldown: 10 days<br>• Admin approval required</p>
        <form method="POST" action="/withdraw">
            <input name="amount" type="number" step="0.01" min="4" placeholder="Amount $ Min 4" required>
            <input name="phone" value="{user.phone}" placeholder="Confirm Phone" required>
            <input name="password" type="password" placeholder="Confirm Password" required>
            <button>Submit Withdrawal Request</button>
        </form>
        </div>
    </div>

    <div class="tab-content">
        <div class="box">
        <h3>📜 Withdrawal History</h3>
        <table>
            <tr><th>Amount</th><th>Phone</th><th>Status</th><th>Date</th></tr>'''

    if withdrawals:
        for w in withdrawals:
            status_color = '#22c55e' if w.status=='approved' else '#ffaa00' if w.status=='pending' else '#ef4444'
            date_str = w.approved_at.strftime('%Y-%m-%d %H:%M') if w.approved_at else w.requested_at.strftime('%Y-%m-%d %H:%M')
            html += f'<tr><td>${w.amount}</td><td>{w.phone or "-"}</td><td style="color:{status_color};font-weight:600">{w.status.upper()}</td><td>{date_str}</td></tr>'
    else:
        html += '<tr><td colspan="4" style="text-align:center;padding:30px;color:#888">No withdrawal history yet</td></tr>'

    html += '''</table>
        </div>

        <div class="box">
        <h3>🎯 Stage Requests History</h3>
        <table>
            <tr><th>Stage</th><th>Status</th><th>Requested</th><th>Approved</th></tr>'''

    if stage_requests:
        for s in stage_requests:
            status_color = '#22c55e' if s.status=='approved' else '#ffaa00'
            req_date = s.requested_at.strftime('%Y-%m-%d %H:%M')
            app_date = s.approved_at.strftime('%Y-%m-%d %H:%M') if s.approved_at else '-'
            html += f'<tr><td>Stage {s.stage_number}</td><td style="color:{status_color};font-weight:600">{s.status.upper()}</td><td>{req_date}</td><td>{app_date}</td></tr>'
    else:
        html += '<tr><td colspan="4" style="text-align:center;padding:30px;color:#888">No stage requests yet</td></tr>'

    html += '''</table>
        </div>
    </div>

    <div class="tab-content">
        <div class="box">
        <h3>ℹ️ Stages Info - Tap to Expand</h3>'''

    stages_info = [
        (1, "Stage 1: Starter", f"Target: ${STAGE_TARGETS[1]}. Free to start. Claim $0.40 daily."),
        (2, "Stage 2: Bronze", f"Target: ${STAGE_TARGETS[2]}. Unlock by balance. Higher rewards."),
        (3, "Stage 3: Silver", f"Target: ${STAGE_TARGETS[3]}. Better bonuses + referrals."),
        (4, "Stage 4: Gold", f"Target: ${STAGE_TARGETS[4]}. VIP support + fast withdrawals."),
        (5, "Stage 5: Diamond", f"Target: ${STAGE_TARGETS[5]}. Maximum rewards + exclusive.")
    ]

    for stage_num, title, desc in stages_info:
        html += f'''
        <div class="stage" onclick="toggleStage(this)">
            <div class="stage-header">
                <b>{title}</b>
                <span class="arrow">▼</span>
            </div>
            <div class="stage-body">
                <p>{desc}</p>
                <p style="color:#888;font-size:13px">Current: Stage {user.current_stage} | Your Balance: ${user.balance:.2f}</p>
            </div>
        </div>'''

    html += '''</div>
    </div>
    </div>

    <script>
    function showTab(n){
        document.querySelectorAll('.tab').forEach((t,i)=>t.classList.toggle('active',i==n));
        document.querySelectorAll('.tab-content').forEach((c,i)=>c.classList.toggle('active',i==n));
    }
    function toggleStage(el){
        el.classList.toggle('active');
    }
    </script>'''

    return html

@app.route('/request_stage/<int:stage>')
def request_stage(stage):
    token = request.cookies.get('access_token')
    if not token: return redirect('/loginpage')
    try:
        decoded = decode_token(token)
        user = User.query.get(decoded['sub'])
    except: return redirect('/loginpage')

    if user.current_stage >= stage:
        return f'<h1>✓ Already Stage {user.current_stage}</h1><a href="/dashboard">Back</a>'

    target_balance = STAGE_TARGETS.get(stage, 0)
    if user.balance < target_balance:
        return f'<h1>❌ Need ${target_balance} to unlock Stage {stage}</h1><a href="/dashboard">Back</a>'

    req = StageRequest(user_id=user.id, stage_number=stage)
    db.session.add(req)
    db.session.commit()
    return f'<h1>✅ Request Sent!</h1><p>Admin will approve Stage {stage}</p><a href="/dashboard">Back</a>'

@app.route('/cart/add/<int:product_id>')
def add_to_cart(product_id):
    token = request.cookies.get('access_token')
    if not token: return redirect('/loginpage')
    try:
        decoded = decode_token(token)
        user = User.query.get(decoded['sub'])
    except: return redirect('/loginpage')

    user.balance += Decimal('0.40')
    db.session.commit()
    return redirect('/dashboard')

# === FIXED DASHBOARD WITH REFERRAL LINK ===
@app.route('/dashboard')
def dashboard():
    token = request.cookies.get('access_token')
    if not token: return '<h1>Please login first</h1><a href="/loginpage">Login</a>'
    try:
        decoded = decode_token(token)
        user = User.query.get(decoded['sub'])
    except: return '<h1>Invalid token</h1><a href="/loginpage">Login again</a>'

    products = Product.query.all()
    can_withdraw = user.balance >= 4.00 and user.streak_days >= 10
    today = datetime.utcnow().date()
    can_claim = not user.last_claim_date or user.last_claim_date.date()!= today

    steps_html = '<div style="display:flex;justify-content:space-between;align-items:center;margin:30px 0;padding:20px;background:rgba(255,255,255,0.04);border-radius:20px;border:1px solid rgba(168,85,247,0.3)">'
    for i in range(1,6):
        is_active = user.current_stage >= i
        bg = 'linear-gradient(135deg,#22c55e,#16a34a)' if is_active else 'rgba(255,255,255,0.08)'
        border = '#22c55e' if is_active else 'rgba(255,255,255,0.15)'
        color = '#22c55e' if is_active else '#666'
        can_unlock = user.current_stage+1==i and user.balance>=STAGE_TARGETS[i]
        btn = f'<a href="/request_stage/{i}" style="margin-top:8px;padding:6px 12px;background:#a855f7;color:white;border-radius:8px;text-decoration:none;font-size:11px">Unlock</a>' if can_unlock else ''
        steps_html += f'<div style="text-align:center;flex:1"><div style="width:50px;height:50px;margin:0 auto 8px;border-radius:50%;background:{bg};display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;border:3px solid {border}">{i}</div><div style="font-size:12px;font-weight:600;color:{color}">Stage {i}</div>{btn}</div>'
        if i<5:
            line_bg = 'linear-gradient(90deg,#22c55e,#a855f7)' if user.current_stage>i else 'rgba(255,255,255,0.08)'
            steps_html += f'<div style="height:3px;flex:1;background:{line_bg};margin:0 5px;border-radius:2px"></div>'
    steps_html += '</div>'

    claim_btn = '<a href="/claim" style="padding:14px 28px;background:linear-gradient(135deg,#22c55e,#16a34a);color:white;text-decoration:none;border-radius:12px;font-weight:600">🎁 Claim $0.40</a>' if can_claim else '<span style="color:#aaa">✓ Claimed today</span>'
    withdraw_btn = f'<a href="/settings" style="padding:14px 28px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;text-decoration:none;border-radius:12px;font-weight:600">💰 Request Withdrawal</a>' if can_withdraw else f'<span style="color:#ffaa00;font-size:16px">⏳ Need $4 + 10 days [{user.streak_days}/10]</span>'

    referral_box = f'''<div style="background:rgba(168,85,247,0.1);padding:15px;border-radius:15px;border:1px solid #a855f7;margin:20px 0">
        <p style="margin:0;color:#a855f7;font-size:12px">Your Referral Link:</p>
        <p style="margin:5px 0;word-break:break-all;font-size:14px">{request.url_root}signup?ref={user.referral_code}</p>
        <button onclick="navigator.clipboard.writeText('{request.url_root}signup?ref={user.referral_code}')" style="padding:8px 15px;background:#a855f7;color:white;border:none;border-radius:8px;font-size:12px;cursor:pointer">Copy Link</button>
    </div>'''

    products_html = "<h2 style='margin-top:40px;color:#a855f7;text-align:center'>🛍️ Products:</h2>"
    if not products:
        products_html += "<p style='text-align:center;color:#555;font-size:18px'>No products yet. Admin add some!</p>"
    else:
        for p in products:
            img_url = p.image_url.strip() if p.image_url else ""
            img_tag = f"<img src='{img_url}' style='width:100%;height:200px;object-fit:cover;border-radius:15px;margin-bottom:12px' onerror=\"this.src='https://via.placeholder.com/400x200/111/a855f7?text=No+Image'\">" if img_url else "<div style='width:100%;height:200px;background:linear-gradient(135deg,#111,#222);border-radius:15px;margin-bottom:12px;display:flex;align-items:center;justify-content:center;color:#555;font-size:18px'>📦 No Image</div>"
            products_html += f"<div style='border:1px solid rgba(168,85,247,0.2); padding:20px; margin:20px 0; background:rgba(255,255,255,0.03); border-radius:20px'>{img_tag}<h3 style='margin:0 0 10px 0;font-size:22px'>{p.name}</h3><p style='margin:0 0 15px 0; color:#aaa;font-size:17px'>${p.price} | Stock: {p.stock}</p><a href='/cart/add/{p.id}' style='display:inline-block;padding:12px 24px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;text-decoration:none;border-radius:12px;font-weight:600'>🛒 Add +$0.40</a></div>"

    admin_btns = ''
    if user.is_admin:
        admin_btns = '<p><a href="/admin/dashboard" style="padding:12px 20px;background:#ef4444;color:white;text-decoration:none;border-radius:10px;margin:5px;display:inline-block">👑 Admin Panel</a></p>'

    menu = f'''<div style="text-align:right;position:relative">
    <button onclick="document.getElementById('menu').style.display=document.getElementById('menu').style.display==='block'?'none':'block'" style="background:rgba(255,255,255,0.1);border:2px solid rgba(168,85,247,0.4);color:white;padding:12px 16px;border-radius:12px;cursor:pointer;font-size:20px">⋮</button>
    <div id="menu" style="display:none;position:absolute;right:0;top:55px;background:rgba(26,26,46,0.98);border:2px solid rgba(168,85,247,0.5);border-radius:15px;min-width:200px;z-index:999">
        <a href="/dashboard" style="display:block;padding:15px 20px;color:white;text-decoration:none;border-bottom:1px solid rgba(168,85,247,0.2)">🏠 Home</a>
        <a href="/settings" style="display:block;padding:15px 20px;color:white;text-decoration:none;border-bottom:1px solid rgba(168,85,247,0.2)">⚙️ Settings</a>
        <a href="/logout" style="display:block;padding:15px 20px;color:#ff6666;text-decoration:none">🚪 Logout</a>
    </div>
    </div>'''

    return f'''<style>body{{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins;margin:0;min-height:100vh}}</style>
    <div style="max-width:900px;margin:auto;padding:20px">
    {menu}
    {steps_html}
    <h1 style='text-align:center;margin-bottom:30px;font-size:42px'>🛒 Welcome {user.name}! Stage {user.current_stage}</h1>
    <div style="padding:25px;margin:20px 0;background:rgba(255,255,255,0.05);border-radius:20px;text-align:center">{claim_btn}</div>
    <div style="padding:25px;margin:20px 0;background:rgba(255,255,255,0.05);border-radius:20px">
        <h3 style="color:#a855f7">💰 Wallet</h3>
        <p>Balance: <b style="font-size:28px;color:#a855f7">${user.balance}</b></p>
        <p>Withdrawn: <b style="font-size:28px;color:#22c55e">${user.total_withdrawn}</b></p>
        {withdraw_btn}
        {referral_box}
        <div style="margin-top:20px">{admin_btns}</div>
    </div>
    <hr style="margin:40px 0;border:none;height:2px;background:linear-gradient(90deg,transparent,#a855f7,transparent)">
    {products_html}
    </div>'''

# === FIXED WITHDRAW - NO @jwt_required ===
@app.route('/withdraw', methods=['POST'])
def withdraw():
    token = request.cookies.get('access_token')
    if not token: return redirect('/loginpage')
    try:
        decoded = decode_token(token)
        user = User.query.get(decoded['sub'])
    except: return redirect('/loginpage')

    amount = Decimal(request.form.get('amount', '0'))
    phone = request.form.get('phone', '').strip()
    password = request.form.get('password', '')

    if not check_password_hash(user.password_hash, password):
        return '<h1>❌ Wrong password</h1><a href="/settings">Try again</a>'
    if phone!= user.phone:
        return '<h1>❌ Phone must match account</h1><a href="/settings">Try again</a>'
    if amount <= 0 or amount > user.balance or amount < 4:
        return '<h1>❌ Invalid amount Min $4</h1><a href="/settings">Back</a>'

    withdrawal = Withdrawal(user_id=user.id, amount=amount, phone=phone)
    db.session.add(withdrawal)
    user.balance -= amount
    db.session.commit()
    return f'<h1>✅ Request sent!</h1><p>Admin will review ${amount}</p><a href="/settings">Back</a>'

# === ADMIN DASHBOARD COMBINED ===
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    pending_withdrawals = Withdrawal.query.filter_by(status='pending').order_by(Withdrawal.id.desc()).all()
    pending_stages = StageRequest.query.filter_by(status='pending').order_by(StageRequest.id.desc()).all()

    html = '''<style>body{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins;padding:20px}
   .container{max-width:1000px;margin:auto}.box{background:rgba(255,255,255,0.05);padding:25px;border-radius:20px;border:1px solid rgba(168,85,247,0.3);margin-bottom:20px}
    table{width:100%;border-collapse:collapse;margin-top:15px}th,td{padding:12px;border-bottom:1px solid #333;text-align:left}
    th{background:rgba(168,85,247,0.2)}.btn{padding:8px 15px;border:none;border-radius:8px;cursor:pointer;font-weight:bold;margin:2px;text-decoration:none;display:inline-block}
   .approve{background:#22c55e;color:white}.reject{background:#ef4444;color:white}.btn-link{padding:12px 20px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;text-decoration:none;border-radius:10px;margin:5px;display:inline-block}</style>
    
    <div class="container">
    <h1>👑 Admin Panel</h1>
    <div style="margin:20px 0">
        <a href="/admin/add-product" class="btn-link">➕ Add Product</a>
        <a href="/dashboard" class="btn-link">🏠 User View</a>
    </div>
    
    <div class="box">
    <h3>💰 Pending Withdrawals</h3>
    <table>
    <tr><th>ID</th><th>User</th><th>Amount</th><th>Phone</th><th>Date</th><th>Action</th></tr>'''
    
    for w in pending_withdrawals:
        u = User.query.get(w.user_id)
        html += f'''<tr>
            <td>{w.id}</td>
            <td>{u.name} - {u.email}</td>
            <td>${w.amount}</td>
            <td>{w.phone}</td>
            <td>{w.requested_at.strftime('%Y-%m-%d
