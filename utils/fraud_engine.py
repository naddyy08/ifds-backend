# utils/fraud_engine.py
from models import db, Transaction, FraudAlert, Inventory
from datetime import datetime, timedelta, timezone
import numpy as np

# ✅ Malaysia timezone (UTC+8)
MALAYSIA_TZ = timezone(timedelta(hours=8))


def analyze_transaction(transaction):
    """
    Main fraud detection function.
    Analyzes a transaction and creates alerts if suspicious.
    Returns list of alerts created.
    """
    alerts = []

    # Run all fraud detection checks
    alert1 = check_large_quantity(transaction)
    alert2 = check_excessive_waste(transaction)
    alert3 = check_after_hours(transaction)
    alert4 = check_rapid_removals(transaction)
    alert5 = check_sudden_stock_drop(transaction)

    # Collect any alerts that were found
    for alert in [alert1, alert2, alert3, alert4, alert5]:
        if alert:
            alerts.append(alert)

    return alerts


# ============================================
# CHECK 1: Large Quantity Removal
# ============================================
def check_large_quantity(transaction):
    """
    Flag if quantity removed is unusually large
    Threshold: more than 50% of previous stock in one transaction
    """

    if transaction.transaction_type not in ['stock_out', 'waste']:
        return None

    if transaction.previous_quantity <= 0:
        return None

    percentage_removed = (
        transaction.quantity / transaction.previous_quantity
    ) * 100

    if percentage_removed >= 50:

        if percentage_removed >= 80:
            severity = 'high'
        elif percentage_removed >= 60:
            severity = 'medium'
        else:
            severity = 'low'

        alert = FraudAlert(
            transaction_id=transaction.id,
            alert_type='LARGE_QUANTITY_REMOVAL',
            severity=severity,
            description=(
                f'Large quantity removal detected! '
                f'{transaction.quantity} {transaction.inventory_item.unit} removed '
                f'({percentage_removed:.1f}% of previous stock '
                f'{transaction.previous_quantity} {transaction.inventory_item.unit}). '
                f'Item: {transaction.inventory_item.item_name}'
            )
        )

        transaction.is_flagged = True
        db.session.add(alert)
        db.session.commit()

        return alert

    return None


# ============================================
# CHECK 2: Excessive Waste
# ============================================
def check_excessive_waste(transaction):
    """
    Flag if waste recorded is unusually high
    Checks: more than 30% of stock reported as waste
    """

    if transaction.transaction_type != 'waste':
        return None

    if transaction.previous_quantity <= 0:
        return None

    waste_percentage = (
        transaction.quantity / transaction.previous_quantity
    ) * 100

    if waste_percentage >= 30:

        if waste_percentage >= 60:
            severity = 'high'
        elif waste_percentage >= 45:
            severity = 'medium'
        else:
            severity = 'low'

        alert = FraudAlert(
            transaction_id=transaction.id,
            alert_type='EXCESSIVE_WASTE',
            severity=severity,
            description=(
                f'Excessive waste detected! '
                f'{transaction.quantity} {transaction.inventory_item.unit} '
                f'({waste_percentage:.1f}% of stock) reported as waste. '
                f'Item: {transaction.inventory_item.item_name}. '
                f'Reason given: {transaction.reason}'
            )
        )

        transaction.is_flagged = True
        db.session.add(alert)
        db.session.commit()

        return alert

    return None


# ============================================
# CHECK 3: After Hours Activity (Malaysia UTC+8)
# ============================================
def check_after_hours(transaction):
    """
    Flag transactions outside normal working hours in Malaysia time (UTC+8).
    Normal hours: 6 AM to 11 PM MYT
    """

    # ✅ Convert UTC timestamp to Malaysia time (UTC+8)
    local_time = transaction.timestamp.replace(
        tzinfo=timezone.utc
    ).astimezone(MALAYSIA_TZ)

    transaction_hour = local_time.hour

    # After hours: before 6 AM or at/after 11 PM MYT
    if transaction_hour < 6 or transaction_hour >= 23:

        # High severity for stock_out and waste after hours
        if transaction.transaction_type in ['stock_out', 'waste']:
            severity = 'high'
        else:
            severity = 'medium'

        alert = FraudAlert(
            transaction_id=transaction.id,
            alert_type='AFTER_HOURS_ACTIVITY',
            severity=severity,
            description=(
                f'Transaction recorded outside normal hours! '
                f'Time: {local_time.strftime("%I:%M %p")} MYT '
                f'(Normal hours: 06:00 AM - 11:00 PM MYT). '
                f'Type: {transaction.transaction_type.upper()}. '
                f'Item: {transaction.inventory_item.item_name}'
            )
        )

        transaction.is_flagged = True
        db.session.add(alert)
        db.session.commit()

        return alert

    return None


# ============================================
# CHECK 4: Rapid Multiple Removals
# ============================================
def check_rapid_removals(transaction):
    """
    Flag if same item is removed multiple times within short period
    Threshold: more than 3 removals within 1 hour for same item
    """

    if transaction.transaction_type not in ['stock_out', 'waste']:
        return None

    one_hour_ago = datetime.utcnow() - timedelta(hours=1)

    recent_removals = Transaction.query.filter(
        Transaction.inventory_id == transaction.inventory_id,
        Transaction.transaction_type.in_(['stock_out', 'waste']),
        Transaction.timestamp >= one_hour_ago,
        Transaction.id != transaction.id
    ).count()

    if recent_removals >= 3:

        alert = FraudAlert(
            transaction_id=transaction.id,
            alert_type='RAPID_MULTIPLE_REMOVALS',
            severity='high',
            description=(
                f'Multiple rapid removals detected! '
                f'{recent_removals + 1} removals of '
                f'{transaction.inventory_item.item_name} '
                f'within the last hour. '
                f'This pattern may indicate unauthorized stock removal.'
            )
        )

        transaction.is_flagged = True
        db.session.add(alert)
        db.session.commit()

        return alert

    return None


# ============================================
# CHECK 5: Sudden Stock Drop
# ============================================
def check_sudden_stock_drop(transaction):
    """
    Flag if stock drops below critical level suddenly
    Threshold: stock drops below 20% of reorder level
    """

    if transaction.transaction_type not in ['stock_out', 'waste']:
        return None

    item = transaction.inventory_item

    if item.reorder_level > 0:
        critical_level = item.reorder_level * 0.2

        if transaction.new_quantity <= critical_level:

            alert = FraudAlert(
                transaction_id=transaction.id,
                alert_type='CRITICAL_STOCK_LEVEL',
                severity='high',
                description=(
                    f'Critical stock level reached! '
                    f'{item.item_name} dropped to '
                    f'{transaction.new_quantity} {item.unit} '
                    f'(Reorder level: {item.reorder_level} {item.unit}). '
                    f'Immediate investigation recommended.'
                )
            )

            transaction.is_flagged = True
            db.session.add(alert)
            db.session.commit()

            return alert

    return None


# ============================================
# GET FRAUD STATISTICS
# ============================================
def get_fraud_statistics():
    """
    Get overall fraud detection statistics
    """
    total_alerts = FraudAlert.query.count()
    pending = FraudAlert.query.filter_by(status='pending').count()
    resolved = FraudAlert.query.filter_by(status='resolved').count()
    dismissed = FraudAlert.query.filter_by(status='dismissed').count()

    high = FraudAlert.query.filter_by(severity='high').count()
    medium = FraudAlert.query.filter_by(severity='medium').count()
    low = FraudAlert.query.filter_by(severity='low').count()

    return {
        'total_alerts': total_alerts,
        'by_status': {
            'pending': pending,
            'resolved': resolved,
            'dismissed': dismissed
        },
        'by_severity': {
            'high': high,
            'medium': medium,
            'low': low
        }
    }