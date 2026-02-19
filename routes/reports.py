# routes/reports.py
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, Inventory, Transaction, FraudAlert, User, AuditLog
from datetime import datetime, timedelta
from sqlalchemy import func
import io

reports_bp = Blueprint('reports', __name__)


# ============================================
# DAILY INVENTORY REPORT
# ============================================
@reports_bp.route('/daily-inventory', methods=['GET'])
@jwt_required()
def daily_inventory_report():
    """
    Get daily inventory snapshot
    Optional: ?date=2025-02-17
    """
    try:
        # Get date parameter or use today
        date_str = request.args.get('date')
        if date_str:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            target_date = datetime.utcnow().date()
        
        # Get all active inventory items
        items = Inventory.query.filter_by(is_active=True).all()
        
        # Get transactions for this date
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())
        
        transactions = Transaction.query.filter(
            Transaction.timestamp >= start_of_day,
            Transaction.timestamp <= end_of_day
        ).all()
        
        # Calculate totals
        total_stock_value = sum(
            item.quantity * item.unit_price for item in items
        )
        
        low_stock_items = [
            item for item in items 
            if item.quantity <= item.reorder_level
        ]
        
        report_data = {
            'report_type': 'Daily Inventory Report',
            'date': target_date.strftime('%Y-%m-%d'),
            'generated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'summary': {
                'total_items': len(items),
                'total_stock_value': round(total_stock_value, 2),
                'low_stock_count': len(low_stock_items),
                'transactions_today': len(transactions)
            },
            'inventory_items': [item.to_dict() for item in items],
            'low_stock_items': [item.to_dict() for item in low_stock_items],
            'transactions': [t.to_dict() for t in transactions]
        }
        
        return jsonify(report_data), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# WEEKLY FRAUD SUMMARY
# ============================================
@reports_bp.route('/weekly-fraud', methods=['GET'])
@jwt_required()
def weekly_fraud_summary():
    """
    Get fraud alerts summary for the past week
    Optional: ?start_date=2025-02-10
    """
    try:
        claims = get_jwt()
        role = claims.get('role')
        
        # Only admin and manager can view fraud reports
        if role not in ['admin', 'manager']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Get date range
        start_date_str = request.args.get('start_date')
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        else:
            start_date = datetime.utcnow() - timedelta(days=7)
        
        end_date = start_date + timedelta(days=7)
        
        # Get fraud alerts in date range
        alerts = FraudAlert.query.filter(
            FraudAlert.detected_at >= start_date,
            FraudAlert.detected_at < end_date
        ).order_by(FraudAlert.detected_at.desc()).all()
        
        # Count by severity
        high_count = sum(1 for a in alerts if a.severity == 'high')
        medium_count = sum(1 for a in alerts if a.severity == 'medium')
        low_count = sum(1 for a in alerts if a.severity == 'low')
        
        # Count by status
        pending_count = sum(1 for a in alerts if a.status == 'pending')
        resolved_count = sum(1 for a in alerts if a.status == 'resolved')
        dismissed_count = sum(1 for a in alerts if a.status == 'dismissed')
        
        # Count by type
        alert_types = {}
        for alert in alerts:
            alert_types[alert.alert_type] = alert_types.get(alert.alert_type, 0) + 1
        
        report_data = {
            'report_type': 'Weekly Fraud Summary',
            'period': {
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d')
            },
            'generated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'summary': {
                'total_alerts': len(alerts),
                'by_severity': {
                    'high': high_count,
                    'medium': medium_count,
                    'low': low_count
                },
                'by_status': {
                    'pending': pending_count,
                    'resolved': resolved_count,
                    'dismissed': dismissed_count
                },
                'by_type': alert_types
            },
            'alerts': [alert.to_dict() for alert in alerts]
        }
        
        return jsonify(report_data), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# MONTHLY TRANSACTION ANALYTICS
# ============================================
@reports_bp.route('/monthly-analytics', methods=['GET'])
@jwt_required()
def monthly_analytics():
    """
    Get monthly transaction analytics
    Optional: ?month=2&year=2025
    """
    try:
        # Get month and year parameters
        month = int(request.args.get('month', datetime.utcnow().month))
        year = int(request.args.get('year', datetime.utcnow().year))
        
        # Calculate date range
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        
        # Get all transactions in this month
        transactions = Transaction.query.filter(
            Transaction.timestamp >= start_date,
            Transaction.timestamp < end_date
        ).all()
        
        # Calculate statistics
        stock_in_count = sum(1 for t in transactions if t.transaction_type == 'stock_in')
        stock_out_count = sum(1 for t in transactions if t.transaction_type == 'stock_out')
        waste_count = sum(1 for t in transactions if t.transaction_type == 'waste')
        
        stock_in_total = sum(
            t.quantity for t in transactions 
            if t.transaction_type == 'stock_in'
        )
        stock_out_total = sum(
            t.quantity for t in transactions 
            if t.transaction_type == 'stock_out'
        )
        waste_total = sum(
            t.quantity for t in transactions 
            if t.transaction_type == 'waste'
        )
        
        # Group by item
        item_stats = {}
        for trans in transactions:
            item_name = trans.inventory_item.item_name
            if item_name not in item_stats:
                item_stats[item_name] = {
                    'stock_in': 0,
                    'stock_out': 0,
                    'waste': 0
                }
            
            if trans.transaction_type == 'stock_in':
                item_stats[item_name]['stock_in'] += trans.quantity
            elif trans.transaction_type == 'stock_out':
                item_stats[item_name]['stock_out'] += trans.quantity
            elif trans.transaction_type == 'waste':
                item_stats[item_name]['waste'] += trans.quantity
        
        # Top 5 most used items
        sorted_items = sorted(
            item_stats.items(),
            key=lambda x: x[1]['stock_out'],
            reverse=True
        )[:5]
        
        report_data = {
            'report_type': 'Monthly Transaction Analytics',
            'period': {
                'month': month,
                'year': year,
                'month_name': start_date.strftime('%B')
            },
            'generated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'summary': {
                'total_transactions': len(transactions),
                'stock_in_count': stock_in_count,
                'stock_out_count': stock_out_count,
                'waste_count': waste_count,
                'total_stock_in': round(stock_in_total, 2),
                'total_stock_out': round(stock_out_total, 2),
                'total_waste': round(waste_total, 2)
            },
            'top_5_most_used_items': [
                {
                    'item_name': name,
                    'stock_out': round(stats['stock_out'], 2),
                    'waste': round(stats['waste'], 2)
                }
                for name, stats in sorted_items
            ],
            'item_statistics': item_stats,
            'transactions': [t.to_dict() for t in transactions]
        }
        
        return jsonify(report_data), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# USER ACTIVITY REPORT
# ============================================
@reports_bp.route('/user-activity', methods=['GET'])
@jwt_required()
def user_activity_report():
    """
    Get user activity report
    Optional: ?user_id=1&days=7
    """
    try:
        claims = get_jwt()
        role = claims.get('role')
        
        # Only admin and manager can view user activity
        if role not in ['admin', 'manager']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Get parameters
        user_id = request.args.get('user_id')
        days = int(request.args.get('days', 7))
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Build query
        audit_query = AuditLog.query.filter(
            AuditLog.timestamp >= start_date
        )
        
        if user_id:
            audit_query = audit_query.filter_by(user_id=int(user_id))
        
        audit_logs = audit_query.order_by(
            AuditLog.timestamp.desc()
        ).all()
        
        # Get transaction counts per user
        transaction_query = Transaction.query.filter(
            Transaction.timestamp >= start_date
        )
        
        if user_id:
            transaction_query = transaction_query.filter_by(
                user_id=int(user_id)
            )
        
        transactions = transaction_query.all()
        
        # Group by user
        user_stats = {}
        for trans in transactions:
            uid = trans.user_id
            if uid not in user_stats:
                user_stats[uid] = {
                    'username': trans.user.username,
                    'role': trans.user.role,
                    'stock_in': 0,
                    'stock_out': 0,
                    'waste': 0,
                    'total_transactions': 0
                }
            
            user_stats[uid]['total_transactions'] += 1
            if trans.transaction_type == 'stock_in':
                user_stats[uid]['stock_in'] += 1
            elif trans.transaction_type == 'stock_out':
                user_stats[uid]['stock_out'] += 1
            elif trans.transaction_type == 'waste':
                user_stats[uid]['waste'] += 1
        
        report_data = {
            'report_type': 'User Activity Report',
            'period': {
                'days': days,
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': datetime.utcnow().strftime('%Y-%m-%d')
            },
            'generated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'summary': {
                'total_audit_logs': len(audit_logs),
                'total_transactions': len(transactions)
            },
            'user_statistics': user_stats,
            'audit_logs': [
                {
                    'id': log.id,
                    'user_id': log.user_id,
                    'username': log.user.username if log.user else 'Unknown',
                    'action': log.action,
                    'details': log.details,
                    'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                }
                for log in audit_logs
            ]
        }
        
        return jsonify(report_data), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# LOW STOCK ALERT REPORT
# ============================================
@reports_bp.route('/low-stock-alert', methods=['GET'])
@jwt_required()
def low_stock_alert_report():
    """
    Get items that are low on stock
    """
    try:
        # Get items where quantity <= reorder_level
        low_stock_items = Inventory.query.filter(
            Inventory.quantity <= Inventory.reorder_level,
            Inventory.is_active == True
        ).all()
        
        # Get items where quantity is 0 (out of stock)
        out_of_stock = [item for item in low_stock_items if item.quantity == 0]
        
        # Get items critically low (below 50% of reorder level)
        critical_items = [
            item for item in low_stock_items 
            if item.quantity < (item.reorder_level * 0.5) and item.quantity > 0
        ]
        
        report_data = {
            'report_type': 'Low Stock Alert Report',
            'generated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'summary': {
                'total_low_stock': len(low_stock_items),
                'out_of_stock_count': len(out_of_stock),
                'critical_count': len(critical_items)
            },
            'out_of_stock': [item.to_dict() for item in out_of_stock],
            'critical_items': [item.to_dict() for item in critical_items],
            'all_low_stock': [item.to_dict() for item in low_stock_items]
        }
        
        return jsonify(report_data), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# WASTE ANALYSIS REPORT
# ============================================
@reports_bp.route('/waste-analysis', methods=['GET'])
@jwt_required()
def waste_analysis_report():
    """
    Get waste analysis report
    Optional: ?days=30
    """
    try:
        days = int(request.args.get('days', 30))
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Get all waste transactions
        waste_transactions = Transaction.query.filter(
            Transaction.transaction_type == 'waste',
            Transaction.timestamp >= start_date
        ).all()
        
        # Calculate total waste
        total_waste_value = sum(
            trans.quantity * trans.inventory_item.unit_price
            for trans in waste_transactions
        )
        
        # Group by item
        waste_by_item = {}
        for trans in waste_transactions:
            item_name = trans.inventory_item.item_name
            if item_name not in waste_by_item:
                waste_by_item[item_name] = {
                    'total_quantity': 0,
                    'unit': trans.inventory_item.unit,
                    'count': 0,
                    'reasons': []
                }
            
            waste_by_item[item_name]['total_quantity'] += trans.quantity
            waste_by_item[item_name]['count'] += 1
            if trans.reason:
                waste_by_item[item_name]['reasons'].append(trans.reason)
        
        # Top 5 most wasted items
        sorted_waste = sorted(
            waste_by_item.items(),
            key=lambda x: x[1]['total_quantity'],
            reverse=True
        )[:5]
        
        report_data = {
            'report_type': 'Waste Analysis Report',
            'period': {
                'days': days,
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': datetime.utcnow().strftime('%Y-%m-%d')
            },
            'generated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'summary': {
                'total_waste_transactions': len(waste_transactions),
                'estimated_waste_value': round(total_waste_value, 2)
            },
            'top_5_most_wasted': [
                {
                    'item_name': name,
                    'quantity': round(stats['total_quantity'], 2),
                    'unit': stats['unit'],
                    'count': stats['count']
                }
                for name, stats in sorted_waste
            ],
            'waste_by_item': waste_by_item,
            'transactions': [t.to_dict() for t in waste_transactions]
        }
        
        return jsonify(report_data), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# DASHBOARD SUMMARY
# ============================================
@reports_bp.route('/dashboard-summary', methods=['GET'])
@jwt_required()
def dashboard_summary():
    """
    Get overall dashboard summary statistics
    """
    try:
        # Inventory stats
        total_items = Inventory.query.filter_by(is_active=True).count()
        low_stock = Inventory.query.filter(
            Inventory.quantity <= Inventory.reorder_level,
            Inventory.is_active == True
        ).count()
        
        # Transaction stats (last 7 days)
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_transactions = Transaction.query.filter(
            Transaction.timestamp >= week_ago
        ).count()
        
        # Fraud stats
        pending_alerts = FraudAlert.query.filter_by(status='pending').count()
        high_severity_alerts = FraudAlert.query.filter(
            FraudAlert.status == 'pending',
            FraudAlert.severity == 'high'
        ).count()
        
        # User activity (today)
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0)
        today_transactions = Transaction.query.filter(
            Transaction.timestamp >= today_start
        ).count()
        
        summary = {
            'inventory': {
                'total_items': total_items,
                'low_stock_items': low_stock
            },
            'transactions': {
                'last_7_days': recent_transactions,
                'today': today_transactions
            },
            'fraud_alerts': {
                'pending': pending_alerts,
                'high_severity_pending': high_severity_alerts
            },
            'generated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return jsonify(summary), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500