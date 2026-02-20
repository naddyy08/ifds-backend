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

def create_app():
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(Config)
    
    # Initialize extensions
    db.init_app(app)
    CORS(app)  # Enable CORS for React frontend
    JWTManager(app)
    
    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(inventory_bp, url_prefix='/api/inventory')
    app.register_blueprint(transactions_bp, url_prefix='/api/transactions')
    app.register_blueprint(fraud_bp, url_prefix='/api/fraud')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
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
                'reports': '/api/reports'
            }
        })
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Endpoint not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error'}), 500
    
    @app.errorhandler(401)
    def unauthorized(error):
        return jsonify({'error': 'Unauthorized access'}), 401
    
    @app.errorhandler(403)
    def forbidden(error):
        return jsonify({'error': 'Forbidden - insufficient permissions'}), 403
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)

# Create app instance for Gunicorn (production)
app = create_app()