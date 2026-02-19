# routes/fraud.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, FraudAlert, Transaction, AuditLog
from utils.fraud_engine import get_fraud_statistics, analyze_transaction
from datetime import datetime

fraud_bp = Blueprint('fraud', __name__)


# ============================================
# GET ALL FRAUD ALERTS
# ============================================
@fraud_bp.route('/', methods=['GET'])
@jwt_required()
def get_all_alerts():
    """
    Get all fraud alerts
    Optional filters: ?severity=high&status=pending
    """
    try:
        query = FraudAlert.query
        
        # Filter by severity
        severity = request.args.get('severity')
        if severity:
            query = query.filter_by(severity=severity)
        
        # Filter by status
        status = request.args.get('status')
        if status:
            query = query.filter_by(status=status)
        
        # Filter by alert type
        alert_type = request.args.get('type')
        if alert_type:
            query = query.filter_by(alert_type=alert_type)
        
        # Order by latest first
        alerts = query.order_by(
            FraudAlert.detected_at.desc()
        ).all()
        
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
    Get specific fraud alert by ID
    """
    try:
        alert = FraudAlert.query.get(alert_id)
        
        if not alert:
            return jsonify({'error': 'Alert not found'}), 404
        
        return jsonify({
            'alert': alert.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# REVIEW ALERT (Mark as Reviewed)
# ============================================
@fraud_bp.route('/<int:alert_id>/review', methods=['PUT'])
@jwt_required()
def review_alert(alert_id):
    """
    Mark alert as reviewed
    Required: status (resolved/dismissed)
    Optional: notes
    """
    try:
        user_id = int(get_jwt_identity())
        claims = get_jwt()
        role = claims.get('role')
        
        # Only admin and manager can review
        if role not in ['admin', 'manager']:
            return jsonify({
                'error': 'Unauthorized. Only admin and manager can review alerts.'
            }), 403
        
        alert = FraudAlert.query.get(alert_id)
        
        if not alert:
            return jsonify({'error': 'Alert not found'}), 404
        
        data = request.get_json()
        
        # Validate status
        valid_statuses = ['reviewed', 'resolved', 'dismissed']
        if data.get('status') not in valid_statuses:
            return jsonify({
                'error': f'Invalid status. Must be: {", ".join(valid_statuses)}'
            }), 400
        
        # Update alert
        alert.status = data['status']
        alert.reviewed_by = user_id
        alert.reviewed_at = datetime.utcnow()
        alert.notes = data.get('notes', '')
        
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            user_id=user_id,
            action='REVIEW_FRAUD_ALERT',
            details=f'Alert #{alert_id} marked as {data["status"]}',
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
# GET FRAUD STATISTICS
# ============================================
@fraud_bp.route('/statistics', methods=['GET'])
@jwt_required()
def get_statistics():
    """
    Get fraud detection statistics
    """
    try:
        stats = get_fraud_statistics()
        
        return jsonify({
            'statistics': stats
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# RUN MANUAL FRAUD CHECK
# ============================================
@fraud_bp.route('/check/<int:transaction_id>', methods=['POST'])
@jwt_required()
def manual_fraud_check(transaction_id):
    """
    Manually run fraud check on a specific transaction
    """
    try:
        user_id = int(get_jwt_identity())
        claims = get_jwt()
        role = claims.get('role')
        
        # Only admin and manager
        if role not in ['admin', 'manager']:
            return jsonify({
                'error': 'Unauthorized.'
            }), 403
        
        transaction = Transaction.query.get(transaction_id)
        
        if not transaction:
            return jsonify({'error': 'Transaction not found'}), 404
        
        # Run fraud analysis
        alerts = analyze_transaction(transaction)
        
        if alerts:
            return jsonify({
                'message': f'⚠️ {len(alerts)} fraud alert(s) detected!',
                'alerts': [alert.to_dict() for alert in alerts]
            }), 200
        else:
            return jsonify({
                'message': '✅ No fraud detected for this transaction',
                'alerts': []
            }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# GET PENDING ALERTS COUNT
# ============================================
@fraud_bp.route('/pending-count', methods=['GET'])
@jwt_required()
def get_pending_count():
    """
    Get count of pending alerts
    Useful for dashboard notifications
    """
    try:
        count = FraudAlert.query.filter_by(status='pending').count()
        high_count = FraudAlert.query.filter_by(
            status='pending',
            severity='high'
        ).count()
        
        return jsonify({
            'pending_alerts': count,
            'high_severity_pending': high_count
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500