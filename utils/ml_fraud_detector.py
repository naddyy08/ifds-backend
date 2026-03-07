# backend/utils/ml_fraud_detector.py
import numpy as np
from sklearn.ensemble import IsolationForest
import pickle
import os

class MLFraudDetector:
    def __init__(self):
        self.model = None
        self.model_path = 'models/fraud_detector.pkl'
        
    def train_model(self, transaction_data):
        """
        Train Isolation Forest on transaction patterns
        transaction_data: list of [quantity, previous_qty, time_of_day, day_of_week]
        """
        # Isolation Forest - good for anomaly detection
        self.model = IsolationForest(
            contamination=0.1,  # Expect 10% anomalies
            random_state=42,
            n_estimators=100
        )
        
        # Convert to numpy array
        X = np.array(transaction_data)
        
        # Train model
        self.model.fit(X)
        
        # Save model
        os.makedirs('models', exist_ok=True)
        with open(self.model_path, 'wb') as f:
            pickle.dump(self.model, f)
            
        return True
    
    def predict_fraud(self, transaction_features):
        """
        Predict if transaction is fraudulent
        Returns: (is_fraud, anomaly_score)
        """
        if self.model is None:
            self.load_model()
        
        # Convert to numpy array
        X = np.array([transaction_features])
        
        # Predict (-1 = anomaly, 1 = normal)
        prediction = self.model.predict(X)
        
        # Get anomaly score
        score = self.model.score_samples(X)[0]
        
        is_fraud = prediction[0] == -1
        
        return is_fraud, abs(score)
    
    def load_model(self):
        """Load trained model from disk"""
        if os.path.exists(self.model_path):
            with open(self.model_path, 'rb') as f:
                self.model = pickle.load(f)
            return True
        return False

# Helper function to extract features from transaction
def extract_features(transaction, inventory_item):
    """
    Extract features for ML model
    """
    from datetime import datetime
    
    now = datetime.utcnow()
    
    features = [
        float(transaction.get('quantity', 0)),
        float(inventory_item.quantity),  # Previous quantity
        float(transaction.get('quantity', 0)) / float(inventory_item.quantity) if inventory_item.quantity > 0 else 0,  # Percentage
        now.hour,  # Time of day
        now.weekday(),  # Day of week
    ]
    
    return features