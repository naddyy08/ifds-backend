# routes/auth.py
from flask import Blueprint, request, jsonify
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt_identity,
    get_jwt
)
from models import db, User, AuditLog
from datetime import datetime
import re

auth_bp = Blueprint('auth', __name__)
bcrypt = Bcrypt()


def validate_password_strength(password):
    """
    Validate password meets security requirements
    Returns (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r"\d", password):
        return False, "Password must contain at least one number"

    return True, None


# ============================================
# REGISTER NEW USER
# ============================================
@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register a new user.
    Role is ALWAYS set to 'staff' regardless of what is sent.
    Only admin can change roles via the user management panel.
    Expected JSON: {username, email, password}
    """
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['username', 'email', 'password']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Validate username length
        if len(data['username']) < 3:
            return jsonify({'error': 'Username must be at least 3 characters long'}), 400

        # Validate email format
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, data['email']):
            return jsonify({'error': 'Invalid email format'}), 400

        # Check if username already exists
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'error': 'Username already exists'}), 409

        # Check if email already exists
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already exists'}), 409

        # Validate password strength
        is_valid, error_msg = validate_password_strength(data['password'])
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        # Hash password
        password_hash = bcrypt.generate_password_hash(data['password']).decode('utf-8')

        # ✅ SECURITY FIX: Always assign 'staff' role — ignore any role sent from frontend
        assigned_role = 'staff'

        # Create new user
        new_user = User(
            username=data['username'],
            email=data['email'],
            password_hash=password_hash,
            role=assigned_role
        )

        db.session.add(new_user)
        db.session.commit()

        # Log the action
        log = AuditLog(
            user_id=new_user.id,
            action='USER_REGISTERED',
            details=f'New staff user registered: {data["username"]}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'message': 'User registered successfully',
            'user': new_user.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# LOGIN
# ============================================
@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()

        if not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Username and password are required'}), 400

        user = User.query.filter_by(username=data['username']).first()

        if not user:
            log = AuditLog(
                user_id=None,
                action='FAILED_LOGIN_ATTEMPT',
                details=f'Failed login attempt for username: {data["username"]}',
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()

            return jsonify({'error': 'Invalid credentials'}), 401

        if not user.is_active:
            return jsonify({'error': 'Account is deactivated. Please contact administrator.'}), 403

        if not bcrypt.check_password_hash(user.password_hash, data['password']):
            log = AuditLog(
                user_id=user.id,
                action='FAILED_LOGIN_ATTEMPT',
                details=f'Failed login attempt - wrong password for: {user.username}',
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()

            return jsonify({'error': 'Invalid credentials'}), 401

        # Create JWT token with role claims
        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={
                'username': user.username,
                'role': user.role,
                'email': user.email
            }
        )

        # Log successful login
        log = AuditLog(
            user_id=user.id,
            action='USER_LOGIN',
            details=f'User logged in successfully (Role: {user.role})',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'user': user.to_dict()
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# GET CURRENT USER PROFILE
# ============================================
@auth_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_profile():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))

        if not user:
            return jsonify({'error': 'User not found'}), 404

        return jsonify({'user': user.to_dict()}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# LOGOUT (For audit trail)
# ============================================
@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    try:
        user_id = get_jwt_identity()

        log = AuditLog(
            user_id=int(user_id),
            action='USER_LOGOUT',
            details='User logged out',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({'message': 'Logout successful'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# CHANGE PASSWORD
# ============================================
@auth_bp.route('/change-password', methods=['PUT'])
@jwt_required()
def change_password():
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        if not data.get('current_password') or not data.get('new_password'):
            return jsonify({'error': 'Current and new password are required'}), 400

        is_valid, error_msg = validate_password_strength(data['new_password'])
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        user = User.query.get(int(user_id))

        if not user:
            return jsonify({'error': 'User not found'}), 404

        if not bcrypt.check_password_hash(user.password_hash, data['current_password']):
            log = AuditLog(
                user_id=int(user_id),
                action='FAILED_PASSWORD_CHANGE',
                details='Failed password change attempt - wrong current password',
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()

            return jsonify({'error': 'Current password is incorrect'}), 401

        user.password_hash = bcrypt.generate_password_hash(
            data['new_password']
        ).decode('utf-8')
        db.session.commit()

        log = AuditLog(
            user_id=int(user_id),
            action='PASSWORD_CHANGED',
            details='User changed password successfully',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({'message': 'Password changed successfully'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500