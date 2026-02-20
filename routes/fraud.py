# routes/fraud.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, FraudAlert, Transaction, AuditLog
from datetime import datetime

fraud_bp = Blueprint('fraud', __name__)


# ============================================
# GET ALL FRAUD ALERTS
# ============================================
@fraud_bp.route('/', methods=['GET'])
@jwt_required()
def get_all_alerts():
    """
    Get all fraud alerts (all roles can view)
    Optional filters: ?status=pending&severity=high
    """
    try:
        user_id = int(get_jwt_identity())
        
        # Get query parameters
        status = request.args.get('status')
        severity = request.args.get('severity')
        
        query = FraudAlert.query
        
        if status:
            query = query.filter_by(status=status)
        if severity:
            query = query.filter_by(severity=severity)
        
        alerts = query.order_by(FraudAlert.detected_at.desc()).all()
        
        # Log action
        log = AuditLog(
            user_id=user_id,
            action='VIEW_FRAUD_ALERTS',
            details=f'Viewed {len(alerts)} fraud alerts',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'alerts': [alert.to_dict() for alert in alerts],
            'total': len(alerts)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# GET ALERT BY ID
# ============================================
@fraud_bp.route('/<int:alert_id>', methods=['GET'])
@jwt_required()
def get_alert_by_id(alert_id):
    """
    Get specific fraud alert details (all roles)
    """
    try:
        alert = FraudAlert.query.get(alert_id)
        
        if not alert:
            return jsonify({'error': 'Alert not found'}), 404
        
        return jsonify({'alert': alert.to_dict()}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# REVIEW FRAUD ALERT (Manager/Admin Only)
# ============================================
@fraud_bp.route('/<int:alert_id>/review', methods=['PUT'])
@jwt_required()
def review_alert(alert_id):
    """
    Review and update fraud alert status
    RBAC: Only managers and admins can review alerts
    Required: {status: 'resolved'/'dismissed', notes: 'review notes'}
    """
    try:
        user_id = int(get_jwt_identity())
        claims = get_jwt()
        role = claims.get('role')
        
        # ✅ RBAC: Only manager and admin can review
        if role not in ['admin', 'manager']:
            log = AuditLog(
                user_id=user_id,
                action='UNAUTHORIZED_ALERT_REVIEW_ATTEMPT',
                details=f'User with role "{role}" attempted to review alert {alert_id}',
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()
            
            return jsonify({
                'error': 'Unauthorized. Only managers and administrators can review fraud alerts.'
            }), 403
        
        data = request.get_json()
        
        # Validate required fields
        if 'status' not in data:
            return jsonify({'error': 'Status is required'}), 400
        
        valid_statuses = ['reviewed', 'resolved', 'dismissed']
        if data['status'] not in valid_statuses:
            return jsonify({
                'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            }), 400
        
        alert = FraudAlert.query.get(alert_id)
        
        if not alert:
            return jsonify({'error': 'Alert not found'}), 404
        
        # Update alert
        old_status = alert.status
        alert.status = data['status']
        alert.reviewed_by = user_id
        alert.reviewed_at = datetime.utcnow()
        alert.notes = data.get('notes', '')
        
        db.session.commit()
        
        # Log the review
        log = AuditLog(
            user_id=user_id,
            action='FRAUD_ALERT_REVIEWED',
            details=f'Alert {alert_id} reviewed: {old_status} → {data["status"]}. Type: {alert.alert_type}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'message': f'Alert marked as {data["status"]}',
            'alert': alert.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# FRAUD STATISTICS
# ============================================
@fraud_bp.route('/statistics', methods=['GET'])
@jwt_required()
def get_fraud_statistics():
    """
    Get fraud alert statistics (all roles)
    """
    try:
        # Count by status
        pending = FraudAlert.query.filter_by(status='pending').count()
        reviewed = FraudAlert.query.filter_by(status='reviewed').count()
        resolved = FraudAlert.query.filter_by(status='resolved').count()
        dismissed = FraudAlert.query.filter_by(status='dismissed').count()
        
        # Count by severity
        high = FraudAlert.query.filter_by(severity='high').count()
        medium = FraudAlert.query.filter_by(severity='medium').count()
        low = FraudAlert.query.filter_by(severity='low').count()
        
        # Count by type
        alert_types = db.session.query(
            FraudAlert.alert_type,
            db.func.count(FraudAlert.id)
        ).group_by(FraudAlert.alert_type).all()
        
        statistics = {
            'by_status': {
                'pending': pending,
                'reviewed': reviewed,
                'resolved': resolved,
                'dismissed': dismissed,
                'total': pending + reviewed + resolved + dismissed
            },
            'by_severity': {
                'high': high,
                'medium': medium,
                'low': low
            },
            'by_type': {
                alert_type: count for alert_type, count in alert_types
            }
        }
        
        return jsonify(statistics), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500