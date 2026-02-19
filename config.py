# config.py
import os
from datetime import timedelta

class Config:
    # Database - Use PostgreSQL in production, SQLite/MySQL in development
    DATABASE_URI = os.getenv('DATABASE_URL')
    
    # Render uses postgres:// but SQLAlchemy needs postgresql://
    if DATABASE_URI and DATABASE_URI.startswith("postgres://"):
        DATABASE_URI = DATABASE_URI.replace("postgres://", "postgresql://", 1)
    
    # Fallback to local database if no DATABASE_URL
    if not DATABASE_URI:
        DATABASE_URI = os.getenv('DATABASE_URI', 'mysql+pymysql://root@localhost/inventory_fraud_detection')
    
    SQLALCHEMY_DATABASE_URI = DATABASE_URI
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # JWT
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-this')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)