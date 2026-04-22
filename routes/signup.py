from flask import Blueprint, request, jsonify
import re
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User

signup_bp = Blueprint('signup_bp', __name__)

@signup_bp.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    full_name = data.get('full_name', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    
    # Strict Backend Validations
    if not full_name or not email or not password:
         return jsonify({'status': 'error', 'message': 'All fields are required.'}), 400
         
    if not re.match(r"^[a-zA-Z]+$", full_name):
         return jsonify({'status': 'error', 'message': 'Name must contain only letters, no spaces.'}), 400
         
    if not re.match(r"^[A-Za-z0-9._%+-]+@(gmail\.com|saveetha\.com|mail\.com)$", email, re.IGNORECASE):
         return jsonify({'status': 'error', 'message': 'Invalid email domain.'}), 400
         
    if not re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*(),.?\":{}|<>])[A-Za-z\d!@#$%^&*(),.?\":{}|<>]{6,8}$", password):
         return jsonify({'status': 'error', 'message': 'Password does not meet strict requirements.'}), 400

    # Check if user email already exists
    if User.query.filter_by(email=email).first():
        return jsonify({'status': 'error', 'message': 'Email already exists! Please login.'}), 409
        
    # Secure Password Hashing (FIXED: Cleaned up indentation)
    hashed_pw = generate_password_hash(password)
    new_user = User(full_name=full_name, email=email, password_hash=hashed_pw)
    
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Registration successful!'}), 201

# PHASE 26: Complete Account Deletion
from models import DailyLog, FoodLog, WorkoutLog, UserGoal, MasterBlueprint

@signup_bp.route('/delete_account', methods=['POST'])
def delete_account():
    data = request.get_json()
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({'status': 'error', 'message': 'user_id required'}), 400
        
    user = User.query.get(user_id)
    if not user:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404
        
    try:
        # Wipe all child records first to avoid foreign key constraints
        DailyLog.query.filter_by(user_id=user_id).delete()
        FoodLog.query.filter_by(user_id=user_id).delete()
        WorkoutLog.query.filter_by(user_id=user_id).delete()
        UserGoal.query.filter_by(user_id=user_id).delete()
        MasterBlueprint.query.filter_by(user_id=user_id).delete()
        
        # Finally, delete the user
        # Finally, delete the user
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({'status': 'success', 'message': 'Account completely deleted'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# PHASE 27: Secure Password Change Route
@signup_bp.route('/change_password', methods=['POST'])
def change_password():
    data = request.get_json()
    user_id = data.get('user_id')
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    
    if not user_id or not current_password or not new_password:
        return jsonify({'status': 'error', 'message': 'All fields are required.'}), 400
        
    user = User.query.get(user_id)
    if not user:
        return jsonify({'status': 'error', 'message': 'User not found.'}), 404
        
    # 1. Verify Current Password
    if not check_password_hash(user.password_hash, current_password):
        return jsonify({'status': 'error', 'message': 'Incorrect current password.'}), 401
        
    # 2. Strict Regex Validation for New Password
    if not re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*(),.?\":{}|<>])[A-Za-z\d!@#$%^&*(),.?\":{}|<>]{6,8}$", new_password):
        return jsonify({'status': 'error', 'message': 'New password does not meet strict requirements.'}), 400
        
    # 3. Hash and Save
    try:
        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Password updated successfully!'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500