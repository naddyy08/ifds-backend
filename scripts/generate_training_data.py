# backend/scripts/generate_training_data.py
import random
from datetime import datetime, timedelta
import sys
sys.path.append('..')

from app import create_app
from models import db, Transaction, Inventory
from utils.ml_fraud_detector import MLFraudDetector, extract_features

def generate_synthetic_transactions(app):
    """Generate synthetic transaction data for ML training"""
    
    with app.app_context():
        # Get all inventory items
        items = Inventory.query.filter_by(is_active=True).all()
        
        training_data = []
        
        for item in items:
            # Generate 100 normal transactions
            for _ in range(100):
                # Normal transaction: 5-15% of stock
                qty = item.quantity * random.uniform(0.05, 0.15)
                hour = random.randint(8, 18)  # Business hours
                day = random.randint(0, 4)  # Weekdays
                
                features = [
                    qty,
                    item.quantity,
                    qty / item.quantity,
                    hour,
                    day
                ]
                training_data.append(features)
            
            # Generate 10 fraudulent transactions
            for _ in range(10):
                # Fraud: >50% of stock or odd hours
                qty = item.quantity * random.uniform(0.5, 0.9)
                hour = random.choice([2, 3, 23])  # Odd hours
                day = random.randint(0, 6)
                
                features = [
                    qty,
                    item.quantity,
                    qty / item.quantity,
                    hour,
                    day
                ]
                training_data.append(features)
        
        # Train model
        detector = MLFraudDetector()
        detector.train_model(training_data)
        
        print(f"✅ Model trained on {len(training_data)} transactions")
        print(f"✅ Model saved to models/fraud_detector.pkl")

if __name__ == '__main__':
    app = create_app()
    generate_synthetic_transactions(app)