from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Profile Integration Columns
    username = db.Column(db.String(50), unique=True, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    height = db.Column(db.String(10), nullable=True)
    weight = db.Column(db.String(10), nullable=True)
    dob = db.Column(db.String(20), nullable=True) # NEW: Date of Birth
    gender = db.Column(db.String(20), nullable=True) # NEW: Gender for Clinical BMR
    nationality = db.Column(db.String(100), nullable=True) # NEW: Country
    region = db.Column(db.String(100), nullable=True) # NEW: State/City
    profile_image = db.Column(db.String(255), nullable=True)
    streak_count = db.Column(db.Integer, default=0) # NEW: Gamified Streaks

    logs = db.relationship('DailyLog', backref='user', lazy=True)

class DailyLog(db.Model):
    __tablename__ = 'daily_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    calories_intake = db.Column(db.Integer, default=0)
    workout_mins = db.Column(db.Integer, default=0)
    sleep_mins = db.Column(db.Integer, default=0)
    steps_count = db.Column(db.Integer, default=0) # PHASE 19: Added Steps Tracking

class FoodLog(db.Model):
    __tablename__ = 'food_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    food_name = db.Column(db.String(100), nullable=False)
    calories = db.Column(db.Integer, nullable=False)
    protein_g = db.Column(db.Float, default=0.0)
    carbs_g = db.Column(db.Float, default=0.0)
    fats_g = db.Column(db.Float, default=0.0)
    meal_type = db.Column(db.String(50)) # e.g., Breakfast, Lunch, Snack

class WorkoutLog(db.Model):
    __tablename__ = 'workout_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    exercise_type = db.Column(db.String(100), nullable=False)
    duration_mins = db.Column(db.Integer, nullable=False)
    calories_burned = db.Column(db.Integer, nullable=False)
    # FIXED: Removed 'intensity' column as instructed.

class UserGoal(db.Model):
    __tablename__ = 'user_goals'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    goal_type = db.Column(db.String(100), nullable=False) # e.g., Lose Weight, Target Thighs
    target_value = db.Column(db.String(50)) # e.g., 65kg
    start_date = db.Column(db.String(50))
    end_date = db.Column(db.String(50))
    is_feasible = db.Column(db.Boolean, default=False)
    ai_feedback = db.Column(db.Text) # The "Doctor's" advice if timeline is unsafe
    last_checkin_week = db.Column(db.Integer, default=0) # NEW: Tracks the last completed week

class MasterBlueprint(db.Model):
    __tablename__ = 'master_blueprints'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.Date, default=datetime.utcnow().date)
    nutrition_plan_json = db.Column(db.Text) # 7-day meal plan
    fitness_plan_json = db.Column(db.Text)   # 7-day workout plan