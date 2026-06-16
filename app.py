from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
import anthropic
import os

load_dotenv()

app = Flask(__name__)
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

conversation_history = []

@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    question = data.get("message", "")
    if not question:
        return jsonify({"error": "No message"}), 400
    conversation_history.append({"role": "user", "content": question})
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system="You are FootballGPT, an expert football analyst specialising in comparing players and teams across different eras.",
        messages=conversation_history
    )
    answer = response.content[0].text
    conversation_history.append({"role": "assistant", "content": answer})
    return jsonify({"response": answer})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
