import sqlite3
import requests
import json
import os
from dotenv import load_dotenv
from google import genai
from flask import Flask, request, jsonify
from flask_cors import CORS

load_dotenv()  # Load environment variables from .env

app = Flask(__name__)
CORS(app)

def setup_database():
    connection = sqlite3.connect("vibefit.db")
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_vibe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT DEFAULT CURRENT_TIMESTAMP,
            energy_level INTEGER,
            available_time INTEGER,
            focus_area TEXT,
            recommended_workout TEXT
        )
    """)
    connection.commit()
    connection.close()

def save_user_log(energy, time, focus_area, workout_name):
    connection = sqlite3.connect("vibefit.db")
    cursor = connection.cursor()
    cursor.execute("""
        INSERT INTO user_vibe (energy_level, available_time, focus_area, recommended_workout)
        VALUES (?, ?, ?, ?)
    """, (energy, time, focus_area, workout_name))
    connection.commit()
    connection.close()
    print(f"Saved -> Energy: {energy}%, Time: {time}m, Focus: {focus_area}")

def get_latest_vibe():
    connection = sqlite3.connect("vibefit.db")
    cursor = connection.cursor()
    cursor.execute("""
        SELECT energy_level, available_time, focus_area 
        FROM user_vibe 
        ORDER BY id DESC 
        LIMIT 1
    """)
    result = cursor.fetchone()
    connection.close()
    
    if result:
        return result[0], result[1], result[2]  # Returns energy, time, and focus
    return None, None, None
    
# Updated: Reads a local mock file to bypass the MuscleWiki paywall
def get_exercise_pool():
    print("Reading exercise pool from mock_exercises.json...")
    try:
        with open("mock_exercises.json", "r") as file:
            data = json.load(file)
            print(f"Success! Fetched {len(data)} exercises from mock data.")
            return data
    except Exception as e:
        print(f"Failed to read mock data: {e}")
        return None
    
def generate_llm_workout(energy, time, focus, exercises):
    print("\n--- Sending Data to the LLM Brain ---")
    
    prompt = f"""
    You are the AI engine for VibeFit, an intelligent workout app.
    
    User Context:
    - Current Energy Level: {energy}%
    - Available Time: {time} minutes
    - Focus Area: {focus}
    
    Candidate Exercise Pool (JSON):
    {json.dumps(exercises, indent=2)}
    
    Your Task:
    1. Filter the pool to prioritize the user's Focus Area.
    2. Adjust difficulty based on energy (< 40% = easy, > 70% = hard).
    3. Fit the routine into the {time}-minute limit.
    4. Return your final choice strictly as a JSON list. 
    
    Each exercise in the JSON must have exactly these three keys:
    - "name": The exercise name.
    - "ai_reason": 1 sentence explaining why it matches their vibe and focus.
    - "points": An integer (e.g., 5 for easy, 10 for medium, 15 for hard).
    
    Respond ONLY with the raw JSON list. No conversational text.
    """
    print("Asking the AI to generate a plan...")
    
    # 1. Initialize the Gemini Client (Paste your key here!)
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    
    # 2. Call the real LLM (Gemini 3.5 Flash is incredibly fast and great at JSON)
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt
    )
    
    # 3. Clean the response and convert it into a Python list
    try:
        # LLMs sometimes wrap JSON in markdown blocks (```json), so we strip those out
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        workout_plan = json.loads(clean_text)
        return workout_plan
    except Exception as e:
        print("Error parsing LLM response:", e)
        print("Raw AI text was:", response.text)
        return None
    
def adjust_workout_mid_session(remaining_time, new_energy, current_exercise_pool):
    print(f"\n⚡ ALERT: Jimmy changed his settings mid-workout! New Energy: {new_energy}%, Time Left: {remaining_time}m")
    
    # We need to grab his current focus so we don't accidentally lose it
    _, _, current_focus = get_latest_vibe()
    
    # 1. Save this new sudden drop into our SQLite database
    save_user_log(new_energy, remaining_time, current_focus, "Recalculating mid-workout...")
    
    # 2. Re-read the database to make sure our state is perfectly synced
    latest_energy, latest_time, latest_focus = get_latest_vibe()
    
    # 3. Call the LLM brain again with the updated conditions!
    print("Asking the LLM to dynamically adjust the remaining routine...")
    adjusted_workout = generate_llm_workout(latest_energy, latest_time, latest_focus, current_exercise_pool)
    
    return adjusted_workout

# NEW: The API Endpoint that frontend will talk to
@app.route('/api/generate_workout', methods=['POST'])
def api_generate_workout():
    # 1. Catch the data sent from the UI (Energy, Time, Focus)
    incoming_data = request.json
    ui_energy = incoming_data.get("energy")
    ui_time = incoming_data.get("time")
    ui_focus = incoming_data.get("focus")
    
    print(f"\n📞 API RECEIVED CALL -> Energy: {ui_energy}%, Time: {ui_time}m, Focus: {ui_focus}")

    # 2. Save it to SQLite 
    save_user_log(ui_energy, ui_time, ui_focus, "Generating via API...")
    
    # 3. Load exercises and trigger the LLM Brain
    exercise_pool = get_exercise_pool()
    if exercise_pool:
        workout_plan = generate_llm_workout(ui_energy, ui_time, ui_focus, exercise_pool)
        
        # 4. Send the final JSON straight back to the frontend screen
        return jsonify(workout_plan)
    else:
        return jsonify({"error": "Failed to load exercises"}), 500
# NEW: The API Endpoint for when Jimmy changes his energy mid-workout
@app.route('/api/adapt_workout', methods=['POST'])
def api_adapt_workout():
    incoming_data = request.json
    ui_remaining_time = incoming_data.get("time")
    ui_new_energy = incoming_data.get("energy")
    
    print(f"\n⚡ API RECEIVED MID-WORKOUT ALERT -> New Energy: {ui_new_energy}%, Time Left: {ui_remaining_time}m")
    
    # Trigger your mid-session adjustment logic
    exercise_pool = get_exercise_pool()
    if exercise_pool:
        adapted_plan = adjust_workout_mid_session(ui_remaining_time, ui_new_energy, exercise_pool)
        return jsonify(adapted_plan)
    else:
        return jsonify({"error": "Failed to load exercises"}), 500
    
# Start the Server!
if __name__ == "__main__":
    setup_database()
    print("🚀 VibeFit Server is awake and listening on http://127.0.0.1:5000 ...")
    app.run(debug=True, port=5000)