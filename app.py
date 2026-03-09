# app.py
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import Config
from models import db
from routes.auth import auth_bp
from routes.inventory import inventory_bp
from routes.transactions import transactions_bp
from routes.fraud import fraud_bp
from routes.reports import reports_bp
from routes.audit import audit_bp
import os

def create_app():
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(Config)
    
    # Initialize extensions
    db.init_app(app)
    
    # ✅ CRITICAL: CORS Configuration - MUST be before JWTManager
    # Allow all origins for FYP/development environment
    CORS(app, 
         resources={r"/api/*": {"origins": "*"}},
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
         expose_headers=["Content-Type", "Authorization"],
         supports_credentials=False,
         send_wildcard=True,
         always_send=True)
    
    # Initialize JWT AFTER CORS
    JWTManager(app)
    
    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(inventory_bp, url_prefix='/api/inventory')
    app.register_blueprint(transactions_bp, url_prefix='/api/transactions')
    app.register_blueprint(fraud_bp, url_prefix='/api/fraud')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    app.register_blueprint(audit_bp, url_prefix='/api/audit')
    
    # Register users blueprint for admin RBAC (if exists)
    try:
        from routes.users import users_bp
        app.register_blueprint(users_bp, url_prefix='/api/users')
    except ImportError:
        print("[WARNING] Users blueprint not found - skipping")
    
    # Register settings blueprint (if exists)
    try:
        from routes.settings import settings_bp
        app.register_blueprint(settings_bp, url_prefix='/api/settings')
    except ImportError:
        print("[WARNING] Settings blueprint not found - skipping")
    
    # Create database tables
    with app.app_context():
        db.create_all()
        print("[OK] Database tables created!")
    
    # Root endpoint
    @app.route('/')
    def index():
        return jsonify({
            'message': 'Welcome to IFDS API',
            'version': '1.0',
            'endpoints': {
                'auth': '/api/auth',
                'inventory': '/api/inventory',
                'transactions': '/api/transactions',
                'fraud': '/api/fraud',
                'reports': '/api/reports',
                'audit': '/api/audit',
                'users': '/api/users',
                'settings': '/api/settings'
            }
        })
    
    # CORS-specific route for preflight
    @app.after_request
    def after_request(response):
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Endpoint not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error'}), 500
    
    return app

if __name__ == '__main__':
    app = create_app()
    print("[RUNNING] IFDS Backend Server Running...")
    print("[SERVER] http://localhost:5000")
    app.run(debug=True, port=5000)

# Create app instance for Gunicorn (production)
app = create_app()