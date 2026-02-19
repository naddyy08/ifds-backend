# routes/transactions.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, Transaction, Inventory, AuditLog
from datetime import datetime
from utils.fraud_engine import analyze_transaction

transactions_bp = Blueprint('transactions', __name__)


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
            details=f'Stock IN: {item.item_name} +{quantity} {item.unit}',
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
# RECORD STOCK OUT (WITH FRAUD DETECTION)
# ============================================
@transactions_bp.route('/stock-out', methods=['POST'])
@jwt_required()
def stock_out():
    """
    Record stock used/removed from inventory
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
            details=f'Stock OUT: {item.item_name} -{quantity} {item.unit}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()

        # ============================================
        # RUN FRAUD DETECTION
        # ============================================
        db.session.refresh(transaction)
        fraud_alerts = analyze_transaction(transaction)

        response_data = {
            'message': 'Stock OUT recorded successfully',
            'transaction': transaction.to_dict(),
            'updated_quantity': new_qty
        }

        # Add fraud warning to response if detected
        if fraud_alerts:
            response_data['fraud_warning'] = {
                'message': f'⚠️ {len(fraud_alerts)} fraud alert(s) detected!',
                'alerts': [alert.to_dict() for alert in fraud_alerts]
            }

        return jsonify(response_data), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# RECORD WASTE/SPOILAGE (WITH FRAUD DETECTION)
# ============================================
@transactions_bp.route('/waste', methods=['POST'])
@jwt_required()
def record_waste():
    """
    Record wasted or spoiled inventory
    Required: inventory_id, quantity, reason
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
        
        # Check if enough stock
        if item.quantity < quantity:
            return jsonify({
                'error': f'Insufficient stock. Available: {item.quantity} {item.unit}'
            }), 400
        
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
            details=f'Waste: {item.item_name} -{quantity} {item.unit}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()

        # ============================================
        # RUN FRAUD DETECTION
        # ============================================
        db.session.refresh(transaction)
        fraud_alerts = analyze_transaction(transaction)

        response_data = {
            'message': 'Waste recorded successfully',
            'transaction': transaction.to_dict(),
            'updated_quantity': new_qty
        }

        # Add fraud warning to response if detected
        if fraud_alerts:
            response_data['fraud_warning'] = {
                'message': f'⚠️ {len(fraud_alerts)} fraud alert(s) detected!',
                'alerts': [alert.to_dict() for alert in fraud_alerts]
            }

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
    Get all transactions
    Optional filters: ?type=stock_in&item_id=1
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
        ).all()
        
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
    Get a specific transaction by ID
    """
    try:
        transaction = Transaction.query.get(transaction_id)
        
        if not transaction:
            return jsonify({'error': 'Transaction not found'}), 404
        
        return jsonify({
            'transaction': transaction.to_dict()
        }), 200
        
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
# GET TRANSACTION SUMMARY
# ============================================
@transactions_bp.route('/summary', methods=['GET'])
@jwt_required()
def get_summary():
    """
    Get transaction summary counts
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
        
        return jsonify({
            'summary': {
                'total_transactions': total,
                'stock_in': stock_in,
                'stock_out': stock_out,
                'waste': waste,
                'flagged': flagged
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500