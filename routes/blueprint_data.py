from flask import Blueprint, request, jsonify
from models import db, MasterBlueprint, DailyLog, FoodLog, WorkoutLog, UserGoal
from datetime import datetime
import json

blueprint_data_bp = Blueprint('blueprint_data', __name__)

from datetime import timedelta # Ensure timedelta is imported!

@blueprint_data_bp.route('/get_blueprint', methods=['GET'])
def get_blueprint():
    user_id = request.args.get('user_id')
    dev_offset_str = request.args.get('dev_offset', '0') # NEW: Catch the offset
    try:
        dev_offset = int(dev_offset_str)
    except ValueError:
        dev_offset = 0

    blueprint = MasterBlueprint.query.filter_by(user_id=user_id).first()
    
    # NEW: TIME MACHINE LOGIC! Shift the server's perception of "today"
    today = datetime.utcnow().date() + timedelta(days=dev_offset)
    
    # PHASE 15: Exact Macro Fetcher
    today_log = DailyLog.query.filter_by(user_id=user_id, date=today).first()
    consumed_cals = today_log.calories_intake if today_log else 0
    
    food_logs = FoodLog.query.filter_by(user_id=user_id, date=today).all()
    total_protein = sum(log.protein_g for log in food_logs) if food_logs else 0.0
    total_carbs = sum(log.carbs_g for log in food_logs) if food_logs else 0.0
    total_fats = sum(log.fats_g for log in food_logs) if food_logs else 0.0
    
    if blueprint and blueprint.fitness_plan_json:
        # PHASE 17 FIX: Get EXACT start date from UserGoal table!
        active_goal = UserGoal.query.filter_by(user_id=user_id).order_by(UserGoal.id.desc()).first()
        days_active = 0
        
        if active_goal and active_goal.start_date:
            try:
                # Convert "2026-03-29" string to Date object
                start_date_obj = datetime.strptime(active_goal.start_date, "%Y-%m-%d").date()
                days_active = (today - start_date_obj).days
                # Ensure days_active doesn't go negative if there's a timezone glitch
                if days_active < 0:
                    days_active = 0
            except ValueError:
                pass # Fallback to 0 if date format is weird
        
        # NEW: Robust Check-In Logic using last_checkin_week memory!
        # Lockout happens if we've passed a 7-day milestone AND haven't checked in for it yet.
        last_checkin = active_goal.last_checkin_week if active_goal and active_goal.last_checkin_week else 0
        completed_weeks = days_active // 7
        
        if completed_weeks > 0 and (last_checkin < completed_weeks):
            needs_checkin = True
        else:
            needs_checkin = False
        
        # NEW: Create a list of exact food names logged today to send to the phone
        logged_today = [log.food_name for log in food_logs] if food_logs else []
        
        return jsonify({
            "status": "success",
            "message": "Blueprint found",
            "fitness_plan": json.loads(blueprint.fitness_plan_json),
            "nutrition_plan": json.loads(blueprint.nutrition_plan_json) if blueprint.nutrition_plan_json else [],
            "consumed_calories": consumed_cals,
            "protein_g": float(total_protein),
            "carbs_g": float(total_carbs),
            "fats_g": float(total_fats),
            "needs_checkin": needs_checkin, 
            "days_active": days_active,
            "logged_foods": logged_today
        }), 200
    else:
        return jsonify({
            "status": "error", 
            "message": "No blueprint found", 
            "fitness_plan": None,
            "nutrition_plan": None
        }), 200


@blueprint_data_bp.route('/log_workout', methods=['POST'])
def log_workout():
    data = request.json
    user_id = data.get('user_id')
    calories_burned = data.get('calories_burned', 0)
    workout_mins = data.get('workout_mins', 0)
    exercise_type = data.get('exercise_type', 'Workout')
    
    today = datetime.utcnow().date()
    
    try:
        # 1. Log the specific workout
        new_workout = WorkoutLog(
            user_id=user_id, 
            date=today, 
            exercise_type=exercise_type, 
            calories_burned=calories_burned, 
            duration_mins=workout_mins
        )
        db.session.add(new_workout)
        
        # 2. Add to Daily Totals (Safely matching models.py columns!)
        daily_log = DailyLog.query.filter_by(user_id=user_id, date=today).first()
        if not daily_log:
            # FIXED: Removed non-existent columns (sleep_hours, water_ml, calories_burned)
            daily_log = DailyLog(user_id=user_id, date=today, calories_intake=0, workout_mins=0, sleep_mins=0)
            db.session.add(daily_log)
            
        # FIXED: Only updating workout_mins because calories_burned doesn't exist in DailyLog
        daily_log.workout_mins += workout_mins
        
        db.session.commit()
        return jsonify({"status": "success", "message": "Workout saved successfully!"}), 200
        
    except Exception as e:
        db.session.rollback() # CRITICAL FIX: Clears the stuck database session so the UI doesn't wipe out!
        return jsonify({"status": "error", "message": str(e)}), 500