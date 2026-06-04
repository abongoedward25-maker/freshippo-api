from flask import Flask, request, jsonify, make_response
import os
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, decode_token
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import timedelta
from decimal import Decimal
from functools import wraps

load_dotenv()

app = Flask(__name__)
CORS(app)
@app.route('/')
def homepage():  # changed from home to homepage
    html = """
    <html>
        <head><title>Freshippo API</title></head>
        <body style="font-family:Arial; text-align:center; padding:50px">
            <h1>🛒 Freshippo API</h1>
            <p>Status: <b style="color:green">LIVE</b></p>
            <h3>Available Endpoints:</h3>
            <p>GET /health</p>
            <p>POST /register</p>
            <p>POST /login</p>
            <p>GET /products</p>
        </body>
    </html>
    """
    return html 
    
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

# === MODELS ===
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), default='')
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self):
        return {"id": self.id, "email": self.email, "name": self.name, "phone": self.phone, "is_admin": self.is_admin}

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    price = db.Column(db.Numeric(10, 2), nullable=False)
    stock = db.Column(db.Integer, default=0)
    category = db.Column(db.String(100), default='General')
    image_url = db.Column(db.String(500), default='')

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "price": float(self.price), "stock": self.stock,
            "category": self.category, "image_url": self.image_url
        }

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

# Admin check
def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user = User.query.get(get_jwt_identity())
        if not user or not user.is_admin:
            return jsonify({"msg": "Admin required"}), 403
        return fn(*args, **kwargs)
    return wrapper

# Create tables only, no seed data
with app.app_context():
    db.create_all()

# === ROUTES ===
@app.route('/')
def home():
    return jsonify({"status": "Freshippo API LIVE ✅", "products": "add via POST /products"})

@app.route('/health')
def health():
    try:
        db.session.execute(db.text('SELECT 1'))
        return jsonify({"status": "healthy"}), 200
    except Exception as e:
        return jsonify({"status": "error", "db": str(e)}), 500

# AUTH
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

@app.route('/loginpage', methods=['GET', 'POST'])
def login_page():  # <-- 0 spaces
    if request.method == 'POST':  # <-- 4 spaces
        email = request.form.get('email')  # <-- 8 spaces
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            token = create_access_token(identity=str(user.id))
            resp = make_response(f'<h1>Welcome Back!</h1><p><a href="/dashboard">Go to Dashboard</a></p>')  # <-- 12 spaces
            resp.set_cookie('access_token', token, httponly=True)  # <-- 12 spaces
            return resp  # <-- 12 spaces - THIS MUST BE INSIDE the if block
        return "Error: Wrong credentials <br><a href='/loginpage'>Try again</a>"  # <-- 8 spaces
    return "<h2>Login</h2>...form..."  # <-- 4 spaces

# PRODUCTS - YOU ADD THESE
@app.route('/products', methods=['POST'])
@admin_required
def add_product():
    data = request.get_json()
    try:
        product = Product(
            name=data['name'],
            description=data.get('description', ''),
            price=Decimal(str(data['price'])),
            stock=data.get('stock', 0),
            category=data.get('category', 'General'),
            image_url=data.get('image_url', '')
        )
        db.session.add(product)
        db.session.commit()
        return jsonify({"msg": "Product added", "product": product.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/signup', methods=['GET', 'POST'])
def signup_page():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        
        if User.query.filter_by(email=email).first():
            return f"Error: Email exists <br><a href='/signup'>Try again</a>"
        
        try:
            user = User(email=email, name=name, phone='')
            user.password_hash = generate_password_hash(password)
            db.session.add(user)
            db.session.commit()
            token = create_access_token(identity=str(user.id))
            return f"<h1>Account Created</h1><p>Welcome {name}</p><a href='/loginpage'>Sign In</a>"
        except Exception as e:
            db.session.rollback()
            return f"Error: {str(e)} <br><a href='/signup'>Try again</a>"
    
    return "<h2>Sign Up</h2><form method='POST'><input name='name' placeholder='Name' required><br><input name='email' type='email' required><br><input name='password' type='password' required><br><button>Sign Up</button></form>"

if user and check_password_hash(user.password_hash, password):
    token = create_access_token(identity=str(user.id))
    resp = make_response(f'<h1>Welcome Back!</h1><p><a href="/dashboard">Go to Dashboard</a></p>')
    resp.set_cookie('access_token', token, httponly=True)
    return resp

@app.route('/dashboard')
def dashboard():
    token = request.cookies.get('access_token')
    if not token:
        return '<h1>Please login first</h1><a href="/loginpage">Login</a>'
    
    try:
        from flask_jwt_extended import decode_token
        decoded = decode_token(token)
        user_id = decoded['sub']
        user = User.query.get(user_id)
    except:
        return '<h1>Invalid token</h1><a href="/loginpage">Login again</a>'
    
    products = Product.query.all()
    
    html = f"""
    <html><body style="font-family:Arial; padding:20px; max-width:600px; margin:auto">
    <h1>🛒 Welcome {user.name}!</h1>
    <p>Email: {user.email} | Admin: {user.is_admin}</p>
    <hr>
    <h2>Products in Store:</h2>
    """
    
    if not products:
        html += "<p>No products yet. Add some!</p>"
    else:
        for p in products:
            html += f"<div style='border:1px solid #ddd; padding:10px; margin:10px 0'><h3>{p.name}</h3><p>${p.price} | Stock: {p.stock}</p></div>"
    
    if user.is_admin:
        html += '<p><a href="/add-product">+ Add New Product</a></p>'
    
    html += '<p><a href="/loginpage">Logout</a></p></body></html>'
    return html
