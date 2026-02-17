import json
import boto3
import os
from datetime import datetime, timedelta
from decimal import Decimal

ce = boto3.client('ce')
dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')
s3 = boto3.client('s3')

ANOMALIES_TABLE = os.environ['ANOMALIES_TABLE']
COST_ALERTS_TOPIC = os.environ['COST_ALERTS_TOPIC']
S3_BUCKET = os.environ['S3_BUCKET']
THRESHOLD_PERCENTAGE = float(os.environ.get('THRESHOLD_PERCENTAGE', '25'))

def lambda_handler(event, context):
    """
    Analyzes AWS costs and detects anomalies
    """
    print(f"Starting cost analysis at {datetime.now()}")
    
    try:
        # Get cost data
        cost_data = get_cost_data()
        
        # Detect anomalies
        anomalies = detect_anomalies(cost_data)
        
        # Get cost by service
        service_costs = get_cost_by_service()
        
        # Get cost forecast
        forecast = get_cost_forecast()
        
        # Save results
        save_cost_analysis(cost_data, anomalies, service_costs, forecast)
        
        # Send alerts if anomalies detected
        if anomalies:
            send_anomaly_alerts(anomalies)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'anomalies_detected': len(anomalies),
                'total_cost_last_7_days': cost_data['total_cost'],
                'services_analyzed': len(service_costs)
            }, default=str)
        }
        
    except Exception as e:
        print(f"Error in cost analysis: {str(e)}")
        raise

def get_cost_data():
    """Get cost and usage data from Cost Explorer"""
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)
    
    response = ce.get_cost_and_usage(
        TimePeriod={
            'Start': start_date.strftime('%Y-%m-%d'),
            'End': end_date.strftime('%Y-%m-%d')
        },
        Granularity='DAILY',
        Metrics=['BlendedCost', 'UnblendedCost', 'UsageQuantity']
    )
    
    daily_costs = []
    total_cost = 0
    
    for result in response['ResultsByTime']:
        cost = float(result['Total']['BlendedCost']['Amount'])
        daily_costs.append({
            'date': result['TimePeriod']['Start'],
            'cost': cost
        })
        total_cost += cost
    
    return {
        'daily_costs': daily_costs,
        'total_cost': total_cost,
        'period_days': 30
    }

def detect_anomalies(cost_data):
    """Detect cost anomalies using statistical analysis"""
    anomalies = []
    daily_costs = cost_data['daily_costs']
    
    if len(daily_costs) < 7:
        print("Not enough data for anomaly detection")
        return anomalies
    
    # Calculate baseline (average of first 23 days)
    baseline_costs = [d['cost'] for d in daily_costs[:-7]]
    baseline_avg = sum(baseline_costs) / len(baseline_costs)
    
    # Check last 7 days for anomalies
    for day in daily_costs[-7:]:
        deviation = ((day['cost'] - baseline_avg) / baseline_avg) * 100
        
        if abs(deviation) > THRESHOLD_PERCENTAGE:
            anomaly = {
                'date': day['date'],
                'cost': day['cost'],
                'baseline': baseline_avg,
                'deviation_percentage': deviation,
                'severity': 'high' if abs(deviation) > 50 else 'medium'
            }
            anomalies.append(anomaly)
            
            # Save to DynamoDB
            save_anomaly(anomaly)
    
    return anomalies

def get_cost_by_service():
    """Get costs broken down by service"""
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=7)
    
    response = ce.get_cost_and_usage(
        TimePeriod={
            'Start': start_date.strftime('%Y-%m-%d'),
            'End': end_date.strftime('%Y-%m-%d')
        },
        Granularity='DAILY',
        Metrics=['BlendedCost'],
        GroupBy=[
            {'Type': 'DIMENSION', 'Key': 'SERVICE'}
        ]
    )
    
    service_costs = {}
    for result in response['ResultsByTime']:
        for group in result['Groups']:
            service = group['Keys'][0]
            cost = float(group['Metrics']['BlendedCost']['Amount'])
            
            if service not in service_costs:
                service_costs[service] = 0
            service_costs[service] += cost
    
    # Sort by cost
    sorted_services = sorted(
        service_costs.items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    return dict(sorted_services[:10])  # Top 10 services

def get_cost_forecast():
    """Get cost forecast for next 7 days"""
    try:
        start_date = datetime.now().date()
        end_date = start_date + timedelta(days=7)
        
        response = ce.get_cost_forecast(
            TimePeriod={
                'Start': start_date.strftime('%Y-%m-%d'),
                'End': end_date.strftime('%Y-%m-%d')
            },
            Metric='BLENDED_COST',
            Granularity='DAILY'
        )
        
        return {
            'total': float(response['Total']['Amount']),
            'period': '7_days'
        }
    except Exception as e:
        print(f"Error getting forecast: {str(e)}")
        return {'total': 0, 'period': '7_days'}

def save_anomaly(anomaly):
    """Save anomaly to DynamoDB"""
    table = dynamodb.Table(ANOMALIES_TABLE)
    
    anomaly_id = f"{anomaly['date']}-{int(datetime.now().timestamp())}"
    
    # Calculate TTL (30 days from now)
    ttl = int((datetime.now() + timedelta(days=30)).timestamp())
    
    table.put_item(
        Item={
            'anomaly_id': anomaly_id,
            'detected_date': anomaly['date'],
            'cost': Decimal(str(anomaly['cost'])),
            'baseline': Decimal(str(anomaly['baseline'])),
            'deviation_percentage': Decimal(str(anomaly['deviation_percentage'])),
            'severity': anomaly['severity'],
            'status': 'new',
            'detected_at': datetime.now().isoformat(),
            'ttl': ttl
        }
    )

def save_cost_analysis(cost_data, anomalies, service_costs, forecast):
    """Save analysis results to S3"""
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    
    analysis = {
        'timestamp': timestamp,
        'cost_data': cost_data,
        'anomalies': anomalies,
        'service_costs': service_costs,
        'forecast': forecast
    }
    
    key = f"analysis/cost-analysis-{timestamp}.json"
    
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(analysis, indent=2, default=str),
        ContentType='application/json'
    )
    
    print(f"Analysis saved to s3://{S3_BUCKET}/{key}")

def send_anomaly_alerts(anomalies):
    """Send SNS alerts for detected anomalies"""
    high_severity = [a for a in anomalies if a['severity'] == 'high']
    
    subject = f"🚨 Cost Anomaly Detected: {len(anomalies)} anomalies found"
    
    message = "AWS Cost Anomaly Alert\n\n"
    message += f"Detected {len(anomalies)} cost anomalies:\n\n"
    
    for anomaly in anomalies:
        message += f"Date: {anomaly['date']}\n"
        message += f"Cost: ${anomaly['cost']:.2f}\n"
        message += f"Baseline: ${anomaly['baseline']:.2f}\n"
        message += f"Deviation: {anomaly['deviation_percentage']:.1f}%\n"
        message += f"Severity: {anomaly['severity']}\n\n"
    
    sns.publish(
        TopicArn=COST_ALERTS_TOPIC,
        Subject=subject,
        Message=message
    )
    
    print(f"Alert sent for {len(anomalies)} anomalies")
