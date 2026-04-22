import os
import json
from datetime import datetime
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from models import db, FoodLog, User
from google import genai
from google.genai import types
from models import DailyLog
import os
from dotenv import load_dotenv

scanner_bp = Blueprint('scanner', __name__)

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Ensure temp upload folder exists for scanner
UPLOAD_FOLDER = 'uploads/temp_scans'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@scanner_bp.route('/analyze_food', methods=['POST'])
def analyze_food():
    if 'image' not in request.files or 'user_id' not in request.form:
        return jsonify({"status": "error", "message": "Missing image or user_id"}), 400

    user_id = request.form['user_id']
    expected_food = request.form.get('expected_food') # NEW: Optional param for Strict Auditing
    file = request.files['image']
    
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400

    # Save image temporarily
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        print(f"--- STARTING AI SCAN FOR USER {user_id} ---")
        # Initialize Gemini 2.5 Flash Vision
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Upload to Gemini
        print("Uploading file to Gemini...")
        gemini_file = client.files.upload(file=filepath)
        print("File uploaded successfully!")
        
        # Dynamic Prompt based on Strict Auditor vs Free Scanner
        if expected_food:
            print(f"Strict Auditor Mode: Looking for {expected_food}")
            prompt = f"""
            Analyze this image. The user is prescribed to eat: "{expected_food}".
            1. Is this food generally the same dish/type? If it is a completely different meal (e.g. biryani instead of veg meals), return EXACTLY: {{"error": "mismatch"}}
            2. If it is completely blurry or no food is visible, return EXACTLY: {{"error": "unclear_image"}}
            3. If it IS the correct food, but the portion size is significantly larger, ACCEPT IT but heavily increase the estimated calories accordingly.
            If accepted, return ONLY a valid JSON object (no markdown):
            {{
                "food_name": "Name of food",
                "calories": integer,
                "protein_g": float,
                "carbs_g": float,
                "fats_g": float,
                "confidence": integer from 0 to 100
            }}
            """
        else:
            print("Free Scanner Mode")
            prompt = """
            Analyze this image. If the image is completely blurry, too dark, or does NOT contain any recognizable food, return exactly: {"error": "unclear_image"}
            If it IS food, return ONLY a valid JSON object (no markdown tags):
            {
                "food_name": "Name of food",
                "calories": integer,
                "protein_g": float,
                "carbs_g": float,
                "fats_g": float,
                "confidence": integer from 0 to 100
            }
            """
        
        print("Waiting for AI response...")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[gemini_file, prompt]
        )
        print(f"RAW AI RESPONSE: {response.text}")
        
        # Parse JSON
        clean_text = response.text.strip().replace('```json', '').replace('```', '')
        ai_data = json.loads(clean_text)
        
        # Handle Unclear Image from AI
        if ai_data.get("error") == "unclear_image":
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({"status": "error", "message": "unclear_image"}), 400
            
        # Handle Mismatch Error (Strict Auditor)
        if ai_data.get("error") == "mismatch":
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({"status": "error", "message": "mismatch"}), 400
            
        confidence = ai_data.get('confidence', 0)
        auto_logged = False
        
        # Auto-Logging Logic! ONLY trigger if expected_food is passed (Strict verification)
        if confidence >= 90 and expected_food:
            # FIX: Apply the time machine offset to the auto-logged meal
            from datetime import timedelta
            dev_offset = int(request.form.get('dev_offset', 0))
            today = datetime.utcnow().date() + timedelta(days=dev_offset)
            
            scan_calories = ai_data.get('calories', 0)
            
            # 1. Save specific food item
            new_log = FoodLog(
                user_id=user_id,
                date=today,
                food_name=ai_data.get('food_name', 'Unknown Meal'),
                calories=scan_calories,
                protein_g=ai_data.get('protein_g', 0.0),
                carbs_g=ai_data.get('carbs_g', 0.0),
                fats_g=ai_data.get('fats_g', 0.0),
                meal_type="Scanned Meal"
            )
            db.session.add(new_log)
            
            # 2. Add calories to the DailyLog total!
            daily_summary = DailyLog.query.filter_by(user_id=user_id, date=today).first()
            if not daily_summary:
                daily_summary = DailyLog(user_id=user_id, date=today, calories_intake=scan_calories)
                db.session.add(daily_summary)
            else:
                daily_summary.calories_intake += scan_calories
                
            db.session.commit()
            auto_logged = True
            
        # Clean up temp file
        if os.path.exists(filepath):
            os.remove(filepath)
            
        return jsonify({
            "status": "success",
            "message": "Analysis complete",
            "food_name": ai_data.get('food_name'),
            "calories": ai_data.get('calories'),
            "protein_g": ai_data.get('protein_g'),
            "carbs_g": ai_data.get('carbs_g'),
            "fats_g": ai_data.get('fats_g'),
            "confidence": confidence,
            "auto_logged": auto_logged
        }), 200

    except Exception as e:
        print(f"CRITICAL SCANNER CRASH: {str(e)}") # NEW: This will print the EXACT reason it crashed!
        if os.path.exists(filepath):
            os.remove(filepath)
            
        error_msg = str(e).lower()
        
        # Check for API Quota / Rate Limit errors
        if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
            print("API QUOTA EXCEEDED DETECTED!")
            return jsonify({"status": "error", "message": "quota_exceeded"}), 429
            
        # NEW: Check for Google Server Overload (503)
        if "503" in error_msg or "unavailable" in error_msg or "high demand" in error_msg:
            print("GEMINI SERVERS ARE OVERLOADED!")
            return jsonify({"status": "error", "message": "ai_busy"}), 503
            
        return jsonify({"status": "error", "message": str(e)}), 500


@scanner_bp.route('/log_meal', methods=['POST'])
def log_meal():
    data = request.json
    user_id = data.get('user_id')
    calories = data.get('calories', 0)
    
    # FIX: Apply the time machine offset to the database log
    from datetime import timedelta
    dev_offset = int(data.get('dev_offset', 0))
    today = datetime.utcnow().date() + timedelta(days=dev_offset)
    
    try:
        # 1. Log to FoodLog
        new_log = FoodLog(
            user_id=user_id,
            date=today,
            food_name=data.get('food_name'),
            calories=calories,
            protein_g=data.get('protein_g', 0.0),
            carbs_g=data.get('carbs_g', 0.0),
            fats_g=data.get('fats_g', 0.0),
            meal_type=data.get('meal_type', 'Manual Entry')
        )
        db.session.add(new_log)
        
        # 2. PHASE 21 FIX: Sync with DailyLog so Home Screen updates!
        daily_summary = DailyLog.query.filter_by(user_id=user_id, date=today).first()
        if not daily_summary:
            daily_summary = DailyLog(user_id=user_id, date=today, calories_intake=calories)
            db.session.add(daily_summary)
        else:
            daily_summary.calories_intake += calories
            
        db.session.commit()
        return jsonify({"status": "success", "message": "Meal logged successfully!"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500