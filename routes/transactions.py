# routes/transactions.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, Transaction, Inventory, AuditLog
from datetime import datetime
from utils.fraud_engine import analyze_transaction

transactions_bp = Blueprint('transactions', __name__)


# ============================================
# HELPER FUNCTIONS
# ============================================
def extract_ml_features(transaction_data, inventory_item):
    """
    Extract features for ML fraud detection
    Returns: [quantity, previous_qty, percentage, hour, day_of_week]
    """
    now = datetime.utcnow()
    quantity = float(transaction_data.get('quantity', 0))
    prev_qty = float(inventory_item.quantity)
    
    # Calculate percentage of stock being removed
    percentage = (quantity / prev_qty * 100) if prev_qty > 0 else 0
    
    features = [
        quantity,           # Raw quantity
        prev_qty,          # Current stock level
        percentage,        # Percentage of stock
        now.hour,          # Hour of day (0-23)
        now.weekday(),     # Day of week (0-6)
    ]
    
    return features


# ============================================
# RECORD STOCK IN
# ============================================
@transactions_bp.route('/stock-in', methods=['POST'])
@jwt_required()
def stock_in():
    """
    Record new stock received from supplier
    Required: inventory_id, quantity
    Optional: reason, reference_no
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        # Validate required fields
        if not data.get('inventory_id') or not data.get('quantity'):
            return jsonify({'error': 'inventory_id and quantity are required'}), 400
        
        # Get inventory item
        item = Inventory.query.get(data['inventory_id'])
        if not item:
            return jsonify({'error': 'Inventory item not found'}), 404
        
        if not item.is_active:
            return jsonify({'error': 'Item is not active'}), 400
        
        quantity = float(data['quantity'])
        if quantity <= 0:
            return jsonify({'error': 'Quantity must be greater than 0'}), 400
        
        # Record previous and new quantity
        previous_qty = item.quantity
        new_qty = previous_qty + quantity
        
        # Update inventory
        item.quantity = new_qty
        item.last_restocked = datetime.utcnow()
        
        # Create transaction record
        transaction = Transaction(
            inventory_id=item.id,
            user_id=user_id,
            transaction_type='stock_in',
            quantity=quantity,
            previous_quantity=previous_qty,
            new_quantity=new_qty,
            reason=data.get('reason', 'Stock received from supplier'),
            reference_no=data.get('reference_no')
        )
        
        db.session.add(transaction)
        
        # Audit log
        log = AuditLog(
            user_id=user_id,
            action='STOCK_IN',
            details=f'Stock IN: {item.item_name} +{quantity} {item.unit} (New stock: {new_qty})',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'message': 'Stock IN recorded successfully',
            'transaction': transaction.to_dict(),
            'updated_quantity': new_qty
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# RECORD STOCK OUT (WITH AI FRAUD DETECTION)
# ============================================
@transactions_bp.route('/stock-out', methods=['POST'])
@jwt_required()
def stock_out():
    """
    Record stock used/removed from inventory
    Includes AI-powered fraud detection
    Required: inventory_id, quantity
    Optional: reason, reference_no
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        # Validate required fields
        if not data.get('inventory_id') or not data.get('quantity'):
            return jsonify({'error': 'inventory_id and quantity are required'}), 400
        
        item = Inventory.query.get(data['inventory_id'])
        if not item:
            return jsonify({'error': 'Inventory item not found'}), 404
        
        quantity = float(data['quantity'])
        if quantity <= 0:
            return jsonify({'error': 'Quantity must be greater than 0'}), 400
        
        # Check if enough stock available
        if item.quantity < quantity:
            return jsonify({
                'error': f'Insufficient stock. Available: {item.quantity} {item.unit}'
            }), 400
        
        # Extract features for ML detection (BEFORE updating inventory)
        ml_features = extract_ml_features(data, item)
        
        # Record previous and new quantity
        previous_qty = item.quantity
        new_qty = previous_qty - quantity
        
        # Update inventory
        item.quantity = new_qty
        
        # Create transaction record
        transaction = Transaction(
            inventory_id=item.id,
            user_id=user_id,
            transaction_type='stock_out',
            quantity=quantity,
            previous_quantity=previous_qty,
            new_quantity=new_qty,
            reason=data.get('reason', 'Stock used in operations'),
            reference_no=data.get('reference_no')
        )
        
        db.session.add(transaction)
        
        # Audit log
        log = AuditLog(
            user_id=user_id,
            action='STOCK_OUT',
            details=f'Stock OUT: {item.item_name} -{quantity} {item.unit} (Remaining: {new_qty})',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()

        # ============================================
        # AI FRAUD DETECTION ENGINE
        # ============================================
        db.session.refresh(transaction)
        
        # Run rule-based fraud detection
        fraud_alerts = analyze_transaction(transaction)
        
        # Optional: Run ML-based detection
        ml_risk_score = 0
        ml_detected = False
        
        try:
            # Calculate ML risk score based on features
            # Feature analysis for suspicious patterns
            percentage = ml_features[2]  # Percentage of stock removed
            hour = ml_features[3]        # Hour of day
            
            # Simple ML-like scoring (you can replace with actual sklearn model)
            risk_factors = []
            
            # High percentage removal
            if percentage > 50:
                ml_risk_score += 40
                risk_factors.append(f"High removal rate: {percentage:.1f}%")
            elif percentage > 30:
                ml_risk_score += 20
                risk_factors.append(f"Moderate removal rate: {percentage:.1f}%")
            
            # Unusual hours (outside business hours)
            if hour < 6 or hour > 22:
                ml_risk_score += 30
                risk_factors.append(f"Off-hours transaction: {hour}:00")
            
            # Large absolute quantity
            if quantity > 100:
                ml_risk_score += 15
                risk_factors.append(f"Large quantity: {quantity}")
            
            # If ML risk score is high, mark as detected
            if ml_risk_score >= 50:
                ml_detected = True
                
                # Log ML detection
                ml_log = AuditLog(
                    user_id=user_id,
                    action='ML_FRAUD_DETECTED',
                    details=f'ML Risk Score: {ml_risk_score}/100. Factors: {", ".join(risk_factors)}',
                    ip_address=request.remote_addr
                )
                db.session.add(ml_log)
                db.session.commit()
                
        except Exception as ml_error:
            print(f"ML detection error: {ml_error}")

        # Build response
        response_data = {
            'message': 'Stock OUT recorded successfully',
            'transaction': transaction.to_dict(),
            'updated_quantity': new_qty,
            'ai_analysis': {
                'ml_risk_score': ml_risk_score,
                'risk_level': 'high' if ml_risk_score >= 70 else 'medium' if ml_risk_score >= 40 else 'low',
                'ml_detected': ml_detected
            }
        }

        # Add fraud warning to response if detected
        if fraud_alerts or ml_detected:
            total_alerts = len(fraud_alerts) + (1 if ml_detected else 0)
            response_data['fraud_warning'] = {
                'message': f'⚠️ {total_alerts} fraud alert(s) detected!',
                'rule_based_alerts': [alert.to_dict() for alert in fraud_alerts],
                'ml_detection': {
                    'detected': ml_detected,
                    'risk_score': ml_risk_score,
                    'severity': 'high' if ml_risk_score >= 70 else 'medium'
                } if ml_detected else None
            }
            
            # Mark transaction as flagged if fraud detected
            transaction.is_flagged = True
            db.session.commit()

        return jsonify(response_data), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# RECORD WASTE/SPOILAGE (WITH AI FRAUD DETECTION)
# ============================================
@transactions_bp.route('/waste', methods=['POST'])
@jwt_required()
def record_waste():
    """
    Record wasted or spoiled inventory
    Includes AI fraud detection for excessive waste claims
    Required: inventory_id, quantity, reason
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        # Validate required fields
        if not data.get('inventory_id') or not data.get('quantity'):
            return jsonify({'error': 'inventory_id and quantity are required'}), 400
        
        if not data.get('reason'):
            return jsonify({'error': 'Reason is required for waste transactions'}), 400
        
        item = Inventory.query.get(data['inventory_id'])
        if not item:
            return jsonify({'error': 'Inventory item not found'}), 404
        
        quantity = float(data['quantity'])
        if quantity <= 0:
            return jsonify({'error': 'Quantity must be greater than 0'}), 400
        
        # Check if enough stock
        if item.quantity < quantity:
            return jsonify({
                'error': f'Insufficient stock. Available: {item.quantity} {item.unit}'
            }), 400
        
        # Extract ML features
        ml_features = extract_ml_features(data, item)
        
        # Record previous and new quantity
        previous_qty = item.quantity
        new_qty = previous_qty - quantity
        
        # Update inventory
        item.quantity = new_qty
        
        # Create transaction record
        transaction = Transaction(
            inventory_id=item.id,
            user_id=user_id,
            transaction_type='waste',
            quantity=quantity,
            previous_quantity=previous_qty,
            new_quantity=new_qty,
            reason=data.get('reason', 'Spoilage/Waste'),
            reference_no=data.get('reference_no')
        )
        
        db.session.add(transaction)
        
        # Audit log
        log = AuditLog(
            user_id=user_id,
            action='WASTE_RECORDED',
            details=f'Waste: {item.item_name} -{quantity} {item.unit}. Reason: {data.get("reason")}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()

        # ============================================
        # AI FRAUD DETECTION FOR WASTE
        # ============================================
        db.session.refresh(transaction)
        
        # Run rule-based fraud detection
        fraud_alerts = analyze_transaction(transaction)
        
        # ML analysis for waste patterns
        ml_risk_score = 0
        percentage = ml_features[2]
        
        # Waste-specific risk scoring
        if percentage > 30:  # Wasting >30% of stock is highly suspicious
            ml_risk_score += 50
        if percentage > 50:  # Wasting >50% is critical
            ml_risk_score += 40
            
        ml_detected = ml_risk_score >= 50

        response_data = {
            'message': 'Waste recorded successfully',
            'transaction': transaction.to_dict(),
            'updated_quantity': new_qty,
            'ai_analysis': {
                'ml_risk_score': ml_risk_score,
                'risk_level': 'high' if ml_risk_score >= 70 else 'medium' if ml_risk_score >= 40 else 'low'
            }
        }

        # Add fraud warning if detected
        if fraud_alerts or ml_detected:
            total_alerts = len(fraud_alerts) + (1 if ml_detected else 0)
            response_data['fraud_warning'] = {
                'message': f'⚠️ {total_alerts} fraud alert(s) detected on waste transaction!',
                'rule_based_alerts': [alert.to_dict() for alert in fraud_alerts],
                'ml_detection': {
                    'detected': ml_detected,
                    'risk_score': ml_risk_score,
                    'note': 'Excessive waste claim detected'
                } if ml_detected else None
            }
            
            transaction.is_flagged = True
            db.session.commit()

        return jsonify(response_data), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# GET ALL TRANSACTIONS
# ============================================
@transactions_bp.route('/', methods=['GET'])
@jwt_required()
def get_all_transactions():
    """
    Get all transactions with optional filters
    Optional filters: ?type=stock_in&item_id=1&flagged=true
    """
    try:
        user_id = int(get_jwt_identity())
        
        query = Transaction.query
        
        # Filter by type
        transaction_type = request.args.get('type')
        if transaction_type:
            query = query.filter_by(transaction_type=transaction_type)
        
        # Filter by item
        item_id = request.args.get('item_id')
        if item_id:
            query = query.filter_by(inventory_id=int(item_id))
        
        # Filter by flagged
        flagged = request.args.get('flagged')
        if flagged:
            query = query.filter_by(is_flagged=flagged.lower() == 'true')
        
        # Order by latest first
        transactions = query.order_by(
            Transaction.timestamp.desc()
        ).limit(100).all()  # Limit to last 100 for performance
        
        return jsonify({
            'transactions': [t.to_dict() for t in transactions],
            'total': len(transactions)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# GET TRANSACTION BY ID
# ============================================
@transactions_bp.route('/<int:transaction_id>', methods=['GET'])
@jwt_required()
def get_transaction_by_id(transaction_id):
    """
    Get a specific transaction by ID with fraud analysis
    """
    try:
        transaction = Transaction.query.get(transaction_id)
        
        if not transaction:
            return jsonify({'error': 'Transaction not found'}), 404
        
        # Include fraud alerts if any
        fraud_alerts = transaction.fraud_alerts
        
        response = {
            'transaction': transaction.to_dict(),
            'fraud_alerts': [alert.to_dict() for alert in fraud_alerts] if fraud_alerts else [],
            'fraud_alert_count': len(fraud_alerts)
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# GET TRANSACTIONS BY ITEM
# ============================================
@transactions_bp.route('/item/<int:item_id>', methods=['GET'])
@jwt_required()
def get_transactions_by_item(item_id):
    """
    Get all transactions for a specific inventory item
    """
    try:
        item = Inventory.query.get(item_id)
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        
        transactions = Transaction.query.filter_by(
            inventory_id=item_id
        ).order_by(
            Transaction.timestamp.desc()
        ).all()
        
        return jsonify({
            'item_name': item.item_name,
            'current_quantity': item.quantity,
            'unit': item.unit,
            'transactions': [t.to_dict() for t in transactions],
            'total': len(transactions)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# GET TRANSACTION SUMMARY WITH AI STATS
# ============================================
@transactions_bp.route('/summary', methods=['GET'])
@jwt_required()
def get_summary():
    """
    Get transaction summary counts including AI detection stats
    """
    try:
        total = Transaction.query.count()
        stock_in = Transaction.query.filter_by(
            transaction_type='stock_in'
        ).count()
        stock_out = Transaction.query.filter_by(
            transaction_type='stock_out'
        ).count()
        waste = Transaction.query.filter_by(
            transaction_type='waste'
        ).count()
        flagged = Transaction.query.filter_by(
            is_flagged=True
        ).count()
        
        # Calculate fraud detection rate
        fraud_rate = (flagged / total * 100) if total > 0 else 0
        
        return jsonify({
            'summary': {
                'total_transactions': total,
                'stock_in': stock_in,
                'stock_out': stock_out,
                'waste': waste,
                'flagged_transactions': flagged,
                'fraud_detection_rate': round(fraud_rate, 2),
                'ai_protection': 'active'
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500