# routes/audit.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, AuditLog, User

audit_bp = Blueprint('audit', __name__)


@audit_bp.route('/', methods=['GET'])
@jwt_required()
def get_audit_logs():
    """
    Get all audit logs (Admin only)
    """
    try:
        user_id = int(get_jwt_identity())
        claims = get_jwt()
        role = claims.get('role')
        
        # RBAC: Only admins can view audit logs
        if role != 'admin':
            return jsonify({
                'error': 'Unauthorized. Only administrators can view audit logs.'
            }), 403
        
        # Get query parameters
        limit = min(int(request.args.get('limit', 100)), 1000)
        offset = int(request.args.get('offset', 0))
        
        # Get logs
        logs = AuditLog.query.order_by(
            AuditLog.timestamp.desc()
        ).limit(limit).offset(offset).all()
        
        total = AuditLog.query.count()
        
        return jsonify({
            'logs': [log.to_dict() for log in logs],
            'total': total,
            'limit': limit,
            'offset': offset
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@audit_bp.route('/<int:log_id>', methods=['GET'])
@jwt_required()
def get_audit_log(log_id):
    """
    Get specific audit log by ID (Admin only)
    """
    try:
        user_id = int(get_jwt_identity())
        claims = get_jwt()
        role = claims.get('role')
        
        if role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        log = AuditLog.query.get(log_id)
        
        if not log:
            return jsonify({'error': 'Log not found'}), 404
        
        return jsonify({'log': log.to_dict()}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@audit_bp.route('/statistics', methods=['GET'])
@jwt_required()
def get_statistics():
    """
    Get audit log statistics (Admin only)
    """
    try:
        user_id = int(get_jwt_identity())
        claims = get_jwt()
        role = claims.get('role')
        
        if role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        total = AuditLog.query.count()
        
        # Count by action
        failed_logins = AuditLog.query.filter_by(
            action='FAILED_LOGIN_ATTEMPT'
        ).count()
        
        unauthorized = AuditLog.query.filter(
            AuditLog.action.like('UNAUTHORIZED%')
        ).count()
        
        return jsonify({
            'statistics': {
                'total_logs': total,
                'failed_logins': failed_logins,
                'unauthorized_attempts': unauthorized
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500