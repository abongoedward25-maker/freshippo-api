from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os, random, string

app = Flask(__name__)

# FIX 1: Crash-proof DATABASE_URL. Render uses postgres:// but SQLAlchemy needs postgresql://
db_url = os.getenv('DATABASE_URL', '')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

if not db_url:
    raise ValueError("DATABASE_URL environment variable is not set")

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'freshippo_secret_2026')

db = SQLAlchemy(app)
jwt = JWTManager(app)

MANAGER = {'phone': '+254767005095', 'password_hash': generate_password_hash('Freshippo')}
STAGES = {
    1: {'name': 'Stage 1', 'duration_days': 365, 'type': 'Ordinary employee'},
    2: {'name': 'Stage 2', 'duration_days': 730, 'type': 'Senior employee'},
    3: {'name': 'Stage 3', 'duration_days': 730, 'type': 'Hiring employee'}
}

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(15), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    referral_code = db.Column(db.String(10), unique=True)
    balance = db.Column(db.Float, default=0.0)
    days_completed = db.Column(db.Integer, default=0)
    last_task_date = db.Column(db.Date)
    tasks_today = db.Column(db.Integer, default=0)

class StageRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    stage = db.Column(db.Integer)
    status = db.Column(db.String(20), default='pending')
    joined_at = db.Column(db.DateTime)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)

# FIX 2: Root route so Render health check passes
@app.route('/')
def health():
    return jsonify({"status": "Freshippo API running", "endpoints": ["/signup", "/login", "/join_stage", "/my_stages"]})

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    if not data or not data.get('phone') or not data.get('password') or not data.get('name'):
        return jsonify({'message': 'Missing fields'}), 400
    if User.query.filter_by(phone=data['phone']).first():
        return jsonify({'message': 'Account already exists'}), 400
    code = ''.join(random.choices(string.digits, k=6))
    user = User(name=data['name'], phone=data['phone'], password_hash=generate_password_hash(data['password']), referral_code=code)
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'Registration successful'})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    if not data or not data.get('phone') or not data.get('password'):
        return jsonify({'message': 'Missing credentials'}), 400
    user = User.query.filter_by(phone=data['phone']).first()
    if not user or not check_password_hash(user.password_hash, data['password']):
        return jsonify({'message': 'Invalid credentials'}), 401
    token = create_access_token(identity=user.id)
    return jsonify({'message': 'Successfully login', 'token': token})

@app.route('/join_stage', methods=['POST'])
@jwt_required()
def join_stage():
    user_id = get_jwt_identity()
    stage = request.json.get('stage')
    if stage not in [1,2,3]:
        return jsonify({'message': 'Invalid stage'}), 400
    if StageRequest.query.filter_by(user_id=user_id, stage=stage).first():
        return jsonify({'message': 'Already requested this stage'}), 400
    req = StageRequest(user_id=user_id, stage=stage)
    db.session.add(req)
    db.session.commit()
    return jsonify({'message': 'Wait for manager approval'})

@app.route('/my_stages', methods=['GET'])
@jwt_required()
def my_stages():
    user_id = get_jwt_identity()
    requests = StageRequest.query.filter_by(user_id=user_id).all()
    result = {}
    for s in [1,2,3]:
        req = next((r for r in requests if r.stage==s), None)
        result[f'stage_{s}'] = {'status': req.status if req else 'not_joined', 'details': STAGES[s]}
    return jsonify(result)

@app.route('/admin/approve', methods=['POST'])
def admin_approve():
    data = request.json
    if not data or data.get('manager_phone')!= MANAGER['phone'] or not check_password_hash(MANAGER['password_hash'], data.get('manager_password','')):
        return jsonify({'message': 'Unauthorized'}), 401
    req = StageRequest.query.get(data.get('request_id'))
    if not req:
        return jsonify({'message': 'Request not found'}), 404
    req.status = 'approved'
    req.joined_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'message': 'Joined successfully'})

@app.route('/admin/update_manager', methods=['POST'])
def update_manager():
    data = request.json
    if not check_password_hash(MANAGER['password_hash'], data.get('old_password','')):
        return jsonify({'message': 'Wrong old password'}), 401
    MANAGER['password_hash'] = generate_password_hash(data.get('new_password',''))
    MANAGER['phone'] = data.get('new_phone', MANAGER['phone'])
