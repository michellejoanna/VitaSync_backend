import json
import os
import re
from datetime import datetime
from flask import Blueprint, request, jsonify
from models import db, User, UserGoal, MasterBlueprint
from google import genai
from models import DailyLog # Ensure DailyLog is imported at the top!
from dotenv import load_dotenv

# Load the hidden secrets from the .env file
load_dotenv()

goal_bp = Blueprint('goal_engine', __name__)

# Safely grab the key without hardcoding it!
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

@goal_bp.route('/check_feasibility', methods=['POST'])
def check_feasibility():
    data = request.json
    user_id = data.get('user_id')
    goal_type = data.get('goal_type')
    target = data.get('target')
    start_date = data.get('start_date')
    # IGNORING end_date from phone. Goals are continuous now.

    user = User.query.get(user_id)
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404

    # --- 1. PRE-FLIGHT MEDICAL MATH (Saves API Quota) ---
    try:
        current_weight = float(re.sub(r'[^\d.]', '', str(user.weight)))
        target_weight = float(re.sub(r'[^\d.]', '', str(target)))
        height_cm = float(re.sub(r'[^\d.]', '', str(user.height)))
        
        # CONTINUOUS GOAL: Default math to a safe 90-day trajectory, but UI tracks weekly.
        days = 90
        end_date = "Continuous Tracking"
        
        dob_date = datetime.strptime(user.dob, "%d/%m/%Y")
        age = (datetime.utcnow() - dob_date).days // 365
        
        # Mifflin-St Jeor BMR calculation
        if user.gender and user.gender.lower() == 'female':
            bmr = (10 * current_weight) + (6.25 * height_cm) - (5 * age) - 161
        elif user.gender and user.gender.lower() == 'male':
            bmr = (10 * current_weight) + (6.25 * height_cm) - (5 * age) + 5
        else: # Average for 'Other' or undefined
            bmr_m = (10 * current_weight) + (6.25 * height_cm) - (5 * age) + 5
            bmr_f = (10 * current_weight) + (6.25 * height_cm) - (5 * age) - 161
            bmr = (bmr_m + bmr_f) / 2

        tdee = bmr * 1.2 # Baseline sedentary burn
        
        # Weight loss safety check
        weight_diff = current_weight - target_weight
        if weight_diff > 0 and 'lose' in str(goal_type).lower():
            # 1 kg fat = ~7700 calories
            total_calorie_deficit = weight_diff * 7700
            daily_deficit = total_calorie_deficit / days
            
            # Medical Rule: Max safe deficit is usually 1000 kcal/day, or consuming < 1200 net kcal is dangerous.
            if daily_deficit > 1000 or (tdee - daily_deficit) < 1100:
                safe_days = int(total_calorie_deficit / 750) # Calculate safe timeline at 750 cal deficit/day
                feedback_msg = f"Medical Alert: Losing {weight_diff}kg in {days} days requires a dangerous daily deficit of {int(daily_deficit)} calories, risking malnutrition and muscle loss. A medically safe timeline for this goal is approximately {safe_days} days."
                
                # Save failed attempt to DB and instantly return WITHOUT calling Gemini
                failed_goal = UserGoal(user_id=user_id, goal_type=goal_type, target_value=target, start_date=start_date, end_date=end_date, is_feasible=False, ai_feedback=feedback_msg)
                db.session.add(failed_goal)
                db.session.commit()
                return jsonify({"status": "success", "is_feasible": False, "feedback": feedback_msg}), 200

    except Exception as e:
        print(f"Pre-flight math failed (likely bad format), falling back to Gemini: {e}")
        pass # If math crashes due to weird text inputs, we just let Gemini handle it

    # --- 2. GEMINI AI GENERATION (If Math Passed) ---
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt = f"""
        Act as an expert medical doctor and fitness coach. 
        User Profile: Age {user.dob}, Gender {user.gender}, Height {user.height}, Current Weight {user.weight}, Region {user.region}.
        Goal: {goal_type} to reach {target}.
        Timeline: From {start_date} to {end_date}.
        
        This goal passed the BMR mathematical safety check. Generate the Master Blueprint.
        
        CRITICAL RULE FOR FITNESS PLAN: You may ONLY prescribe exercises from this exact list: [Squats, Push-ups, Pull-ups, Jumping Jacks, Russian Twists]. Do not suggest any other exercises.
        CRITICAL RULE FOR NUTRITION: Include local, culturally appropriate foods for {user.region}.
        
       Return ONLY a strict JSON object:
        {{
            "is_feasible": true,
            "feedback": "A professional 2-sentence encouragement.",
            "fitness_plan": [
                {{"day": "Mon", "focus": "Cardio", "exercise": "Jumping Jacks", "duration_mins": 15, "target_reps": 50}},
                {{"day": "Tue", "focus": "Lower Body", "exercise": "Squats", "duration_mins": 20, "target_reps": 40}}
            ],
            "nutrition_plan": [
                {{"day": "Mon", "meal_type": "Breakfast", "food": "Short Title (e.g. Idli & Sambar)", "description": "Long detailed description of the meal including portion sizes.", "calories": 350, "time": "08:00 AM"}},
                {{"day": "Mon", "meal_type": "Lunch", "food": "Short Title", "description": "Detailed description...", "calories": 500, "time": "01:00 PM"}}
            ]
        }}
        Note: Generate exactly 7 days for the fitness_plan (Mon-Sun). The Android app will automatically rotate this 7-day master schedule across the user's {days}-day timeline. Generate 1 sample day of nutrition with Breakfast, Lunch, and Dinner. Ensure 'food' is a very short title, and 'description' contains the full text.
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        clean_text = response.text.strip().replace('```json', '').replace('```', '')
        ai_data = json.loads(clean_text)
        
        is_feasible = ai_data.get('is_feasible', True)
        
        new_goal = UserGoal(user_id=user_id, goal_type=goal_type, target_value=target, start_date=start_date, end_date=end_date, is_feasible=is_feasible, ai_feedback=ai_data.get('feedback'))
        db.session.add(new_goal)
        
        if is_feasible and 'fitness_plan' in ai_data:
            fitness_json_string = json.dumps(ai_data['fitness_plan'])
            nutrition_json_string = json.dumps(ai_data.get('nutrition_plan', [])) # NEW
            
            existing_blueprint = MasterBlueprint.query.filter_by(user_id=user_id).first()
            if existing_blueprint:
                existing_blueprint.fitness_plan_json = fitness_json_string
                existing_blueprint.nutrition_plan_json = nutrition_json_string # NEW
            else:
                new_blueprint = MasterBlueprint(user_id=user_id, fitness_plan_json=fitness_json_string, nutrition_plan_json=nutrition_json_string)
                db.session.add(new_blueprint)
                
        db.session.commit()
        
        return jsonify({"status": "success", "is_feasible": is_feasible, "feedback": ai_data.get('feedback')}), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        
        error_msg = str(e).lower()
        
        # DEMO MODE FALLBACK: Distinguish between Quota and Traffic
        if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
            fallback_feedback = "[Demo Data] Today limit finished try tomorrow. We have loaded a baseline blueprint."
        elif "503" in error_msg or "unavailable" in error_msg or "high demand" in error_msg:
            fallback_feedback = "[Demo Data] Heavy traffic occurs try again later. We have loaded a baseline blueprint."
        else:
            return jsonify({"status": "error", "message": str(e)}), 500

        print(f"TRIGGERING FEASIBILITY FALLBACK: {fallback_feedback}")
            
        # 1. Save the Goal as Feasible
        new_goal = UserGoal(user_id=user_id, goal_type=goal_type, target_value=target, start_date=start_date, end_date=end_date, is_feasible=True, ai_feedback=fallback_feedback)
        db.session.add(new_goal)
        
        # 2. Hardcode perfectly valid AI response
        fallback_fitness = [
            {"day": "Mon", "focus": "Cardio", "exercise": "Jumping Jacks", "duration_mins": 15, "target_reps": 60},
            {"day": "Tue", "focus": "Lower Body", "exercise": "Squats", "duration_mins": 20, "target_reps": 40},
            {"day": "Wed", "focus": "Upper Body", "exercise": "Push-ups", "duration_mins": 15, "target_reps": 30},
            {"day": "Thu", "focus": "Core", "exercise": "Russian Twists", "duration_mins": 15, "target_reps": 50},
            {"day": "Fri", "focus": "Full Body", "exercise": "Jumping Jacks", "duration_mins": 20, "target_reps": 60},
            {"day": "Sat", "focus": "Lower Body", "exercise": "Squats", "duration_mins": 15, "target_reps": 30},
            {"day": "Sun", "focus": "Rest", "exercise": "Rest", "duration_mins": 0, "target_reps": 0}
        ]
        fallback_nutrition = [
            {"day": "Mon", "meal_type": "Breakfast", "food": "High Protein Oats", "description": "Oats with nuts and seeds.", "calories": 350, "time": "08:00 AM"},
            {"day": "Mon", "meal_type": "Lunch", "food": "Grilled Chicken & Veggies", "description": "Lean chicken breast with steamed broccoli.", "calories": 450, "time": "01:00 PM"},
            {"day": "Mon", "meal_type": "Dinner", "food": "Lentil Soup", "description": "Warm bowl of high-protein lentil soup.", "calories": 400, "time": "07:30 PM"}
        ]
        
        fitness_json_string = json.dumps(fallback_fitness)
        nutrition_json_string = json.dumps(fallback_nutrition)
        
        existing_blueprint = MasterBlueprint.query.filter_by(user_id=user_id).first()
        if existing_blueprint:
            existing_blueprint.fitness_plan_json = fitness_json_string
            existing_blueprint.nutrition_plan_json = nutrition_json_string
        else:
            new_blueprint = MasterBlueprint(user_id=user_id, fitness_plan_json=fitness_json_string, nutrition_plan_json=nutrition_json_string)
            db.session.add(new_blueprint)
            
        db.session.commit()
        
        return jsonify({
            "status": "success", 
            "is_feasible": True, 
            "feedback": fallback_feedback
        }), 200

# NEW: Route to delete an active blueprint
from models import FoodLog, WorkoutLog # NEW IMPORT FOR DELETION

# NEW: Route to delete an active blueprint and wipe today's logs so UI resets to 0!
@goal_bp.route('/cancel_goal', methods=['POST'])
def cancel_goal():
    data = request.json
    user_id = data.get('user_id')
    
    blueprint = MasterBlueprint.query.filter_by(user_id=user_id).first()
    if blueprint:
        db.session.delete(blueprint)
        
        # FIX: We NO LONGER delete FoodLog, WorkoutLog, or DailyLog!
        # This protects the Home Page steps/calories forever.
        db.session.commit()
        return jsonify({"status": "success", "message": "Goal successfully deleted. Daily logs retained."}), 200
        
    return jsonify({"status": "error", "message": "No active blueprint found."}), 404 

# --- PHASE 13: THE CUSTOMIZATION & PROGRESSION ENGINE ---

@goal_bp.route('/get_swap_options', methods=['POST'])
def get_swap_options():
    data = request.json
    user_id = data.get('user_id')
    meal_type = data.get('meal_type') 
    target_cals = data.get('target_calories') 
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404
        
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Act as a professional dietitian. The user lives in {user.region}, {user.nationality}.
        They want to swap their {meal_type}. It MUST be exactly around {target_cals} calories.
        Provide 3 localized, culturally appropriate {meal_type} alternatives.
        
        Return ONLY a strict JSON array (no markdown tags):
        [
            {{"meal_type": "{meal_type}", "food": "Short Title 1", "description": "Detailed description...", "calories": {target_cals}, "time": "Same time as usual"}},
            {{"meal_type": "{meal_type}", "food": "Short Title 2", "description": "Detailed description...", "calories": {target_cals}, "time": "Same time as usual"}},
            {{"meal_type": "{meal_type}", "food": "Short Title 3", "description": "Detailed description...", "calories": {target_cals}, "time": "Same time as usual"}}
        ]
        """
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        clean_text = response.text.strip().replace('```json', '').replace('```', '')
        options = json.loads(clean_text)
        
        return jsonify({"status": "success", "options": options}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@goal_bp.route('/update_nutrition', methods=['POST'])
def update_nutrition():
    data = request.json
    user_id = data.get('user_id')
    new_nutrition_plan = data.get('nutrition_plan')
    
    blueprint = MasterBlueprint.query.filter_by(user_id=user_id).first()
    if blueprint:
        blueprint.nutrition_plan_json = json.dumps(new_nutrition_plan)
        db.session.commit()
        return jsonify({"status": "success", "message": "Blueprint customized successfully!"}), 200
    return jsonify({"status": "error", "message": "No blueprint found."}), 404

@goal_bp.route('/weekly_update', methods=['POST'])
def weekly_update():
    data = request.json
    user_id = data.get('user_id')
    user_feedback = data.get('feedback') 
    
    user = User.query.get(user_id)
    goal = UserGoal.query.filter_by(user_id=user_id).order_by(UserGoal.id.desc()).first()
    blueprint = MasterBlueprint.query.filter_by(user_id=user_id).first()
    
    if not user or not blueprint or not goal:
        return jsonify({"status": "error", "message": "Data missing."}), 404
        
    # --- PHASE 15: SUCCESS CHECKER LOGIC ---
    try:
        # CRASH FIX: Safely parse floats. If target is text like "Build Muscle", this prevents ValueError!
        current_weight_str = re.sub(r'[^\d.]', '', str(user.weight))
        current_weight = float(current_weight_str) if current_weight_str else 0.0
        
        target_weight_str = re.sub(r'[^\d.]', '', str(goal.target_value))
        target_weight = float(target_weight_str) if target_weight_str else 0.0
        
        is_loss = 'lose' in str(goal.goal_type).lower()
        
        goal_achieved = False
        if target_weight > 0: # Only check for achievement if a numeric target exists!
            if is_loss and current_weight <= target_weight:
                goal_achieved = True
            elif not is_loss and current_weight >= target_weight:
                goal_achieved = True
            
        if goal_achieved:
            # Calculate exactly how many days it took to hit the goal!
            start_date_obj = datetime.strptime(goal.start_date, "%Y-%m-%d").date()
            days_taken = (datetime.utcnow().date() - start_date_obj).days
            
            return jsonify({
                "status": "success", 
                "goal_achieved": True,
                "ai_response": f"Congratulations! You reached your target in {days_taken} days!"
            }), 200

        # If not achieved, dynamically calculate the NEXT week
        current_completed_week = goal.last_checkin_week if goal.last_checkin_week is not None else 0
        next_week = current_completed_week + 2 

        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Act as an expert medical doctor and fitness coach.
        User Profile: Age {user.dob}, Gender {user.gender}, Current Weight {user.weight}.
        Master Goal: {goal.goal_type} to reach {goal.target_value}.
        
        Week {next_week - 1} Check-in Feedback from User: "{user_feedback}"
        
        Based on this feedback, generate a slightly adjusted, more optimized Week {next_week} Blueprint.
        CRITICAL RULE: You may ONLY prescribe exercises from: [Squats, Push-ups, Pull-ups, Jumping Jacks, Russian Twists].
        
        Return ONLY a strict JSON object:
        {{
            "feedback": "A short, encouraging doctor's response to their specific feedback.",
            "fitness_plan": [
                {{"day": "Mon", "focus": "Cardio", "exercise": "Jumping Jacks", "duration_mins": 15, "target_reps": 60}}
            ],
            "nutrition_plan": [
                {{"day": "Mon", "meal_type": "Breakfast", "food": "Title", "description": "Desc", "calories": 350, "time": "08:00 AM"}}
            ]
        }}
        Note: Generate 7 days for fitness, and 1 sample day (3 meals) for nutrition. Adjust reps/calories based on their feedback.
        """
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        clean_text = response.text.strip().replace('```json', '').replace('```', '')
        ai_data = json.loads(clean_text)
        
        blueprint.fitness_plan_json = json.dumps(ai_data.get('fitness_plan', []))
        blueprint.nutrition_plan_json = json.dumps(ai_data.get('nutrition_plan', []))
        
        # PHASE 16: Update the check-in memory so the server knows the next week is unlocked!
        if goal.last_checkin_week is None:
            goal.last_checkin_week = 0
        goal.last_checkin_week += 1
        
        db.session.commit()
        
        return jsonify({
            "status": "success", 
            "goal_achieved": False,
            "message": f"Week {next_week} Plan Generated!", 
            "ai_response": ai_data.get('feedback', 'Keep up the good work!')
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc() 
        
        error_msg = str(e).lower()
        
        # Calculate the next week dynamically for the fallback message too!
        current_completed_week = goal.last_checkin_week if goal.last_checkin_week is not None else 0
        next_week = current_completed_week + 2 
        
        # DEMO MODE FALLBACK: Distinguish between Quota and Traffic
        if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
            ai_response = f"[Demo Data] Today limit finished try tomorrow. Week {next_week} plan loaded!"
        elif "503" in error_msg or "unavailable" in error_msg or "high demand" in error_msg:
            ai_response = f"[Demo Data] Heavy traffic occurs try again later. Week {next_week} plan loaded!"
        else:
            return jsonify({"status": "error", "message": str(e)}), 500

        print(f"TRIGGERING WEEKLY FALLBACK: {ai_response}")
            
        # Hardcoded perfectly valid AI response
        fallback_fitness = [
            {"day": "Mon", "focus": "Cardio", "exercise": "Jumping Jacks", "duration_mins": 15, "target_reps": 60},
            {"day": "Tue", "focus": "Lower Body", "exercise": "Squats", "duration_mins": 20, "target_reps": 40},
            {"day": "Wed", "focus": "Upper Body", "exercise": "Push-ups", "duration_mins": 15, "target_reps": 30},
            {"day": "Thu", "focus": "Core", "exercise": "Russian Twists", "duration_mins": 15, "target_reps": 50},
            {"day": "Fri", "focus": "Full Body", "exercise": "Jumping Jacks", "duration_mins": 20, "target_reps": 60},
            {"day": "Sat", "focus": "Lower Body", "exercise": "Squats", "duration_mins": 15, "target_reps": 30},
            {"day": "Sun", "focus": "Rest", "exercise": "Rest", "duration_mins": 0, "target_reps": 0}
        ]
        fallback_nutrition = [
            {"day": "Mon", "meal_type": "Breakfast", "food": "High Protein Oats", "description": "Oats with nuts and seeds.", "calories": 350, "time": "08:00 AM"},
            {"day": "Mon", "meal_type": "Lunch", "food": "Grilled Chicken & Veggies", "description": "Lean chicken breast with steamed broccoli.", "calories": 450, "time": "01:00 PM"},
            {"day": "Mon", "meal_type": "Dinner", "food": "Lentil Soup", "description": "Warm bowl of high-protein lentil soup.", "calories": 400, "time": "07:30 PM"}
        ]
        
        blueprint.fitness_plan_json = json.dumps(fallback_fitness)
        blueprint.nutrition_plan_json = json.dumps(fallback_nutrition)
        
        if goal.last_checkin_week is None:
            goal.last_checkin_week = 0
        goal.last_checkin_week += 1
        
        db.session.commit()
        
        return jsonify({
            "status": "success", 
            "goal_achieved": False,
            "message": f"Week {next_week} Plan Generated!", 
            "ai_response": ai_response
        }), 200