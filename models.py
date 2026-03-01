# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    __table_args__ = (
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'},
    )
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, manager, staff
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    def to_dict(self):
        """Convert user object to dictionary (exclude password)"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'is_active': self.is_active
        }


class AuditLog(db.Model):
    """
    Tamper-proof audit log model
    CRITICAL: user_id is nullable to log system events and failed login attempts
    No UPDATE or DELETE routes exist for this model
    """
    __tablename__ = 'audit_logs'
    __table_args__ = (
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'},
    )
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, 
        db.ForeignKey('users.id'), 
        nullable=True,  # ← CHANGED: Must be nullable for failed logins and system events
        index=True
    )
    action = db.Column(db.String(100), nullable=False, index=True)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    timestamp = db.Column(
        db.DateTime, 
        default=datetime.utcnow, 
        nullable=False,
        index=True  # Index for faster date-based queries
    )
    
    # Relationship (nullable because user_id can be null)
    user = db.relationship('User', backref='audit_logs')
    
    def __repr__(self):
        return f'<AuditLog {self.action} by User {self.user_id}>'
    
    def to_dict(self):
        """Convert audit log to dictionary for JSON response"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else 'System',  # ← Handle null user_id
            'action': self.action,
            'details': self.details,
            'ip_address': self.ip_address,
            'timestamp': self.timestamp.isoformat()  # ← Better format for frontend
        }


class Inventory(db.Model):
    __tablename__ = 'inventory'
    
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=0)
    unit = db.Column(db.String(20), nullable=False)  # kg, pcs, liters, etc.
    reorder_level = db.Column(db.Float, default=0)  # Alert when stock is low
    unit_price = db.Column(db.Float, default=0.0)
    supplier_name = db.Column(db.String(100))
    last_restocked = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationship
    creator = db.relationship('User', backref='inventory_items')
    
    def __repr__(self):
        return f'<Inventory {self.item_name}>'
    
    def to_dict(self):
        """Convert inventory object to dictionary"""
        return {
            'id': self.id,
            'item_name': self.item_name,
            'category': self.category,
            'quantity': self.quantity,
            'unit': self.unit,
            'reorder_level': self.reorder_level,
            'unit_price': self.unit_price,
            'supplier_name': self.supplier_name,
            'last_restocked': self.last_restocked.strftime('%Y-%m-%d %H:%M:%S') if self.last_restocked else None,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'created_by': self.created_by,
            'is_active': self.is_active
        }
    

class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    inventory_id = db.Column(db.Integer, db.ForeignKey('inventory.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # stock_in, stock_out, waste, adjustment
    quantity = db.Column(db.Float, nullable=False)
    previous_quantity = db.Column(db.Float, nullable=False)  # Stock before transaction
    new_quantity = db.Column(db.Float, nullable=False)       # Stock after transaction
    reason = db.Column(db.String(255))                       # Why this transaction happened
    reference_no = db.Column(db.String(50))                  # Invoice/reference number
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_flagged = db.Column(db.Boolean, default=False)        # Flagged for fraud review
    
    # Relationships
    inventory_item = db.relationship('Inventory', backref='transactions')
    user = db.relationship('User', backref='transactions')
    
    def __repr__(self):
        return f'<Transaction {self.transaction_type} - {self.quantity}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'inventory_id': self.inventory_id,
            'item_name': self.inventory_item.item_name if self.inventory_item else None,
            'user_id': self.user_id,
            'username': self.user.username if self.user else None,
            'transaction_type': self.transaction_type,
            'quantity': self.quantity,
            'previous_quantity': self.previous_quantity,
            'new_quantity': self.new_quantity,
            'reason': self.reason,
            'reference_no': self.reference_no,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'is_flagged': self.is_flagged
        }
    

class FraudAlert(db.Model):
    __tablename__ = 'fraud_alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(
        db.Integer, 
        db.ForeignKey('transactions.id'), 
        nullable=False
    )
    alert_type = db.Column(db.String(100), nullable=False)
    severity = db.Column(db.String(20), nullable=False)  # low, medium, high
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, reviewed, resolved, dismissed
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    
    # Relationships
    transaction = db.relationship('Transaction', backref='fraud_alerts')
    reviewer = db.relationship('User', backref='reviewed_alerts')
    
    def __repr__(self):
        return f'<FraudAlert {self.alert_type} - {self.severity}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'transaction_id': self.transaction_id,
            'alert_type': self.alert_type,
            'severity': self.severity,
            'description': self.description,
            'status': self.status,
            'detected_at': self.detected_at.strftime('%Y-%m-%d %H:%M:%S'),
            'reviewed_by': self.reviewed_by,
            'reviewed_at': self.reviewed_at.strftime('%Y-%m-%d %H:%M:%S') if self.reviewed_at else None,
            'notes': self.notes,
            'transaction': self.transaction.to_dict() if self.transaction else None
        }