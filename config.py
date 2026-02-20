# config.py
import os
from datetime import timedelta

class Config:
    # Database configuration
    # Priority: DATABASE_URL (Render) > DATABASE_URI (.env) > SQLite (fallback)
    
    # First, check for Render's DATABASE_URL (production)
    DATABASE_URI = os.getenv('DATABASE_URL')
    
    # Render uses postgres:// but SQLAlchemy needs postgresql://
    if DATABASE_URI and DATABASE_URI.startswith("postgres://"):
        DATABASE_URI = DATABASE_URI.replace("postgres://", "postgresql://", 1)
    
    # If no DATABASE_URL, check for DATABASE_URI from .env
    if not DATABASE_URI:
        DATABASE_URI = os.getenv('DATABASE_URI')
    
    # Final fallback to SQLite if nothing is set
    if not DATABASE_URI:
        DATABASE_URI = 'sqlite:///ifds.db'
    
    SQLALCHEMY_DATABASE_URI = DATABASE_URI
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # JWT Configuration
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-this')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)