from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt
import os, json
from datetime import datetime

settings_bp = Blueprint('settings', __name__)

SETTINGS_FILE = 'instance/system_settings.json'
BACKUP_FILE = 'instance/db_backup.sql'

# Ensure settings file exists
def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        default = {
            'fraud_thresholds': {
                'waste_percent': 30,
                'high_risk_score': 70
            },
            'notification': {
                'email_enabled': True,
                'sms_enabled': False
            }
        }
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(default, f)
    with open(SETTINGS_FILE) as f:
        return json.load(f)

def save_settings(data):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(data, f)

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
        print("[ERROR] Failed to load settings:", e)
        traceback.print_exc()
        return jsonify({'error': 'Failed to load settings', 'details': str(e)}), 500

# Update settings (admin only)
@settings_bp.route('/', methods=['PUT'])
@jwt_required()
def update_settings():
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    data = request.get_json()
    save_settings(data)
    return jsonify({'message': 'Settings updated'})

# Export DB backup (admin only)
@settings_bp.route('/backup', methods=['GET'])
@jwt_required()
def export_backup():
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    # Example: Use SQLite for demo, adjust for your DB
    from models import db
    db_uri = db.engine.url.database
    backup_path = BACKUP_FILE
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    # SQLite: copy file, MySQL/Postgres: use dump util
    if os.path.exists(db_uri):
        import shutil
        shutil.copy(db_uri, backup_path)
        return send_file(backup_path, as_attachment=True)
    else:
        return jsonify({'error': 'Backup not supported for this DB'}), 400
