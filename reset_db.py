#!/usr/bin/env python
"""
Drop and recreate database tables with correct encoding and storage engine
"""
from flask import Flask
from config import Config
from models import db, User, AuditLog
from routes.auth import auth_bp
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from sqlalchemy import text, inspect

if __name__ == '__main__':
    app = Flask(__name__)
    app.config.from_object(Config)
    
    db.init_app(app)
    CORS(app)
    JWTManager(app)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    
    with app.app_context():
        try:
            print("[*] Disabling foreign key checks...")
            db.session.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            db.session.commit()
            
            # Get all table names
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            print(f"Found tables: {tables}")
            
            # Drop each table
            for table in tables:
                print(f"[*] Dropping table {table}...")
                db.session.execute(text(f"DROP TABLE IF EXISTS {table}"))
                db.session.commit()
            
            print("[OK] All tables dropped!")
            
            print("[*] Creating all tables with correct charset...")
            db.create_all()
            print("[OK] Database tables created with InnoDB and utf8mb4!")
            
            print("[OK] Enabling foreign key checks...")
            db.session.execute(text("SET FOREIGN_KEY_CHECKS=1"))
            db.session.commit()
            print("[OK] Done! All tables recreated successfully.")
        except Exception as e:
            print(f"[ERROR] Error: {e}")
            db.session.rollback()
            raise
