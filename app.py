# ============================================
# FRESHIPPO PREMIUM v4.0 - FULL COMPLETE CODE
# Xender UI + All Features + Admin Panel
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
        'language VARCHAR(10) DEFAULT \'en\''
    ]
    for col in cols:
        try:
            db.session.execute(text(f'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS {col}'))
            db.session.commit()
            print(f"Added column: {col.split()[0]}")
        except Exception as e:
            db.session.rollback()

# === MODELS ===
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

    def to_dict(self):
        return {"id": self.id, "email": self.email, "name": self.name, "phone": self.phone,
                "language": self.language, "is_admin": self.is_admin, "balance": float(self.balance),
                "current_stage": self.current_stage, "stage_status": self.stage_status}

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
    user = User(email=data['email'], name=data['name'], phone=data.get('phone', ''))
    user.password_hash = generate_password_hash(data['password'])
    db.session.add(user)
    db.session.commit()
    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user.to_dict()}), 201

@app.route('/signup', methods=['GET', 'POST'])
def signup_page():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        if User.query.filter_by(email=email).first():
            return f"Error: Email exists <br><a href='/signup'>Try again</a>"
        user = User(email=email, name=name, phone='')
        user.password_hash = generate_password_hash(password)
        db.session.add(user)
        db.session.commit()
        return f"<h1>Account Created</h1><p>Welcome {name}</p><a href='/loginpage'>Sign In</a>"
    return "<style>body{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins}</style><h2>Sign Up</h2><form method='POST' style='max-width:300px;margin:auto;padding:30px;background:rgba(255,255,255,0.05);border-radius:20px'><input name='name' placeholder='Name' required style='width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white'><br><input name='email' type='email' required placeholder='Email' style='width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white'><br><input name='password' type='password' required placeholder='Password' style='width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white'><br><button style='width:100%;padding:14px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;border:none;border-radius:10px;font-weight:bold'>Sign Up</button></form>"

@app.route('/loginpage', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            token = create_access_token(identity=str(user.id))
            resp = make_response(f'<style>body{{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins;text-align:center;padding:50px}}</style><h1>Welcome Back!</h1><p><a href="/dashboard" style="color:#a855f7;font-size:18px">Go to Dashboard</a></p>')
            resp.set_cookie('access_token', token, httponly=True)
            return resp
        return "Error: Wrong credentials <br><a href='/loginpage'>Try again</a>"
    return "<style>body{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:Poppins}</style><h2>Login</h2><form method='POST' style='max-width:300px;margin:auto;padding:30px;background:rgba(255,255,255,0.05);border-radius:20px'><input name='email' type='email' required placeholder='Email' style='width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white'><br><input name='password' type='password' required placeholder='Password' style='width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #333;background:#0a0a0a;color:white'><br><button style='width:100%;padding:14px;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;border:none;border-radius:10px;font-weight:bold'>Sign In</button></form>"

@app.route('/logout')
def logout():
    resp = make_response(redirect('/loginpage'))
    resp.set_cookie('access_token', '', expires=0)
    return resp

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
    can_withdraw = True
    days_left = 0
    if last_withdrawal:
        days_passed = (datetime.utcnow() - last_withdrawal.approved_at).days
        if days_passed < 10:
            can_withdraw = False
            days_left = 10 - days_passed

    # XENDER-STYLE STEPS BAR
    steps_html = f'''
    <div style="display:flex;justify-content:space-between;align-items:center;margin:30px 0;padding:20px;background:rgba(255,255,255,0.04);backdrop-filter:blur(20px);border-radius:20px;border:1px solid rgba(168,85,247,0.3)">
        {''.join([f'''
        <div style="text-align:center;flex:1">
            <div style="width:50px;height:50px;margin:0 auto 8px;border-radius:50%;background:{'linear-gradient(135deg,#22c55e,#16a34a)' if user.current_stage>=i else 'rgba(255,255,255,0.08)'};display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;border:3px solid {'#22c55e' if user.current_stage>=i else 'rgba(255,255,255,0.15)'}">{i}</div>
            <div style="font-size:12px;font-weight:600;color:{'#22c55e' if user.current_stage>=i else '#666'}">Stage {i}</div>
        </div>
        {'<div style="height:3px;flex:1;background:' + ('linear-gradient(90deg,#22c55e,#a855f7)' if user.current_stage>i else 'rgba(255,255,255,0.08)') + ';margin:0 5px;border-radius:2px"></div>' if i<5 else ''}
        ''' for i in range(1,6)])}
    </div>
    '''

    # Products with images
    html = steps_html + f"<h1 style='text-align:center;margin-bottom:30px;font-size:42px'>🛒 Welcome {user.name}!</h1>"
    html += f"<p style='text-align:center;color:#aaa;font-size:17px'>Email: {user.email}</p><hr>"
    html += "<h2 style='margin-top:30px'>Products in Store:</h2>"
    if not products:
        html += "<p style='text-align:center;color:#555'>No products yet. Add some!</p>"
    else:
        for p in products:
            img_url = p.image_url.strip() if p.image_url else ""
            if img_url:
                img_tag = f"<img src='{img_url}' style='width:100%;height:200px;object-fit:cover;border-radius:15px;margin-bottom:12px' onerror=\"this.src='https://via.placeholder.com/400x200/111/a855f7?text=No+Image'\">"
            else:
                img_tag = "<div style='width:100%;height:200px;background:linear-gradient(135deg,#111,#222);border-radius:15px;margin-bottom:12px;display:flex;align-items:center;justify-content:center;color:#555;font-size:18px'>📦 No Image</div>"

            html += f"<div style='border:1px solid rgba(168,85,247,0.2); padding:20px; margin:20px 0; background:rgba(255,255,255,0.03); backdrop-filter:blur(15px); border-radius:20px'>{img_tag}<h3 style='margin:0 0 10px 0;font-size:22px'>{p.name}</h3
