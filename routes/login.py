from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash
from models import db, User

# Create Blueprint
login_bp = Blueprint('login_bp', __name__)

@login_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'status': 'error', 'message': 'Email and password are required.'}), 400

    user = User.query.filter_by(email=email).first()
    
    if user and check_password_hash(user.password_hash, password):
        # Returning full_name so Android can display it on the Home Page
        return jsonify({'status': 'success', 'message': 'Login successful!', 'user_id': user.id, 'full_name': user.full_name}), 200
    else:
        return jsonify({'status': 'error', 'message': 'Invalid email or password.'}), 401