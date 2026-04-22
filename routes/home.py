from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from models import db, User, DailyLog

home_bp = Blueprint('home_bp', __name__)

@home_bp.route('/get_home_data', methods=['GET'])
def get_home_data():
    user_id = request.args.get('user_id')
    dev_offset_str = request.args.get('dev_offset', '0') # NEW: Catch the offset
    
    if not user_id:
        return jsonify({'status': 'error', 'message': 'user_id required'}), 400
        
    user = User.query.get(user_id)
    if not user:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    try:
        dev_offset = int(dev_offset_str)
    except ValueError:
        dev_offset = 0

    # FIX: Apply Time Machine logic to Home Page
    today = datetime.utcnow().date() + timedelta(days=dev_offset)
    yesterday = today - timedelta(days=1)

    # Fetch Logs
    today_log = DailyLog.query.filter_by(user_id=user_id, date=today).first()
    yesterday_log = DailyLog.query.filter_by(user_id=user_id, date=yesterday).first()

    # Default logic if no log exists for today yet
    if not today_log:
        today_log = DailyLog(user_id=user_id, date=today)
        db.session.add(today_log)
        db.session.commit()

    # 1. Trend Calculations
    def calc_trend(today_val, yesterday_val):
        if yesterday_val == 0:
            return "+0%"
        diff = ((today_val - yesterday_val) / yesterday_val) * 100
        sign = "+" if diff > 0 else ""
        return f"{sign}{int(diff)}%"

    cal_trend = calc_trend(today_log.calories_intake, yesterday_log.calories_intake if yesterday_log else 0)
    work_trend = calc_trend(today_log.workout_mins, yesterday_log.workout_mins if yesterday_log else 0)

    # 2. Dynamic Health Score & BMI Calculation
    health_score = 50 # Baseline starting score
    bmi_status = "Profile Incomplete"
    
    # A. BMI Component (Max 30 points)
    if user.height and user.weight:
        try:
            h_meters = float(user.height) / 100
            bmi = float(user.weight) / (h_meters * h_meters)
            
            if 18.5 <= bmi <= 24.9:
                health_score += 30
                bmi_status = "BMI Optimal"
            elif 25.0 <= bmi <= 29.9:
                health_score += 15
                bmi_status = "BMI Overweight"
            elif bmi < 18.5:
                health_score += 10
                bmi_status = "BMI Underweight"
            else:
                health_score += 5
                bmi_status = "BMI Obese"
        except ValueError:
            pass 

    # B. Nutrition Component (Max 35 points)
    # Strictly enforces a 2000 kcal/day target for all users.
    # Scores highest if intake is close to 2000.
    if today_log.calories_intake > 0:
        if 1800 <= today_log.calories_intake <= 2200: # Within 10% of 2000
            health_score += 35
        elif 1500 <= today_log.calories_intake < 1800 or 2200 < today_log.calories_intake <= 2500: # Within 25% of 2000
            health_score += 20
        else:
            health_score += 10

    # C. Activity Component (Max 35 points)
    # Scores based on hitting workout minutes.
    if today_log.workout_mins >= 30:
        health_score += 35
    elif today_log.workout_mins >= 15:
        health_score += 20
    elif today_log.workout_mins > 0:
        health_score += 10
        
    # Cap score at 100
    health_score = min(100, health_score)

    return jsonify({
        'status': 'success',
        'message': 'Data retrieved',
        'health_score': health_score,
        'health_status': bmi_status,
        'calories': str(today_log.calories_intake), # Send as string for UI parsing
        'calories_trend': cal_trend,
        'workout_mins': str(today_log.workout_mins),
        'workout_trend': work_trend,
        'sleep_duration': "0h 0m", # Placeholder since we moved to Steps
        'sleep_status': "Stable"
    }), 200

# PHASE 21: New route to fetch 7-day history for the Canvas Charts
@home_bp.route('/get_weekly_stats', methods=['GET'])
def get_weekly_stats():
    user_id = request.args.get('user_id')
    dev_offset_str = request.args.get('dev_offset', '0') # NEW: Catch the offset
    
    if not user_id:
        return jsonify({'status': 'error', 'message': 'user_id required'}), 400

    try:
        dev_offset = int(dev_offset_str)
    except ValueError:
        dev_offset = 0

    # FIX: Apply Time Machine logic to Weekly Charts
    today = datetime.utcnow().date() + timedelta(days=dev_offset)
    start_date = today - timedelta(days=6) # Get the last 7 days including today

    logs = DailyLog.query.filter(DailyLog.user_id == user_id, DailyLog.date >= start_date).order_by(DailyLog.date.asc()).all()

    # Initialize empty 7-day arrays
    weekly_burn = [0.0] * 7
    weekly_steps = [0.0] * 7
    
    # Map the database logs to the correct day index
    for log in logs:
        day_index = (log.date - start_date).days
        if 0 <= day_index < 7:
            # Calculate total burn (Workout + Estimated Step Burn)
            workout_cals = log.workout_mins * 8
            step_cals = log.steps_count * 0.04
            weekly_burn[day_index] = float(workout_cals + step_cals)
            weekly_steps[day_index] = float(log.steps_count)

    return jsonify({
        'status': 'success',
        'weekly_burn': weekly_burn,
        'weekly_steps': weekly_steps
    }), 200