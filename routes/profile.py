from flask import Blueprint, request, jsonify
import os
import re
from werkzeug.utils import secure_filename
from models import db, User

profile_bp = Blueprint('profile_bp', __name__)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@profile_bp.route('/get_profile', methods=['GET'])
def get_profile():
    user_id = request.args.get('user_id')
    user = User.query.get(user_id)
    if not user:
        return jsonify({'status': 'error', 'message': 'User not found.'}), 404

    return jsonify({
        'status': 'success',
        'username': user.username or "",
        'full_name': user.full_name or "",
        'phone': user.phone or "",
        'height': user.height or "",
        'weight': user.weight or "",
        'dob': user.dob or "",
        'gender': user.gender or "", # NEW
        'nationality': user.nationality or "",
        'region': user.region or "",
        'profile_image': user.profile_image or "" # NEW
    }), 200

@profile_bp.route('/update_profile', methods=['POST'])
def update_profile():
    user_id = request.form.get('user_id')
    user = User.query.get(user_id)

    if not user:
        return jsonify({'status': 'error', 'message': 'User not found.'}), 404

    # Username Logic
    new_username = request.form.get('username', user.username)
    if new_username and new_username != user.username:
        if User.query.filter_by(username=new_username).first():
            return jsonify({'status': 'error', 'message': 'Username already taken!'}), 409
        if ' ' in new_username:
            return jsonify({'status': 'error', 'message': 'Username cannot contain spaces.'}), 400
        user.username = new_username

    # Phone Logic
    new_phone = request.form.get('phone', user.phone)
    if new_phone and not re.match(r"^\d{10}$", new_phone.replace("-", "").replace(" ", "").replace("+", "")):
        return jsonify({'status': 'error', 'message': 'Phone must be exactly 10 digits.'}), 400
    user.phone = new_phone

    # Update Text Fields & New Demographics
    user.full_name = request.form.get('full_name', user.full_name)
    user.height = request.form.get('height', user.height)
    user.weight = request.form.get('weight', user.weight)
    user.dob = request.form.get('dob', user.dob)
    user.gender = request.form.get('gender', user.gender) # NEW
    user.nationality = request.form.get('nationality', user.nationality)
    user.region = request.form.get('region', user.region)

    # Handle Image Upload (CRASH FIX IMPLEMENTED)
    # Handle Image Upload (CRASH FIX & AUTO-CLEANUP IMPLEMENTED)
    if 'profile_image' in request.files:
        file = request.files['profile_image']
        if file and allowed_file(file.filename):
            os.makedirs(UPLOAD_FOLDER, exist_ok=True) # THIS FIXES THE CRASH
            
            # Auto-Cleanup: Delete old profile image to save server space!
            if user.profile_image and os.path.exists(user.profile_image):
                try:
                    os.remove(user.profile_image)
                except Exception:
                    pass # Ignore if file doesn't exist or is locked
                    
            filename = secure_filename(f"user_{user_id}_{file.filename}")
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            user.profile_image = filepath

    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Profile updated successfully!'}), 200