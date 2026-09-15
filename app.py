from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
import anthropic
import os
import random
import bcrypt
from datetime import date, datetime

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'pitchiq-secret-2026')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pitchiq.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login_page'

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# ── DATABASE MODELS ──
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    daily_count = db.Column(db.Integer, default=0)
    last_question_date = db.Column(db.String(20), default="")

    def get_daily_limit(self):
        return 20  # logged in users get 20

    def check_and_reset_daily(self):
        today = str(date.today())
        if self.last_question_date != today:
            self.daily_count = 0
            self.last_question_date = today
            db.session.commit()

    def questions_remaining(self):
        self.check_and_reset_daily()
        return max(0, self.get_daily_limit() - self.daily_count)

    def can_ask(self):
        self.check_and_reset_daily()
        return self.daily_count < self.get_daily_limit()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ── GUEST USAGE TRACKING ──
guest_usage = {}
GUEST_LIMIT = 10

def get_guest_key():
    return request.remote_addr

def check_guest_limit():
    key = get_guest_key()
    today = str(date.today())
    if key not in guest_usage:
        guest_usage[key] = {"date": today, "count": 0}
    if guest_usage[key]["date"] != today:
        guest_usage[key] = {"date": today, "count": 0}
    return guest_usage[key]["count"] < GUEST_LIMIT

def increment_guest():
    key = get_guest_key()
    guest_usage[key]["count"] += 1

def guest_remaining():
    key = get_guest_key()
    today = str(date.today())
    if key not in guest_usage or guest_usage[key]["date"] != today:
        return GUEST_LIMIT
    return max(0, GUEST_LIMIT - guest_usage[key]["count"])

# ── CONVERSATION HISTORY ──
conversation_histories = {}

def get_history():
    if current_user.is_authenticated:
        uid = str(current_user.id)
    else:
        uid = request.remote_addr
    if uid not in conversation_histories:
        conversation_histories[uid] = []
    return conversation_histories[uid]

# ── PAGE ROUTES ──
@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/login")
def login_page():
    return send_from_directory(".", "login.html")

@app.route("/signup")
def signup_page():
    return send_from_directory(".", "signup.html")

# ── AUTH ROUTES ──
@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.json
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not name or not email or not password:
        return jsonify({"success": False, "message": "All fields are required."})

    if User.query.filter_by(email=email).first():
        return jsonify({"success": False, "message": "An account with this email already exists."})

    if len(password) < 6:
        return jsonify({"success": False, "message": "Password must be at least 6 characters."})

    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    user = User(name=name, email=email, password_hash=password_hash)
    db.session.add(user)
    db.session.commit()

    login_user(user)
    return jsonify({"success": True, "message": "Account created successfully!"})

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    user = User.query.filter_by(email=email).first()

    if not user or not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
        return jsonify({"success": False, "message": "Invalid email or password."})

    login_user(user)
    return jsonify({"success": True, "message": "Logged in successfully!"})

@app.route("/api/logout", methods=["POST"])
def logout():
    logout_user()
    return jsonify({"success": True})

@app.route("/api/user")
def get_user():
    if current_user.is_authenticated:
        return jsonify({
            "logged_in": True,
            "name": current_user.name,
            "email": current_user.email,
            "remaining": current_user.questions_remaining(),
            "limit": current_user.get_daily_limit()
        })
    else:
        return jsonify({
            "logged_in": False,
            "remaining": guest_remaining(),
            "limit": GUEST_LIMIT
        })

# ── CHAT ROUTE ──
@app.route("/chat", methods=["POST"])
def chat():
    if current_user.is_authenticated:
        if not current_user.can_ask():
            return jsonify({"error": "limit_reached", "message": "You've used your 20 free questions for today. Come back tomorrow!"}), 429
    else:
        if not check_guest_limit():
            return jsonify({"error": "limit_reached", "message": "You've used your 10 free questions for today. Sign up free for 20 questions! Come back tomorrow."}), 429

    data = request.json
    question = data.get("message", "")
    if not question:
        return jsonify({"error": "No message"}), 400

    history = get_history()
    history.append({"role": "user", "content": question})

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system="You are an expert football analyst called PitchIQ. You specialise in comparing players and teams across different eras. Always give balanced, detailed analysis considering stats, context, era differences, and tactics.",
            messages=history
        )
        answer = response.content[0].text
        history.append({"role": "assistant", "content": answer})

        if current_user.is_authenticated:
            current_user.daily_count += 1
            current_user.last_question_date = str(date.today())
            db.session.commit()
            remaining = current_user.questions_remaining()
        else:
            increment_guest()
            remaining = guest_remaining()

        return jsonify({"response": answer, "remaining": remaining})

    except Exception as e:
        history.pop()
        error_msg = str(e)
        if "credit" in error_msg.lower() or "billing" in error_msg.lower():
            return jsonify({"error": "service_unavailable", "message": "⚽ PitchIQ is temporarily unavailable. Please check back soon!"}), 503
        return jsonify({"error": "service_unavailable", "message": "⚽ Something went wrong. Please try again!"}), 503

# ── SIMULATE ROUTE ──
@app.route("/simulate", methods=["POST"])
def simulate():
    data = request.json
    your_formation = data.get("your_formation", "4-3-3")
    ai_formation = data.get("ai_formation", "4-3-3")
    your_starters = data.get("your_starters", [])
    ai_starters = data.get("ai_starters", [])
    your_team_name = data.get("your_team_name", "Your Team")
    ai_team_name = data.get("ai_team_name", "AI Team")

    score_hint = random.choice([
        "This should be a low scoring tight game (0-0, 1-0, 1-1, 2-1)",
        "This should be a high scoring open game (3-2, 4-3, 3-3, 4-2)",
        "This should be a dominant one-sided win (3-0, 4-0, 4-1, 5-1)",
        "This should be a moderate scoring game (2-0, 2-1, 1-1, 2-2)"
    ])

    prompt = f"""Simulate a football match between these two squads.

{your_team_name} ({your_formation}): {', '.join(your_starters)}
{ai_team_name} ({ai_formation}): {', '.join(ai_starters)}

{score_hint}. Vary the scoreline realistically based on squad quality.

Reply in this exact format only, nothing else:

RESULT: {your_team_name} X - Y {ai_team_name}

SCORERS:
⚽ [minute]' [player] ([{your_team_name} or {ai_team_name}])

WINNER: [{your_team_name} / {ai_team_name} / Draw]

MAN OF THE MATCH: [player name]"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        return jsonify({"result": response.content[0].text})
    except Exception as e:
        return jsonify({"error": "Something went wrong with the simulation"}), 503

# ── KIT ROUTE ──
@app.route("/chat_kit", methods=["POST"])
def chat_kit():
    data = request.json
    messages = data.get("messages", [])
    system = data.get("system", "You are Kit, a helpful assistant.")
    if not messages:
        return jsonify({"error": "No messages"}), 400
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=system,
            messages=messages
        )
        return jsonify({"response": response.content[0].text})
    except Exception as e:
        return jsonify({"error": "Something went wrong"}), 503

# ── CREATE DATABASE AND RUN ──
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))