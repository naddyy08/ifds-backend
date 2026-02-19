# routes/inventory.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    jwt_required, 
    get_jwt_identity,
    get_jwt              # ← ADD THIS
)
from models import db, Inventory, AuditLog
from datetime import datetime

inventory_bp = Blueprint('inventory', __name__)


# ============================================
# GET ALL INVENTORY ITEMS - FIXED
# ============================================
@inventory_bp.route('/', methods=['GET'])
@jwt_required()
def get_all_items():
    try:
        user_id = int(get_jwt_identity())   # ← FIXED
        
        query = Inventory.query
        category = request.args.get('category')
        if category:
            query = query.filter_by(category=category)
        
        active = request.args.get('active', 'true').lower() == 'true'
        query = query.filter_by(is_active=active)
        
        items = query.all()
        
        log = AuditLog(
            user_id=user_id,               # ← FIXED
            action='VIEW_INVENTORY',
            details=f'Viewed {len(items)} inventory items',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'items': [item.to_dict() for item in items],
            'total': len(items)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# GET ITEM BY ID - FIXED
# ============================================
@inventory_bp.route('/<int:item_id>', methods=['GET'])
@jwt_required()
def get_item_by_id(item_id):
    try:
        user_id = int(get_jwt_identity())   # ← FIXED
        
        item = Inventory.query.get(item_id)
        
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        
        log = AuditLog(
            user_id=user_id,               # ← FIXED
            action='VIEW_ITEM',
            details=f'Viewed item: {item.item_name}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'item': item.to_dict()}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# ADD NEW ITEM - FIXED
# ============================================
@inventory_bp.route('/', methods=['POST'])
@jwt_required()
def add_item():
    try:
        user_id = int(get_jwt_identity())   # ← FIXED
        data = request.get_json()
        
        required_fields = ['item_name', 'category', 'quantity', 'unit']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        existing_item = Inventory.query.filter_by(
            item_name=data['item_name'],
            category=data['category']
        ).first()
        
        if existing_item:
            return jsonify({'error': 'Item already exists'}), 409
        
        new_item = Inventory(
            item_name=data['item_name'],
            category=data['category'],
            quantity=float(data['quantity']),
            unit=data['unit'],
            reorder_level=float(data.get('reorder_level', 0)),
            unit_price=float(data.get('unit_price', 0)),
            supplier_name=data.get('supplier_name'),
            created_by=user_id             # ← FIXED
        )
        
        db.session.add(new_item)
        db.session.commit()
        
        log = AuditLog(
            user_id=user_id,               # ← FIXED
            action='ADD_INVENTORY_ITEM',
            details=f'Added: {new_item.item_name}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'message': 'Item added successfully',
            'item': new_item.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# UPDATE ITEM - FIXED
# ============================================
@inventory_bp.route('/<int:item_id>', methods=['PUT'])
@jwt_required()
def update_item(item_id):
    try:
        user_id = int(get_jwt_identity())   # ← FIXED
        data = request.get_json()
        
        item = Inventory.query.get(item_id)
        
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        
        if 'item_name' in data:
            item.item_name = data['item_name']
        if 'category' in data:
            item.category = data['category']
        if 'quantity' in data:
            item.quantity = float(data['quantity'])
        if 'unit' in data:
            item.unit = data['unit']
        if 'reorder_level' in data:
            item.reorder_level = float(data['reorder_level'])
        if 'unit_price' in data:
            item.unit_price = float(data['unit_price'])
        if 'supplier_name' in data:
            item.supplier_name = data['supplier_name']
        if 'is_active' in data:
            item.is_active = data['is_active']
            
        item.updated_at = datetime.utcnow()
        db.session.commit()
        
        log = AuditLog(
            user_id=user_id,               # ← FIXED
            action='UPDATE_INVENTORY_ITEM',
            details=f'Updated: {item.item_name}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'message': 'Item updated successfully',
            'item': item.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# DELETE ITEM - FIXED
# ============================================
@inventory_bp.route('/<int:item_id>', methods=['DELETE'])
@jwt_required()
def delete_item(item_id):
    try:
        user_id = int(get_jwt_identity())   # ← FIXED
        claims = get_jwt()                   # ← GET CLAIMS
        role = claims.get('role')           # ← GET ROLE
        
        # Only admin can delete
        if role != 'admin':
            return jsonify({'error': 'Unauthorized. Only admins can delete items.'}), 403
        
        item = Inventory.query.get(item_id)
        
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        
        item.is_active = False
        item.updated_at = datetime.utcnow()
        db.session.commit()
        
        log = AuditLog(
            user_id=user_id,               # ← FIXED
            action='DELETE_INVENTORY_ITEM',
            details=f'Deleted: {item.item_name}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'message': 'Item deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# SEARCH ITEMS - FIXED
# ============================================
@inventory_bp.route('/search', methods=['GET'])
@jwt_required()
def search_items():
    try:
        user_id = int(get_jwt_identity())   # ← FIXED
        search_query = request.args.get('q', '')
        
        if not search_query:
            return jsonify({'error': 'Search query "q" is required'}), 400
        
        items = Inventory.query.filter(
            Inventory.item_name.ilike(f'%{search_query}%'),
            Inventory.is_active == True
        ).all()
        
        log = AuditLog(
            user_id=user_id,               # ← FIXED
            action='SEARCH_INVENTORY',
            details=f'Searched: {search_query}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'items': [item.to_dict() for item in items],
            'total': len(items),
            'search_query': search_query
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# LOW STOCK ITEMS - FIXED
# ============================================
@inventory_bp.route('/low-stock', methods=['GET'])
@jwt_required()
def get_low_stock():
    try:
        items = Inventory.query.filter(
            Inventory.quantity <= Inventory.reorder_level,
            Inventory.is_active == True
        ).all()
        
        return jsonify({
            'items': [item.to_dict() for item in items],
            'total': len(items)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500