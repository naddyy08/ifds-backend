# routes/inventory.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, Inventory, AuditLog
from datetime import datetime

inventory_bp = Blueprint('inventory', __name__)


# ============================================
# GET ALL INVENTORY ITEMS
# ============================================
@inventory_bp.route('/', methods=['GET'])
@jwt_required()
def get_all_items():
    try:
        user_id = int(get_jwt_identity())
        
        query = Inventory.query
        category = request.args.get('category')
        if category:
            query = query.filter_by(category=category)
        
        active = request.args.get('active', 'true').lower() == 'true'
        query = query.filter_by(is_active=active)
        
        items = query.all()
        
        log = AuditLog(
            user_id=user_id,
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
# GET ITEM BY ID
# ============================================
@inventory_bp.route('/<int:item_id>', methods=['GET'])
@jwt_required()
def get_item_by_id(item_id):
    try:
        user_id = int(get_jwt_identity())
        
        item = Inventory.query.get(item_id)
        
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        
        log = AuditLog(
            user_id=user_id,
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
# ADD NEW ITEM
# ============================================
@inventory_bp.route('/', methods=['POST'])
@jwt_required()
def add_item():
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        required_fields = ['item_name', 'category', 'quantity', 'unit']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        existing_item = Inventory.query.filter_by(
            item_name=data['item_name'],
            category=data['category'],
            is_active=True
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
            created_by=user_id
        )
        
        db.session.add(new_item)
        db.session.commit()
        
        log = AuditLog(
            user_id=user_id,
            action='ADD_INVENTORY_ITEM',
            details=f'Added: {new_item.item_name} (Qty: {new_item.quantity} {new_item.unit})',
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
# UPDATE ITEM
# ============================================
@inventory_bp.route('/<int:item_id>', methods=['PUT'])
@jwt_required()
def update_item(item_id):
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        item = Inventory.query.get(item_id)
        
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        
        # Store old values for audit log
        old_values = []
        
        if 'item_name' in data and data['item_name'] != item.item_name:
            old_values.append(f"name: {item.item_name} → {data['item_name']}")
            item.item_name = data['item_name']
            
        if 'category' in data and data['category'] != item.category:
            old_values.append(f"category: {item.category} → {data['category']}")
            item.category = data['category']
            
        if 'quantity' in data:
            new_qty = float(data['quantity'])
            if new_qty != item.quantity:
                old_values.append(f"quantity: {item.quantity} → {new_qty}")
                item.quantity = new_qty
                
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
            user_id=user_id,
            action='UPDATE_INVENTORY_ITEM',
            details=f'Updated: {item.item_name}. Changes: {", ".join(old_values) if old_values else "No changes"}',
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
# DELETE ITEM (ADMIN ONLY)
# ============================================
@inventory_bp.route('/<int:item_id>', methods=['DELETE'])
@jwt_required()
def delete_item(item_id):
    try:
        user_id = int(get_jwt_identity())
        claims = get_jwt()
        role = claims.get('role')
        
        # Only admin can delete
        if role != 'admin':
            log = AuditLog(
                user_id=user_id,
                action='UNAUTHORIZED_DELETE_ATTEMPT',
                details=f'User with role "{role}" attempted to delete item ID {item_id}',
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()
            
            return jsonify({
                'error': 'Unauthorized. Only admins can delete inventory items.'
            }), 403
        
        item = Inventory.query.get(item_id)
        
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        
        # Soft delete (set is_active to False instead of actually deleting)
        item.is_active = False
        item.updated_at = datetime.utcnow()
        db.session.commit()
        
        log = AuditLog(
            user_id=user_id,
            action='DELETE_INVENTORY_ITEM',
            details=f'Deleted (soft): {item.item_name} (ID: {item.id})',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'message': 'Item deleted successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# SEARCH ITEMS
# ============================================
@inventory_bp.route('/search', methods=['GET'])
@jwt_required()
def search_items():
    try:
        user_id = int(get_jwt_identity())
        search_query = request.args.get('q', '')
        
        if not search_query:
            return jsonify({'error': 'Search query "q" is required'}), 400
        
        items = Inventory.query.filter(
            Inventory.item_name.ilike(f'%{search_query}%'),
            Inventory.is_active == True
        ).all()
        
        log = AuditLog(
            user_id=user_id,
            action='SEARCH_INVENTORY',
            details=f'Searched: "{search_query}" (Found: {len(items)} items)',
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
# LOW STOCK ITEMS
# ============================================
@inventory_bp.route('/low-stock', methods=['GET'])
@jwt_required()
def get_low_stock():
    try:
        user_id = int(get_jwt_identity())
        
        items = Inventory.query.filter(
            Inventory.quantity <= Inventory.reorder_level,
            Inventory.is_active == True
        ).all()
        
        log = AuditLog(
            user_id=user_id,
            action='VIEW_LOW_STOCK',
            details=f'Viewed low stock items (Found: {len(items)} items)',
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