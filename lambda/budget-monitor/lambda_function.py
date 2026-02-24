import json
import boto3
import os
from datetime import datetime, timedelta
from decimal import Decimal

ce = boto3.client('ce')
budgets = boto3.client('budgets')
sns = boto3.client('sns')
s3_client = boto3.client('s3')

COST_ALERTS_TOPIC = os.environ['COST_ALERTS_TOPIC']
S3_BUCKET = os.environ['S3_BUCKET']
DAILY_BUDGET = float(os.environ.get('DAILY_BUDGET', '10'))
MONTHLY_BUDGET = float(os.environ.get('MONTHLY_BUDGET', '100'))
ACCOUNT_ID = os.environ['ACCOUNT_ID']

def lambda_handler(event, context):
    """
    Monitors AWS budgets and spending
    """
    print(f"Starting budget monitoring at {datetime.now()}")
    
    try:
        # Get current month spending
        month_spending = get_month_to_date_spending()
        
        # Get today's spending
        today_spending = get_today_spending()
        
        # Get budget status
        budget_status = get_budget_status()
        
        # Check for budget alerts
        alerts = check_budget_thresholds(month_spending, today_spending)
        
        # Save monitoring data
        save_budget_data(month_spending, today_spending, budget_status)
        
        # Send alerts if needed
        if alerts:
            send_budget_alerts(alerts, month_spending, today_spending)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'month_spending': month_spending,
                'today_spending': today_spending,
                'monthly_budget': MONTHLY_BUDGET,
                'daily_budget': DAILY_BUDGET,
                'alerts_triggered': len(alerts)
            }, default=str)
        }
        
    except Exception as e:
        print(f"Error in budget monitoring: {str(e)}")
        raise

def get_month_to_date_spending():
    """Get spending for current month"""
    today = datetime.now().date()
    start_of_month = today.replace(day=1)
    
    response = ce.get_cost_and_usage(
        TimePeriod={
            'Start': start_of_month.strftime('%Y-%m-%d'),
            'End': today.strftime('%Y-%m-%d')
        },
        Granularity='MONTHLY',
        Metrics=['BlendedCost']
    )
    
    if response['ResultsByTime']:
        total = float(response['ResultsByTime'][0]['Total']['BlendedCost']['Amount'])
        return round(total, 2)
    
    return 0

def get_today_spending():
    """Get spending for today"""
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    
    response = ce.get_cost_and_usage(
        TimePeriod={
            'Start': yesterday.strftime('%Y-%m-%d'),
            'End': today.strftime('%Y-%m-%d')
        },
        Granularity='DAILY',
        Metrics=['BlendedCost']
    )
    
    if response['ResultsByTime']:
        total = float(response['ResultsByTime'][0]['Total']['BlendedCost']['Amount'])
        return round(total, 2)
    
    return 0

def get_budget_status():
    """Get status of AWS Budgets"""
    budget_list = []
    
    try:
        response = budgets.describe_budgets(AccountId=ACCOUNT_ID)
        
        for budget in response['Budgets']:
            budget_list.append({
                'name': budget['BudgetName'],
                'limit': float(budget['BudgetLimit']['Amount']),
                'type': budget['TimeUnit'],
                'calculated_spend': budget.get('CalculatedSpend', {})
            })
    except Exception as e:
        print(f"Error getting budget status: {str(e)}")
    
    return budget_list

def check_budget_thresholds(month_spending, today_spending):
    """Check if spending exceeds thresholds"""
    alerts = []
    
    # Check daily budget
    daily_percent = (today_spending / DAILY_BUDGET * 100) if DAILY_BUDGET > 0 else 0
    
    if daily_percent >= 100:
        alerts.append({
            'type': 'daily_exceeded',
            'severity': 'critical',
            'message': f"Daily spending (${today_spending}) exceeded budget (${DAILY_BUDGET})",
            'percent': daily_percent
        })
    elif daily_percent >= 80:
        alerts.append({
            'type': 'daily_warning',
            'severity': 'warning',
            'message': f"Daily spending at {daily_percent:.1f}% of budget",
            'percent': daily_percent
        })
    
    # Check monthly budget
    monthly_percent = (month_spending / MONTHLY_BUDGET * 100) if MONTHLY_BUDGET > 0 else 0
    
    if monthly_percent >= 100:
        alerts.append({
            'type': 'monthly_exceeded',
            'severity': 'critical',
            'message': f"Monthly spending (${month_spending}) exceeded budget (${MONTHLY_BUDGET})",
            'percent': monthly_percent
        })
    elif monthly_percent >= 80:
        alerts.append({
            'type': 'monthly_warning',
            'severity': 'warning',
            'message': f"Monthly spending at {monthly_percent:.1f}% of budget",
            'percent': monthly_percent
        })
    
    # Forecast check
    days_in_month = (datetime.now().date().replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    day_of_month = datetime.now().date().day
    days_remaining = days_in_month.day - day_of_month
    
    if day_of_month > 0:
        daily_avg = month_spending / day_of_month
        projected_month = daily_avg * days_in_month.day
        
        if projected_month > MONTHLY_BUDGET:
            alerts.append({
                'type': 'monthly_forecast_exceeded',
                'severity': 'warning',
                'message': f"Projected monthly spending (${projected_month:.2f}) will exceed budget (${MONTHLY_BUDGET})",
                'percent': (projected_month / MONTHLY_BUDGET * 100)
            })
    
    return alerts

def save_budget_data(month_spending, today_spending, budget_status):
    """Save budget monitoring data to S3"""
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    
    data = {
        'timestamp': timestamp,
        'month_spending': month_spending,
        'today_spending': today_spending,
        'monthly_budget': MONTHLY_BUDGET,
        'daily_budget': DAILY_BUDGET,
        'budget_status': budget_status,
        'month_percent': (month_spending / MONTHLY_BUDGET * 100) if MONTHLY_BUDGET > 0 else 0,
        'scan_date': datetime.now().isoformat()
    }
    
    key = f"budget/budget-monitor-{timestamp}.json"
    
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(data, indent=2, default=str),
        ContentType='application/json'
    )
    
    print(f"Budget data saved to s3://{S3_BUCKET}/{key}")

def send_budget_alerts(alerts, month_spending, today_spending):
    """Send budget alert notifications"""
    critical_alerts = [a for a in alerts if a['severity'] == 'critical']
    
    if critical_alerts:
        subject = "CRITICAL: AWS Budget Exceeded"
    else:
        subject = "⚠️ AWS Budget Warning"
    
    message = "AWS Budget Alert\n\n"
    message += f"Current Status:\n"
    message += f"  Today's Spending: ${today_spending:.2f} / ${DAILY_BUDGET:.2f}\n"
    message += f"  Month to Date: ${month_spending:.2f} / ${MONTHLY_BUDGET:.2f}\n\n"
    
    message += "Alerts:\n"
    message += "-" * 50 + "\n"
    
    for alert in alerts:
        icon = "" if alert['severity'] == 'critical' else "⚠️"
        message += f"{icon} {alert['message']} ({alert['percent']:.1f}%)\n\n"
    
    message += "\nPlease review your AWS spending and consider taking action to reduce costs.\n"
    
    sns.publish(
        TopicArn=COST_ALERTS_TOPIC,
        Subject=subject,
        Message=message
    )
    
    print(f"Budget alerts sent: {len(alerts)} alerts")
