import json
import boto3
import os
from datetime import datetime, timedelta
from decimal import Decimal
import csv
from io import StringIO

ce = boto3.client('ce')
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')

S3_BUCKET = os.environ['S3_BUCKET']
COST_ALERTS_TOPIC = os.environ['COST_ALERTS_TOPIC']
IDLE_RESOURCES_TABLE = os.environ['IDLE_RESOURCES_TABLE']
ANOMALIES_TABLE = os.environ['ANOMALIES_TABLE']

def lambda_handler(event, context):
    """
    Generates comprehensive FinOps reports
    """
    print(f"Generating FinOps report at {datetime.now()}")
    
    try:
        report_type = event.get('report_type', 'weekly')
        
        # Generate report sections
        cost_summary = generate_cost_summary()
        service_breakdown = generate_service_breakdown()
        idle_resources_summary = generate_idle_resources_summary()
        anomalies_summary = generate_anomalies_summary()
        recommendations = generate_recommendations()
        
        # Compile report
        report = {
            'report_date': datetime.now().isoformat(),
            'report_type': report_type,
            'cost_summary': cost_summary,
            'service_breakdown': service_breakdown,
            'idle_resources': idle_resources_summary,
            'anomalies': anomalies_summary,
            'recommendations': recommendations
        }
        
        # Save report in multiple formats
        report_files = save_report(report)
        
        # Send report notification
        send_report_notification(report, report_files)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'report_generated': True,
                'report_files': report_files,
                'total_potential_savings': idle_resources_summary['total_savings']
            }, default=str)
        }
        
    except Exception as e:
        print(f"Error generating report: {str(e)}")
        raise

def generate_cost_summary():
    """Generate cost summary for the past 30 days"""
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)
    
    response = ce.get_cost_and_usage(
        TimePeriod={
            'Start': start_date.strftime('%Y-%m-%d'),
            'End': end_date.strftime('%Y-%m-%d')
        },
        Granularity='DAILY',
        Metrics=['BlendedCost', 'UnblendedCost']
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
    
    # Calculate averages
    avg_daily = total_cost / len(daily_costs) if daily_costs else 0
    
    # Get last 7 days for trend
    last_7_days_cost = sum(d['cost'] for d in daily_costs[-7:])
    prev_7_days_cost = sum(d['cost'] for d in daily_costs[-14:-7])
    
    trend = 'increasing' if last_7_days_cost > prev_7_days_cost else 'decreasing'
    trend_percent = ((last_7_days_cost - prev_7_days_cost) / prev_7_days_cost * 100) if prev_7_days_cost > 0 else 0
    
    return {
        'total_30_days': round(total_cost, 2),
        'average_daily': round(avg_daily, 2),
        'last_7_days': round(last_7_days_cost, 2),
        'trend': trend,
        'trend_percent': round(trend_percent, 2),
        'daily_breakdown': daily_costs[-7:]  # Last 7 days
    }

def generate_service_breakdown():
    """Generate breakdown by AWS service"""
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=7)
    
    response = ce.get_cost_and_usage(
        TimePeriod={
            'Start': start_date.strftime('%Y-%m-%d'),
            'End': end_date.strftime('%Y-%m-%d')
        },
        Granularity='MONTHLY',
        Metrics=['BlendedCost'],
        GroupBy=[
            {'Type': 'DIMENSION', 'Key': 'SERVICE'}
        ]
    )
    
    service_costs = []
    total = 0
    
    for result in response['ResultsByTime']:
        for group in result['Groups']:
            service = group['Keys'][0]
            cost = float(group['Metrics']['BlendedCost']['Amount'])
            
            if cost > 0.01:  # Filter out negligible costs
                service_costs.append({
                    'service': service,
                    'cost': round(cost, 2)
                })
                total += cost
    
    # Sort by cost
    service_costs.sort(key=lambda x: x['cost'], reverse=True)
    
    # Calculate percentages
    for service in service_costs:
        service['percentage'] = round((service['cost'] / total * 100), 1) if total > 0 else 0
    
    return {
        'services': service_costs[:10],  # Top 10
        'total_cost': round(total, 2)
    }

def generate_idle_resources_summary():
    """Generate summary of idle resources"""
    table = dynamodb.Table(IDLE_RESOURCES_TABLE)
    
    # Get resources from last scan
    cutoff_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    try:
        response = table.scan(
            FilterExpression='scan_date >= :date',
            ExpressionAttributeValues={':date': cutoff_date}
        )
        
        resources_by_type = {}
        total_savings = 0
        
        for item in response['Items']:
            rtype = item['resource_type']
            
            if rtype not in resources_by_type:
                resources_by_type[rtype] = {
                    'count': 0,
                    'resources': []
                }
            
            resources_by_type[rtype]['count'] += 1
            resources_by_type[rtype]['resources'].append({
                'id': item['resource_id'],
                'metadata': item.get('metadata', {})
            })
        
        return {
            'total_idle_resources': sum(r['count'] for r in resources_by_type.values()),
            'by_type': resources_by_type,
            'total_savings': round(total_savings, 2)
        }
        
    except Exception as e:
        print(f"Error getting idle resources: {str(e)}")
        return {'total_idle_resources': 0, 'by_type': {}, 'total_savings': 0}

def generate_anomalies_summary():
    """Generate summary of cost anomalies"""
    table = dynamodb.Table(ANOMALIES_TABLE)
    
    # Get anomalies from last 7 days
    cutoff_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    try:
        response = table.scan(
            FilterExpression='detected_date >= :date',
            ExpressionAttributeValues={':date': cutoff_date}
        )
        
        anomalies = []
        for item in response['Items']:
            anomalies.append({
                'date': item['detected_date'],
                'deviation': float(item.get('deviation_percentage', 0)),
                'severity': item.get('severity', 'unknown'),
                'cost': float(item.get('cost', 0))
            })
        
        # Sort by severity
        severity_order = {'high': 0, 'medium': 1, 'low': 2}
        anomalies.sort(key=lambda x: (severity_order.get(x['severity'], 3), abs(x['deviation'])), reverse=True)
        
        return {
            'total_anomalies': len(anomalies),
            'high_severity': len([a for a in anomalies if a['severity'] == 'high']),
            'anomalies': anomalies[:5]  # Top 5
        }
        
    except Exception as e:
        print(f"Error getting anomalies: {str(e)}")
        return {'total_anomalies': 0, 'high_severity': 0, 'anomalies': []}

def generate_recommendations():
    """Generate cost optimization recommendations"""
    recommendations = []
    
    # Get idle resources
    idle_summary = generate_idle_resources_summary()
    
    if idle_summary['total_idle_resources'] > 0:
        recommendations.append({
            'priority': 'high',
            'category': 'Resource Cleanup',
            'recommendation': f"Clean up {idle_summary['total_idle_resources']} idle resources",
            'potential_savings': idle_summary['total_savings'],
            'action': 'Review and terminate/delete unused resources'
        })
    
    # Get service breakdown for rightsizing recommendations
    service_breakdown = generate_service_breakdown()
    
    # EC2 recommendations
    ec2_cost = next((s['cost'] for s in service_breakdown['services'] if 'EC2' in s['service']), 0)
    if ec2_cost > 20:
        recommendations.append({
            'priority': 'medium',
            'category': 'EC2 Optimization',
            'recommendation': 'Consider Reserved Instances or Savings Plans',
            'potential_savings': round(ec2_cost * 0.3, 2),  # Estimate 30% savings
            'action': 'Review EC2 usage patterns and purchase commitments'
        })
    
    # RDS recommendations
    rds_cost = next((s['cost'] for s in service_breakdown['services'] if 'RDS' in s['service'] or 'Database' in s['service']), 0)
    if rds_cost > 15:
        recommendations.append({
            'priority': 'medium',
            'category': 'RDS Optimization',
            'recommendation': 'Review RDS instance sizes and utilization',
            'potential_savings': round(rds_cost * 0.2, 2),
            'action': 'Downsize underutilized databases or use Aurora Serverless'
        })
    
    # Storage recommendations
    s3_cost = next((s['cost'] for s in service_breakdown['services'] if 'S3' in s['service']), 0)
    if s3_cost > 5:
        recommendations.append({
            'priority': 'low',
            'category': 'Storage Optimization',
            'recommendation': 'Implement S3 lifecycle policies',
            'potential_savings': round(s3_cost * 0.4, 2),
            'action': 'Move infrequent data to S3-IA or Glacier'
        })
    
    # Sort by priority
    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    recommendations.sort(key=lambda x: priority_order.get(x['priority'], 3))
    
    return recommendations

def save_report(report):
    """Save report in multiple formats"""
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    report_files = {}
    
    # Save JSON format
    json_key = f"reports/finops-report-{timestamp}.json"
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=json_key,
        Body=json.dumps(report, indent=2, default=str),
        ContentType='application/json'
    )
    report_files['json'] = json_key
    
    # Save HTML format
    html_content = generate_html_report(report)
    html_key = f"reports/finops-report-{timestamp}.html"
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=html_key,
        Body=html_content,
        ContentType='text/html'
    )
    report_files['html'] = html_key
    
    # Save CSV format (summary)
    csv_content = generate_csv_report(report)
    csv_key = f"reports/finops-report-{timestamp}.csv"
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=csv_key,
        Body=csv_content,
        ContentType='text/csv'
    )
    report_files['csv'] = csv_key
    
    print(f"Report saved: {report_files}")
    
    return report_files

def generate_html_report(report):
    """Generate HTML formatted report"""
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>FinOps Report - {report['report_date']}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 40px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #232F3E;
            border-bottom: 3px solid #FF9900;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #232F3E;
            margin-top: 30px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #232F3E;
            color: white;
        }}
        .metric {{
            display: inline-block;
            margin: 15px 20px 15px 0;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 5px;
            min-width: 200px;
        }}
        .metric-label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
            color: #232F3E;
        }}
        .priority-high {{ color: #d32f2f; }}
        .priority-medium {{ color: #f57c00; }}
        .priority-low {{ color: #388e3c; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>FinOps Report</h1>
        <p>Generated: {report['report_date']}</p>
        
        <h2>Cost Summary (Last 30 Days)</h2>
        <div class="metric">
            <div class="metric-label">Total Cost</div>
            <div class="metric-value">${report['cost_summary']['total_30_days']:.2f}</div>
        </div>
        <div class="metric">
            <div class="metric-label">Daily Average</div>
            <div class="metric-value">${report['cost_summary']['average_daily']:.2f}</div>
        </div>
        <div class="metric">
            <div class="metric-label">Last 7 Days</div>
            <div class="metric-value">${report['cost_summary']['last_7_days']:.2f}</div>
        </div>
        <div class="metric">
            <div class="metric-label">Trend</div>
            <div class="metric-value">{report['cost_summary']['trend']} ({report['cost_summary']['trend_percent']:.1f}%)</div>
        </div>
        
        <h2>🔧 Service Breakdown</h2>
        <table>
            <thead>
                <tr>
                    <th>Service</th>
                    <th>Cost</th>
                    <th>Percentage</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for service in report['service_breakdown']['services']:
        html += f"""
                <tr>
                    <td>{service['service']}</td>
                    <td>${service['cost']:.2f}</td>
                    <td>{service['percentage']:.1f}%</td>
                </tr>
        """
    
    html += """
            </tbody>
        </table>
        
        <h2>💤 Idle Resources</h2>
        <p>Total Idle Resources: <strong>{}</strong></p>
        <p>Potential Monthly Savings: <strong>${:.2f}</strong></p>
    """.format(
        report['idle_resources']['total_idle_resources'],
        report['idle_resources']['total_savings']
    )
    
    html += """
        <h2>Recommendations</h2>
        <table>
            <thead>
                <tr>
                    <th>Priority</th>
                    <th>Category</th>
                    <th>Recommendation</th>
                    <th>Potential Savings</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for rec in report['recommendations']:
        priority_class = f"priority-{rec['priority']}"
        html += f"""
                <tr>
                    <td class="{priority_class}">{rec['priority'].upper()}</td>
                    <td>{rec['category']}</td>
                    <td>{rec['recommendation']}<br><small>{rec['action']}</small></td>
                    <td>${rec['potential_savings']:.2f}/mo</td>
                </tr>
        """
    
    html += """
            </tbody>
        </table>
    </div>
</body>
</html>
    """
    
    return html

def generate_csv_report(report):
    """Generate CSV formatted report"""
    output = StringIO()
    writer = csv.writer(output)
    
    # Cost Summary
    writer.writerow(['Cost Summary'])
    writer.writerow(['Metric', 'Value'])
    writer.writerow(['Total (30 days)', f"${report['cost_summary']['total_30_days']:.2f}"])
    writer.writerow(['Daily Average', f"${report['cost_summary']['average_daily']:.2f}"])
    writer.writerow(['Last 7 Days', f"${report['cost_summary']['last_7_days']:.2f}"])
    writer.writerow(['Trend', f"{report['cost_summary']['trend']} ({report['cost_summary']['trend_percent']:.1f}%)"])
    writer.writerow([])
    
    # Service Breakdown
    writer.writerow(['Service Breakdown'])
    writer.writerow(['Service', 'Cost', 'Percentage'])
    for service in report['service_breakdown']['services']:
        writer.writerow([service['service'], f"${service['cost']:.2f}", f"{service['percentage']:.1f}%"])
    writer.writerow([])
    
    # Recommendations
    writer.writerow(['Recommendations'])
    writer.writerow(['Priority', 'Category', 'Recommendation', 'Potential Savings'])
    for rec in report['recommendations']:
        writer.writerow([rec['priority'], rec['category'], rec['recommendation'], f"${rec['potential_savings']:.2f}"])
    
    return output.getvalue()

def send_report_notification(report, report_files):
    """Send report notification"""
    subject = f"Weekly FinOps Report - ${report['cost_summary']['total_30_days']:.2f}"
    
    message = "AWS FinOps Weekly Report\n\n"
    message += f"Report Period: Last 30 days\n"
    message += f"Generated: {report['report_date']}\n\n"
    
    message += "COST SUMMARY\n"
    message += "-" * 50 + "\n"
    message += f"Total Spend: ${report['cost_summary']['total_30_days']:.2f}\n"
    message += f"Daily Average: ${report['cost_summary']['average_daily']:.2f}\n"
    message += f"Last 7 Days: ${report['cost_summary']['last_7_days']:.2f}\n"
    message += f"Trend: {report['cost_summary']['trend']} ({report['cost_summary']['trend_percent']:.1f}%)\n\n"
    
    message += "TOP SERVICES\n"
    message += "-" * 50 + "\n"
    for service in report['service_breakdown']['services'][:5]:
        message += f"{service['service']}: ${service['cost']:.2f} ({service['percentage']:.1f}%)\n"
    message += "\n"
    
    message += "IDLE RESOURCES\n"
    message += "-" * 50 + "\n"
    message += f"Total Idle: {report['idle_resources']['total_idle_resources']}\n"
    message += f"Potential Savings: ${report['idle_resources']['total_savings']:.2f}/month\n\n"
    
    message += "TOP RECOMMENDATIONS\n"
    message += "-" * 50 + "\n"
    for rec in report['recommendations'][:3]:
        message += f"[{rec['priority'].upper()}] {rec['recommendation']}\n"
        message += f"  Potential Savings: ${rec['potential_savings']:.2f}/month\n\n"
    
    message += f"\nFull report available in S3: {S3_BUCKET}/reports/\n"
    
    sns.publish(
        TopicArn=COST_ALERTS_TOPIC,
        Subject=subject,
        Message=message
    )
    
    print("Report notification sent")
