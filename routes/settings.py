# routes/settings.py
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt
import os, json, io
from datetime import datetime

settings_bp = Blueprint('settings', __name__)

SETTINGS_FILE = 'instance/system_settings.json'

DEFAULT_SETTINGS = {
    'fraud_thresholds': {
        'waste_percent': 30,
        'high_risk_score': 70
    },
    'notification': {
        'email_enabled': True,
        'sms_enabled': False
    }
}

def load_settings():
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(DEFAULT_SETTINGS, f, indent=2)
    with open(SETTINGS_FILE) as f:
        return json.load(f)

def save_settings(data):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


# Get settings (admin only)
@settings_bp.route('/', methods=['GET'])
@jwt_required()
def get_settings():
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    try:
        settings = load_settings()
        return jsonify(settings)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to load settings', 'details': str(e)}), 500


# Update settings (admin only)
@settings_bp.route('/', methods=['PUT'])
@jwt_required()
def update_settings():
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    try:
        data = request.get_json()
        save_settings(data)
        return jsonify({'message': 'Settings updated'})
    except Exception as e:
        return jsonify({'error': 'Failed to save settings', 'details': str(e)}), 500


# Export full database backup as JSON (admin only)
@settings_bp.route('/backup', methods=['GET'])
@jwt_required()
def export_backup():
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Admin only'}), 403

    try:
        from models import User, Inventory, Transaction, FraudAlert, AuditLog

        backup_data = {
            'exported_at': datetime.utcnow().isoformat(),
            'database': 'ifds_db',
            'tables': {
                'users': [u.to_dict() for u in User.query.all()],
                'inventory': [i.to_dict() for i in Inventory.query.all()],
                'transactions': [t.to_dict() for t in Transaction.query.all()],
                'fraud_alerts': [f.to_dict() for f in FraudAlert.query.all()],
                'audit_logs': [a.to_dict() for a in AuditLog.query.all()],
            },
            'summary': {
                'total_users': User.query.count(),
                'total_inventory': Inventory.query.count(),
                'total_transactions': Transaction.query.count(),
                'total_fraud_alerts': FraudAlert.query.count(),
                'total_audit_logs': AuditLog.query.count(),
            }
        }

        # Convert to JSON bytes and send as downloadable file
        json_bytes = json.dumps(backup_data, indent=2, default=str).encode('utf-8')
        buffer = io.BytesIO(json_bytes)
        buffer.seek(0)

        filename = f"ifds_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

        return send_file(
            buffer,
            mimetype='application/json',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Backup failed', 'details': str(e)}), 500