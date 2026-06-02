from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os, random, string

app = Flask(__name__)

# FIX 1: psycopg3 URL format + crash-proof DATABASE_URL
db_url = os.getenv('DATABASE_URL', '')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url.startswith("postgresql://") and "+psycopg" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'freshippo_secret_2026')

db = SQLAlchemy(app)
jwt = JWTManager(app)

STAGES = {
    1: {'name': 'Stage 1', 'days': 365, 'price': 99},
    2: {'name': 'Stage 2', 'days': 730, 'price': 199},
    3: {'name': 'Stage 3', 'days': 1095, 'price': 299}
}

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(15), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    referral_code = db.Column(db.String(10), unique=True)
    referred_by = db.Column(db.String(10))
    balance = db.Column(db.Float, default=0.0)
    current_stage = db.Column(db.Integer, default=1)
    stage_start_date = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    date = db.Column(db.Date, default=datetime.utcnow().date)
    completed = db.Column(db.Boolean, default=False)

class Withdrawal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Float)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def generate_ref_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

@app.route('/')
def health():
    return jsonify({"status": "Freshippo API running", "version": "2.0"})

@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    if not data or not data.get('phone') or not data.get('password') or not data.get('name'):
        return jsonify({'message': 'Missing fields'}), 400

    if User.query.filter_by(phone=data['phone']).first():
        return jsonify({'message': 'Phone already exists'}), 400

    ref_code = generate_ref_code()
    user = User(
        name=data['name'],
        phone=data['phone'],
        password_hash=generate_password_hash(data['password']),
        referral_code=ref_code,
        referred_by=data.get('referral_code')
    )
    db.session.add(user)
    db.session.commit()

    # Referral bonus
    if data.get('referral_code'):
        ref_user = User.query.filter_by(referral_code=data['referral_code']).first()
        if ref_user:
            ref_user.balance += 10

    token = create_access_token(identity=user.id)
    return jsonify({'message': 'User created', 'token': token, 'referral_code': ref_code})

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(phone=data.get('phone')).first()
    if user and check_password_hash(user.password_hash, data.get('password')):
        token = create_access_token(identity=user.id)
        return jsonify({'token': token})
    return jsonify({'message': 'Invalid credentials'}), 401

@app.route('/dashboard', methods=['GET'])
@jwt_required()
def dashboard():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    stage_info = STAGES[user.current_stage]
    days_left = (user.stage_start_date + timedelta(days=stage_info['days']) - datetime.utcnow()).days
    tasks_today = Task.query.filter_by(user_id=user_id, date=datetime.utcnow().date()).count()

    return jsonify({
        'name': user.name,
        'phone': user.phone,
        'balance': user.balance,
        'stage': stage_info['name'],
        'days_left': max(0, days_left),
        'tasks_completed_today': tasks_today,
        'referral_code': user.referral_code
    })

@app.route('/complete_task', methods=['POST'])
@jwt_required()
def complete_task():
    user_id = get_jwt_identity()
    today = datetime.utcnow().date()
    if Task.query.filter_by(user_id=user_id, date=today).first():
        return jsonify({'message': 'Task already completed today'}), 400

    task = Task(user_id=user_id)
    user = User.query.get(user_id)
    user.balance += 5
    db.session.add(task)
    db.session.commit()
    return jsonify({'message': 'Task completed', 'earned': 5, 'new_balance': user.balance})

@app.route('/upgrade_stage', methods=['POST'])
@jwt_required()
def upgrade_stage():
    user_id = get_jwt_identity()
    data = request.get_json()
    new_stage = data.get('stage')

    if new_stage not in [2, 3]:
        return jsonify({'message': 'Invalid stage'}), 400

    user = User.query.get(user_id)
    if user.current_stage >= new_stage:
        return jsonify({'message': 'Already at this stage or higher'}), 400

    price = STAGES[new_stage]['price']
    if user.balance < price:
        return jsonify({'message': 'Insufficient balance'}), 400

    user.balance -= price
    user.current_stage = new_stage
    user.stage_start_date = datetime.utcnow()
    db.session.commit()
    return jsonify({'message': f'Upgraded to Stage {new_stage}', 'new_balance': user.balance})

@app.route('/withdraw', methods=['POST'])
@jwt_required()
def withdraw():
    user_id = get_jwt_identity()
    data = request.get_json()
    amount = float(data.get('amount', 0))

    user = User.query.get(user_id)
    if amount < 50:
        return jsonify({'message': 'Minimum withdrawal is $50'}), 400
    if user.balance < amount:
        return jsonify({'message': 'Insufficient balance'}), 400

    user.balance -= amount
    withdrawal = Withdrawal(user_id=user_id, amount=amount)
    db.session.add(withdrawal)
    db.session.commit()
    return jsonify({'message': 'Withdrawal request submitted', 'amount': amount})

# FIX 2: Don't run db.create_all() on import - Render will timeout
# Run it once manually via Render Shell instead

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
