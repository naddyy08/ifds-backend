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

auth_bp = Blueprint('auth', __name__)
bcrypt = Bcrypt()

# ============================================
# REGISTER NEW USER (Admin Only)
# ============================================
@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register a new user
    Expected JSON: {username, email, password, role}
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['username', 'email', 'password', 'role']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Check if username already exists
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'error': 'Username already exists'}), 409
        
        # Check if email already exists
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already exists'}), 409
        
        # Validate role
        valid_roles = ['admin', 'manager', 'staff']
        if data['role'] not in valid_roles:
            return jsonify({'error': 'Invalid role. Must be: admin, manager, or staff'}), 400
        
        # Hash password
        password_hash = bcrypt.generate_password_hash(data['password']).decode('utf-8')
        
        # Create new user
        new_user = User(
            username=data['username'],
            email=data['email'],
            password_hash=password_hash,
            role=data['role']
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        # Log the action
        log = AuditLog(
            user_id=new_user.id,
            action='USER_REGISTERED',
            details=f'New {data["role"]} user registered',
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
            return jsonify({'error': 'Invalid credentials'}), 401
        
        if not user.is_active:
            return jsonify({'error': 'Account is deactivated'}), 403
        
        if not bcrypt.check_password_hash(user.password_hash, data['password']):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # ✅ FIXED: identity must be a STRING
        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={        # ← Store extra info here
                'username': user.username,
                'role': user.role,
                'email': user.email
            }
        )
        
        log = AuditLog(
            user_id=user.id,
            action='USER_LOGIN',
            details='User logged in successfully',
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
        # ✅ FIXED: identity is now a string (user ID)
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# LOGOUT (Optional - for audit trail)
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
        
        user = User.query.get(int(user_id))
        
        if not bcrypt.check_password_hash(user.password_hash, data['current_password']):
            return jsonify({'error': 'Current password is incorrect'}), 401
        
        user.password_hash = bcrypt.generate_password_hash(
            data['new_password']
        ).decode('utf-8')
        db.session.commit()
        
        log = AuditLog(
            user_id=int(user_id),
            action='PASSWORD_CHANGED',
            details='User changed password',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500