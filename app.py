from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
import anthropic
import os
from datetime import date

load_dotenv()

app = Flask(__name__)
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

conversation_history = []
user_usage = {}
DAILY_LIMIT = 10

def get_user_key(request):
    return request.remote_addr

def check_limit(user_key):
    today = str(date.today())
    if user_key not in user_usage:
        user_usage[user_key] = {"date": today, "count": 0}
    if user_usage[user_key]["date"] != today:
        user_usage[user_key] = {"date": today, "count": 0}
    return user_usage[user_key]["count"] < DAILY_LIMIT

def increment_usage(user_key):
    user_usage[user_key]["count"] += 1

def questions_remaining(user_key):
    today = str(date.today())
    if user_key not in user_usage:
        return DAILY_LIMIT
    if user_usage[user_key]["date"] != today:
        return DAILY_LIMIT
    return DAILY_LIMIT - user_usage[user_key]["count"]

@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_key = get_user_key(request)
    if not check_limit(user_key):
        return jsonify({"error": "limit_reached", "message": "You've used your 10 free questions for today. Come back tomorrow!"}), 429
    data = request.json
    question = data.get("message", "")
    if not question:
        return jsonify({"error": "No message"}), 400
    conversation_history.append({"role": "user", "content": question})
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system="You are FootballGPT, an expert football analyst specialising in comparing players and teams across different eras.",
            messages=conversation_history
        )
        answer = response.content[0].text
        conversation_history.append({"role": "assistant", "content": answer})
        increment_usage(user_key)
        remaining = questions_remaining(user_key)
        return jsonify({"response": answer, "remaining": remaining})
    except Exception as e:
        conversation_history.pop()
        error_msg = str(e)
        if "credit" in error_msg.lower() or "billing" in error_msg.lower():
            return jsonify({"error": "service_unavailable", "message": "⚽ FootballGPT is temporarily unavailable due to high demand. Please check back soon!"}), 503
        return jsonify({"error": "service_unavailable", "message": "⚽ Something went wrong. Please try again in a moment!"}), 503

@app.route("/simulate", methods=["POST"])
def simulate():
    data = request.json
    your_formation = data.get("your_formation", "4-3-3")
    ai_formation = data.get("ai_formation", "4-3-3")
    your_starters = data.get("your_starters", [])
    ai_starters = data.get("ai_starters", [])

    prompt = f"""Simulate a football match between these two squads.

YOUR TEAM ({your_formation}): {', '.join(your_starters)}
AI TEAM ({ai_formation}): {', '.join(ai_starters)}

Reply in this exact format only, nothing else:

RESULT: Your Team X - Y AI Team

SCORERS:
⚽ [minute]' [player] ([Your Team or AI Team])

WINNER: [Your Team / AI Team / Draw]

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))