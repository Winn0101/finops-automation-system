import json
import boto3
import os
from datetime import datetime, timedelta
from decimal import Decimal
import re

ec2 = boto3.client('ec2')
rds = boto3.client('rds')
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')
ssm = boto3.client('ssm')

TAG_COMPLIANCE_TABLE = os.environ['TAG_COMPLIANCE_TABLE']
CLEANUP_NOTIFICATIONS_TOPIC = os.environ['CLEANUP_NOTIFICATIONS_TOPIC']

def lambda_handler(event, context):
    """
    Enforces tagging policies across AWS resources
    """
    print(f"Starting tag enforcement at {datetime.now()}")
    
    try:
        # Load tag policies
        policies = load_tag_policies()
        
        # Scan resources
        compliance_results = {
            'ec2_instances': check_ec2_tags(policies),
            'ebs_volumes': check_ebs_tags(policies),
            'rds_instances': check_rds_tags(policies),
            's3_buckets': check_s3_tags(policies)
        }
        
        # Calculate compliance rate
        total_resources = sum(len(r['resources']) for r in compliance_results.values())
        compliant_resources = sum(len([res for res in r['resources'] if res['compliant']]) for r in compliance_results.values())
        compliance_rate = (compliant_resources / total_resources * 100) if total_resources > 0 else 100
        
        # Send notifications for non-compliant resources
        non_compliant = [
            res for result in compliance_results.values()
            for res in result['resources'] if not res['compliant']
        ]
        
        if non_compliant:
            send_compliance_notifications(non_compliant, policies)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'total_resources': total_resources,
                'compliant_resources': compliant_resources,
                'compliance_rate': round(compliance_rate, 2),
                'non_compliant_count': len(non_compliant)
            })
        }
        
    except Exception as e:
        print(f"Error in tag enforcement: {str(e)}")
        raise

def load_tag_policies():
    """Load tag policies from SSM Parameter Store"""
    try:
        response = ssm.get_parameter(
            Name='/finops-automation/config/tag-policies'
        )
        return json.loads(response['Parameter']['Value'])
    except Exception as e:
        print(f"Error loading tag policies: {str(e)}")
        # Return default policies
        return {
            'required_tags': [
                {'key': 'Environment', 'values': ['Production', 'Staging', 'Development'], 'enforcement': 'strict'},
                {'key': 'Owner', 'values': [], 'enforcement': 'strict'},
                {'key': 'CostCenter', 'values': [], 'enforcement': 'strict'}
            ]
        }

def check_ec2_tags(policies):
    """Check EC2 instance tag compliance"""
    results = {'resources': []}
    
    try:
        response = ec2.describe_instances()
        
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instance_id = instance['InstanceId']
                tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                
                compliance = check_resource_compliance(tags, policies['required_tags'])
                
                results['resources'].append({
                    'resource_id': instance_id,
                    'resource_type': 'ec2_instance',
                    'resource_arn': f"arn:aws:ec2:{boto3.session.Session().region_name}::instance/{instance_id}",
                    'tags': tags,
                    'compliant': compliance['compliant'],
                    'missing_tags': compliance['missing_tags'],
                    'invalid_tags': compliance['invalid_tags']
                })
                
                # Save to DynamoDB
                save_compliance_record(instance_id, 'ec2_instance', compliance)
        
    except Exception as e:
        print(f"Error checking EC2 tags: {str(e)}")
    
    return results

def check_ebs_tags(policies):
    """Check EBS volume tag compliance"""
    results = {'resources': []}
    
    try:
        response = ec2.describe_volumes()
        
        for volume in response['Volumes']:
            volume_id = volume['VolumeId']
            tags = {tag['Key']: tag['Value'] for tag in volume.get('Tags', [])}
            
            compliance = check_resource_compliance(tags, policies['required_tags'])
            
            results['resources'].append({
                'resource_id': volume_id,
                'resource_type': 'ebs_volume',
                'resource_arn': f"arn:aws:ec2:{boto3.session.Session().region_name}::volume/{volume_id}",
                'tags': tags,
                'compliant': compliance['compliant'],
                'missing_tags': compliance['missing_tags'],
                'invalid_tags': compliance['invalid_tags']
            })
            
            save_compliance_record(volume_id, 'ebs_volume', compliance)
        
    except Exception as e:
        print(f"Error checking EBS tags: {str(e)}")
    
    return results

def check_rds_tags(policies):
    """Check RDS instance tag compliance"""
    results = {'resources': []}
    
    try:
        response = rds.describe_db_instances()
        
        for db_instance in response['DBInstances']:
            db_arn = db_instance['DBInstanceArn']
            
            # Get tags
            tags_response = rds.list_tags_for_resource(ResourceName=db_arn)
            tags = {tag['Key']: tag['Value'] for tag in tags_response['TagList']}
            
            compliance = check_resource_compliance(tags, policies['required_tags'])
            
            results['resources'].append({
                'resource_id': db_instance['DBInstanceIdentifier'],
                'resource_type': 'rds_instance',
                'resource_arn': db_arn,
                'tags': tags,
                'compliant': compliance['compliant'],
                'missing_tags': compliance['missing_tags'],
                'invalid_tags': compliance['invalid_tags']
            })
            
            save_compliance_record(db_instance['DBInstanceIdentifier'], 'rds_instance', compliance)
        
    except Exception as e:
        print(f"Error checking RDS tags: {str(e)}")
    
    return results

def check_s3_tags(policies):
    """Check S3 bucket tag compliance"""
    results = {'resources': []}
    
    try:
        response = s3_client.list_buckets()
        
        for bucket in response['Buckets']:
            bucket_name = bucket['Name']
            
            try:
                tags_response = s3_client.get_bucket_tagging(Bucket=bucket_830)
                tags = {tag['Key']: tag['Value'] for tag in tags_response['TagSet']}
            except:
                tags = {}
            
            compliance = check_resource_compliance(tags, policies['required_tags'])
            
            results['resources'].append({
                'resource_id': bucket_name,
                'resource_type': 's3_bucket',
                'resource_arn': f"arn:aws:s3:::{bucket_name}",
                'tags': tags,
                'compliant': compliance['compliant'],
                'missing_tags': compliance['missing_tags'],
                'invalid_tags': compliance['invalid_tags']
            })
            
            save_compliance_record(bucket_name, 's3_bucket', compliance)
        
    except Exception as e:
        print(f"Error checking S3 tags: {str(e)}")
    
    return results

def check_resource_compliance(tags, required_tags):
    """Check if resource tags comply with policies"""
    missing_tags = []
    invalid_tags = []
    
    for required_tag in required_tags:
        tag_key = required_tag['key']
        
        if tag_key not in tags:
            missing_tags.append(tag_key)
            continue
        
        tag_value = tags[tag_key]
        
        # Check allowed values
        if required_tag['values'] and tag_value not in required_tag['values']:
            invalid_tags.append({
                'key': tag_key,
                'value': tag_value,
                'allowed_values': required_tag['values']
            })
        
        # Check pattern if specified
        if 'pattern' in required_tag:
            if not re.match(required_tag['pattern'], tag_value):
                invalid_tags.append({
                    'key': tag_key,
                    'value': tag_value,
                    'pattern': required_tag['pattern']
                })
    
    return {
        'compliant': len(missing_tags) == 0 and len(invalid_tags) == 0,
        'missing_tags': missing_tags,
        'invalid_tags': invalid_tags
    }

def save_compliance_record(resource_id, resource_type, compliance):
    """Save compliance record to DynamoDB"""
    table = dynamodb.Table(TAG_COMPLIANCE_TABLE)
    
    scan_date = datetime.now().strftime('%Y-%m-%d')
    ttl = int((datetime.now() + timedelta(days=90)).timestamp())
    
    table.put_item(
        Item={
            'resource_arn': f"{resource_type}:{resource_id}",
            'scan_date': scan_date,
            'resource_type': resource_type,
            'compliance_status': 'compliant' if compliance['compliant'] else 'non_compliant',
            'missing_tags': compliance['missing_tags'],
            'invalid_tags': compliance.get('invalid_tags', []),
            'scanned_at': datetime.now().isoformat(),
            'ttl': ttl
        }
    )

def send_compliance_notifications(non_compliant_resources, policies):
    """Send notifications for non-compliant resources"""
    if not non_compliant_resources:
        return
    
    subject = f"AWS Tag Compliance Alert: {len(non_compliant_resources)} non-compliant resources"
    
    message = "AWS Tag Compliance Report\n\n"
    message += f"Found {len(non_compliant_resources)} resources not compliant with tagging policies.\n\n"
    
    # Group by resource type
    by_type = {}
    for resource in non_compliant_resources:
        rtype = resource['resource_type']
        if rtype not in by_type:
            by_type[rtype] = []
        by_type[rtype].append(resource)
    
    for rtype, resources in by_type.items():
        message += f"\n{rtype.upper()} ({len(resources)} resources):\n"
        message += "-" * 50 + "\n"
        
        for resource in resources[:5]:  # Limit to 5 per type
            message += f"Resource: {resource['resource_id']}\n"
            if resource['missing_tags']:
                message += f"  Missing tags: {', '.join(resource['missing_tags'])}\n"
            if resource.get('invalid_tags'):
                message += f"  Invalid tags: {len(resource['invalid_tags'])}\n"
            message += "\n"
        
        if len(resources) > 5:
            message += f"... and {len(resources) - 5} more\n\n"
    
    message += "\nPlease add the required tags to these resources within 7 days.\n"
    
    sns.publish(
        TopicArn=CLEANUP_NOTIFICATIONS_TOPIC,
        Subject=subject,
        Message=message
    )
    
    print(f"Compliance notification sent for {len(non_compliant_resources)} resources")
