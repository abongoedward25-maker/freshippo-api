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

# === STAGE CONFIG ===
STAGE_TARGETS = {1: 0, 2: 50, 3: 200, 4: 500, 5: 1000} # Min balance to unlock each stage
DAILY_CREDIT = Decimal('1.00') # $1 per day

# === AUTO MIGRATE MISSING COLUMNS ===
from sqlalchemy import text
with app.app_context():
    db.create_all()
    cols = [
        'balance NUMERIC(10,2) DEFAULT 0.00',
        'total_withdrawn NUMERIC(10,2) DEFAULT 0.00',
        'current_stage INTEGER DEFAULT 1',
        'stage_status VARCHAR(20) DEFAULT \'approved\'',
        'stage_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
        'last_credit_date DATE DEFAULT CURRENT_DATE'
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
    is_admin = db.Column(db.Boolean, default=False)
    balance = db.Column(db.Numeric(10, 2), default=0.00)
    total_withdrawn = db.Column(db.Numeric(10, 2), default=0.00)
    current_stage = db.Column(db.Integer, default=1)
    stage_status = db.Column(db.String(20), default='approved') # approved, pending
    stage_updated_at = db.Column(db.DateTime, server_default=db.func.now())
    last_credit_date = db.Column(db.Date, server_default=db.func.current_date())
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self):
        return {"id": self.id, "email": self.email, "name": self.name, "phone": self.phone,
                "is_admin": self.is_admin, "balance": float(self.balance),
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

# === DAILY CREDIT FUNCTION ===
def credit_daily_balance(user):
    today = datetime.utcnow().date()
    if user.last_credit_date < today:
        target = Decimal(STAGE_TARGETS.get(user.current_stage, 1000))
        if user.balance < target:
            user.balance += DAILY_CREDIT
            if user.balance > target:
                user.balance = target
        user.last_credit_date = today
        db.session.commit()

with app.app_context():
    db.create_all()

# === ROUTES ===
@app.route('/')
def homepage():
    return '''<html><head><title>Freshippo API</title></head><body style="font-family:Arial; text-align:center; padding:50px">
    <h1>🛒 Freshippo API</h1><p>Status: <b style="color:green">LIVE</b></p>
    <p><a href="/signup">Sign Up</a> | <a href="/loginpage">Login</a> | <a href="/dashboard">Dashboard</a></p>
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
    return "<h2>Sign Up</h2><form method='POST'><input name='name' placeholder='Name' required><br><input name='email' type='email' required><br><input name='password' type='password' required><br><button>Sign Up</button></form>"

@app.route('/loginpage', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            token = create_access_token(identity=str(user.id))
            resp = make_response(f'<h1>Welcome Back!</h1><p><a href="/dashboard">Go to Dashboard</a></p>')
            resp.set_cookie('access_token', token, httponly=True)
            return resp
        return "Error: Wrong credentials <br><a href='/loginpage'>Try again</a>"
    return "<h2>Login</h2><form method='POST'><input name='email' type='email' required placeholder='Email'><br><input name='password' type='password' required placeholder='Password'><br><button>Sign In</button></form>"

@app.route('/dashboard')
def dashboard():
    token = request.cookies.get('access_token')
    if not token:
        return '<h1>Please login first</h1><a href="/loginpage">Login</a>'
    try:
        decoded = decode_token(token)
        user = User.query.get(decoded['sub'])
        credit_daily_balance(user) # Auto credit daily
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

    # Stage logic
    next_stage = user.current_stage + 1
    stage_target = STAGE_TARGETS.get(next_stage, 0)
    can_claim_stage = user.balance >= stage_target and user.stage_status == 'approved' and next_stage in STAGE_TARGETS

    html = f"<h1>🛒 Welcome {user.name}!</h1>"
    html += f"<p>Email: {user.email} | Admin: {user.is_admin}</p><hr>"
    html += "<h2>Products in Store:</h2>"
    if not products:
        html += "<p>No products yet. Add some!</p>"
    else:
        for p in products:
            img = f"<img src='{p.image_url}' style='width:100%;max-height:150px;object-fit:cover;border-radius:6px;margin-bottom:8px'>" if p.image_url else ""
            html += f"<div style='border:1px solid #333; padding:12px; margin:10px 0; background:#0a0a0a; border-radius:8px'>{img}<h3 style='margin:0 0 5px 0'>{p.name}</h3><p style='margin:0 0 10px 0; color:#aaa'>${p.price} | Stock: {p.stock}</p><a href='/cart/add/{p.id}' class='btn'>🛒 Add to Cart</a></div>"

    if user.is_admin:
        html += '<p style="margin-top:20px"><a href="/admin/add-product" class="btn">+ Add New Product</a></p>'
        html += '<p><a href="/admin/stages" class="btn">👑 Approve Stages</a></p>'
        html += '<p><a href="/admin/withdrawals" class="btn">💰 Approve Withdrawals</a></p>'

    withdraw_btn = f'<a href="/withdraw" class="btn">💰 Request Withdrawal</a>' if can_withdraw else f'<span style="color:#ffaa00">⏳ Withdrawal available in {days_left} days</span>'
    stage_btn = f'<a href="/stage/claim" class="btn" style="background:#22c55e">🚀 Claim Stage {next_stage}</a>' if can_claim_stage else f'<span style="color:#aaa">Need ${stage_target} to unlock Stage {next_stage}</span>'
    if user.stage_status == 'pending':
        stage_btn = '<span style="color:#ffaa00">⏳ Stage upgrade pending admin approval</span>'

    wrapper = f"""<style>body{{background:#0a0a0a;color:white;font-family:Arial;margin:0}}.watermark{{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%) rotate(-15deg);font-size:15vw;color:rgba(168,85,247,0.08);z-index:0;pointer-events:none;white-space:nowrap}}.content{{position:relative;z-index:1;padding:20px;max-width:800px;margin:auto}}.box{{padding:18px;margin:12px 0;background:#111;border-left:3px solid #a855f7;border-radius:10px}}.btn{{display:inline-block;padding:10px 20px;margin:8px 5px;background:#a855f7;color:white;text-decoration:none;border-radius:8px;font-weight:600}}.btn.red{{background:#ff4444}}.stats{{display:flex;gap:15px;margin-top:10px}}.stat{{flex:1;background:#0a0a0a;padding:12px;border-radius:6px;text-align:center}}</style><div class="watermark">Freshippo</div><div class="content"><div class="box">1️⃣ Admin Panel | Status: {'✅ Active' if user.is_admin else '❌ No Access'}</div><div class="box">2️⃣ Products: {len(products)} items in store</div><div class="box">4️⃣ Withdrawal<div class="stats"><div class="stat"><b>${user.balance}</b><br>Balance</div><div class="stat"><b>${user.total_withdrawn}</b><br>Total Withdrawn</div></div>{withdraw_btn}<p style="font-size:12px;color:#aaa;margin-top:8px">10-day cooldown | +$1 daily</p></div><div class="box">5️⃣ Stages<div class="stats"><div class="stat"><b>Stage {user.current_stage}</b><br>Current</div><div class="stat"><b>{user.stage_status.upper()}</b><br>Status</div></div>{stage_btn}</div><hr style="margin:30px 0">{html}</div>"""
    return wrapper

@app.route('/admin/add-product', methods=['GET', 'POST'])
def add_product():
    token = request.cookies.get('access_token')
    if not token:
        return redirect('/loginpage')
    try:
        decoded = decode_token(token)
        user = User.query.get(decoded['sub'])
        if not user or not user.is_admin:
            return redirect('/loginpage')
    except:
        return redirect('/loginpage')

    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        image_url = request.form['image_url']
        desc = request.form['desc']
        new_product = Product(name=name, price=price, stock=stock, description=desc, image_url=image_url)
        db.session.add(new_product)
        db.session.commit()
        return redirect('/dashboard')

    return '''<!doctype html><html><head><title>Add Product</title></head><body style="background:#0f0f23;color:white;font-family:sans-serif"><form method="post" style="max-width:400px;margin:50px auto;padding:20px;background:#1a1a2e;border-radius:10px"><h2>Add New Product</h2><input name="name" placeholder="Product Name" required style="width:100%;padding:10px;margin:8px 0;border-radius:5px;border:none"><input name="price" type="number" step="0.01" placeholder="Price $" required style="width:100%;padding:10px;margin:8px 0;border-radius:5px;border:none"><input name="stock" type="number" placeholder="Stock Quantity" required style="width:100%;padding:10px;margin:8px 0;border-radius:5px;border:none"><input name="image_url" placeholder="Image URL" style="width:100%;padding:10px;margin:8px 0;border-radius:5px;border:none"><textarea name="desc" placeholder="Description" rows="3" style="width:100%;padding:10px;margin:8px 0;border-radius:5px;border:none"></textarea><button type="submit" style="width:100%;padding:12px;background:#8b5cf6;color:white;border:none;border-radius:5px;font-weight:bold">Add Product</button><br><br><a href="/dashboard" style="color:#8b5cf6">← Back to Dashboard</a></form></body></html>'''

@app.route('/cart/add/<int:product_id>')
@jwt_required()
def add_to_cart(product_id):
    user_id = get_jwt_identity()
    product = Product.query.get(product_id)
    if not product:
        return 'Product not found <a href="/dashboard">Back</a>'
    if product.stock <= 0:
        return '❌ Out of stock <a href="/dashboard">Back</a>'
    item = CartItem.query.filter_by(user_id=user_id, product_id=product_id).first()
    if item:
        item.quantity += 1
    else:
        item = CartItem(user_id=user_id, product_id=product_id, quantity=1)
        db.session.add(item)
    db.session.commit()
    return f'<h1>✅ Added {product.name} to cart!</h1><p>Quantity: {item.quantity if item else 1}</p><a href="/dashboard">Continue Shopping</a>'

@app.route('/withdraw', methods=['GET', 'POST'])
@jwt_required()
def withdraw():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    last_withdrawal = Withdrawal.query.filter_by(user_id=user.id, status='approved').order_by(Withdrawal.approved_at.desc()).first()
    if last_withdrawal:
        days_passed = (datetime.utcnow() - last_withdrawal.approved_at).days
        if days_passed < 10:
            return f'<h1>⏳ Cooldown active</h1><p>Next withdrawal in {10 - days_passed} days</p><a href="/dashboard">Back</a>'
    if request.method == 'POST':
        amount = Decimal(request.form.get('amount', '0'))
        if amount <= 0 or amount > user.balance:
            return 'Invalid amount <br><a href="/dashboard">Back</a>'
        withdrawal = Withdrawal(user_id=user.id, amount=amount)
        db.session.add(withdrawal)
        user.balance -= amount
        db.session.commit()
        return f'<h1>✅ Request sent!</h1><p>Admin will review ${amount}</p><a href="/dashboard">Back</a>'
    return f'<h2>Request Withdrawal</h2><p>Balance: ${user.balance}</p><form method="POST"><input name="amount" type="number" step="0.01" placeholder="Amount" required><br><button>Request</button></form>'

@app.route('/admin/withdrawals')
@admin_required
def admin_withdrawals():
    withdrawals = Withdrawal.query.filter_by(status='pending').all()
    html = '<h1>💰 Pending Withdrawals</h1>'
    for w in withdrawals:
        user = User.query.get(w.user_id)
        html += f'<div style="border:1px solid #444; padding:15px; margin:10px 0; background:#111"><p><b>{user.name}</b> - ${w.amount}</p><a href="/admin/withdraw/approve/{w.id}" class="btn">Approve</a> <a href="/admin/withdraw/reject/{w.id}" class="btn red">Reject</a></div>'
    return html + '<p><a href="/dashboard">Back</a></p>'

@app.route('/admin/withdraw/approve/<int:w_id>')
@admin_required
def approve_withdraw(w_id):
    w = Withdrawal.query.get(w_id)
    user = User.query.get(w.user_id)
    w.status = 'approved'
    w.approved_at = datetime.utcnow()
    user.total_withdrawn += w.amount
    db.session.commit()
    return 'Approved! <a href="/admin/withdrawals">Back</a>'

@app.route('/admin/withdraw/reject/<int:w_id>')
@admin_required
def reject_withdraw(w_id):
    w = Withdrawal.query.get(w_id)
    user = User.query.get(w.user_id)
    w.status = 'rejected'
    user.balance += w.amount
    db.session.commit()
    return 'Rejected & refunded! <a href="/admin/withdrawals">Back</a>'

@app.route('/stage/claim')
@jwt_required()
def claim_stage():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    next_stage = user.current_stage + 1
    target = STAGE_TARGETS.get(next_stage, 0)
    if user.balance >= target and user.stage_status == 'approved' and next_stage in STAGE_TARGETS:
        user.current_stage = next_stage
        user.stage_status = 'pending'
        user.stage_updated_at = datetime.utcnow()
        db.session.commit()
        return f'<h1>🚀 Stage {next_stage} Requested!</h1><p>Admin will review your upgrade</p><a href="/dashboard">Back</a>'
    return 'Cannot claim stage yet <a href="/dashboard">Back</a>'

@app.route('/admin/stages')
@admin_required
def admin_stages():
    users = User.query.filter(User.stage_status=='pending', User.current_stage>1).all()
    html = '<h1>👑 Pending Stage Approvals</h1>'
    for u in users:
        html += f'<div style="border:1px solid #444; padding:15px; margin:10px 0; background:#111"><p><b>{u.name}</b> - Stage {u.current_stage} | Balance: ${u.balance}</p><a href="/admin/stage/approve/{u.id}" class="btn">Approve</a> <a href="/admin/stage/reject/{u.id}" class="btn red">Reject</a></div>'
    return html + '<p><a href="/dashboard">Back</a></p>'

@app.route('/admin/stage/approve/<int:user_id>')
@admin_required
def approve_stage(user_id):
    user = User.query.get(user_id)
    user.stage_status = 'approved'
    user.stage_updated_at = datetime.utcnow()
    db.session.commit()
    return 'Stage approved! <a href="/admin/stages">Back</a>'

@app.route('/admin/stage/reject/<int:user_id>')
@admin_required
def reject_stage(user_id):
    user = User.query.get(user_id)
    user.current_stage = max(1, user.current_stage - 1)
    user.stage_status = 'approved'
    db.session.commit()
    return 'Stage rejected! <a href="/admin/stages">Back</a>'

if __name__ == '__main__':
    app.run(debug=True)
