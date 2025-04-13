import os
import openai
import logging
import sqlite3
import threading
import time
from flask import Flask, request, jsonify

# OpenAI Key
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("Missing OpenAI API Key. Use: export OPENAI_API_KEY='your-key'")

# Flask App
app = Flask(__name__)

# Follow-up + business session memory
session_data = {
    "follow_up_needed": {},
    "last_message_time": {}
}

# SQLite FAQ Setup
DB_FILE = "assistbot.db"
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS faqs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT UNIQUE,
            answer TEXT
        )
    """)
    conn.commit()
    conn.close()
init_db()

# In-memory business data (replace with DB later)
business_profiles = {}

# ========== API ROUTES ========== #

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "")
    business_id = data.get("business_id", "default_business")
    user_id = data.get("user_id", "user")

    if business_id not in business_profiles:
        return jsonify({"response": "❗ Please sign up first before chatting."})

    return jsonify({"response": generate_response(message, business_id, user_id)})

@app.route("/start-trial", methods=["POST"])
def start_trial():
    data = request.form
    business_name = data.get("business_name")
    order_tracking = data.get("order_tracking") == "yes"
    orders_input = data.get("orders", "")

    orders = {}
    if order_tracking and orders_input:
        for entry in orders_input.split(","):
            if ":" in entry:
                oid, status = entry.split(":")
                orders[oid.strip()] = status.strip()

    business_id = business_name.lower().replace(" ", "_")
    business_profiles[business_id] = {
        "name": business_name,
        "orders": orders,
        "trial": True
    }

    return f"✅ {business_name} is now on a free trial and ready to use AssistBot!"

@app.route("/add_faq", methods=["POST"])
def add_faq():
    data = request.json
    question = data.get("question")
    answer = data.get("answer")

    if not question or not answer:
        return jsonify({"error": "Both question and answer are required."}), 400

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO faqs (question, answer) VALUES (?, ?)", (question.lower(), answer))
    conn.commit()
    conn.close()

    return jsonify({"message": "FAQ added successfully."})

# ========== MAIN CHAT LOGIC ========== #

def generate_response(user_message, business_id, user_id):
    session_data["last_message_time"][user_id] = time.time()

    # Handle order tracking
    if "order status" in user_message.lower():
        order_id = user_message.split()[-1]
        profile = business_profiles.get(business_id, {})
        return profile.get("orders", {}).get(order_id, "Order not found.")

    # Check stored FAQs
    faq_answer = get_faq_answer(user_message)
    if faq_answer:
        schedule_follow_up(user_id)
        return faq_answer

    # Store unanswered question
    save_unanswered(user_message)

    # Use OpenAI for fallback
    try:
        reply = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Always respond with clear, friendly answers."},
                {"role": "user", "content": user_message}
            ]
        )
        schedule_follow_up(user_id)
        return reply["choices"][0]["message"]["content"]
    except Exception as e:
        logging.error(f"OpenAI error: {e}")
        return "Sorry, I couldn't process your request right now."

# ========== FAQ & FOLLOW-UP FUNCTIONS ========== #

def get_faq_answer(question):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT answer FROM faqs WHERE question = ?", (question.lower(),))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def save_unanswered(question):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO faqs (question, answer) VALUES (?, ?)", (question.lower(), None))
    conn.commit()
    conn.close()

def schedule_follow_up(user_id):
    if not session_data["follow_up_needed"].get(user_id):
        session_data["follow_up_needed"][user_id] = True
        threading.Timer(300, send_follow_up, args=[user_id]).start()  # 5 minutes = 300 seconds

def send_follow_up(user_id):
    if session_data["follow_up_needed"].get(user_id):
        session_data["follow_up_needed"][user_id] = False
        print(f"\n[Follow-up to {user_id}]: Did I resolve your issue? (Yes/No)")

# ========== MAIN ========== #

if __name__ == "__main__":
    print("\U0001F680 AssistBot is running...")
    app.run(host="0.0.0.0", port=8080)

























    