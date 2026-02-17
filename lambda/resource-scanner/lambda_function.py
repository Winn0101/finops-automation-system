import json
import boto3
import os
from datetime import datetime, timedelta
from decimal import Decimal

ec2 = boto3.client('ec2')
rds = boto3.client('rds')
elbv2 = boto3.client('elbv2')
elb = boto3.client('elb')
cloudwatch = boto3.client('cloudwatch')
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')

IDLE_RESOURCES_TABLE = os.environ['IDLE_RESOURCES_TABLE']
S3_BUCKET = os.environ['S3_BUCKET']

def lambda_handler(event, context):
    """
    Scans AWS resources for idle/underutilized resources
    """
    print(f"Starting resource scan at {datetime.now()}")
    
    try:
        idle_resources = {
            'ec2_instances': scan_idle_ec2_instances(),
            'ebs_volumes': scan_unattached_ebs_volumes(),
            'elastic_ips': scan_unassociated_elastic_ips(),
            'rds_instances': scan_idle_rds_instances(),
            'load_balancers': scan_unused_load_balancers(),
            'old_snapshots': scan_old_snapshots(),
            'old_amis': scan_old_amis()
        }
        
        # Calculate potential savings
        total_savings = calculate_savings(idle_resources)
        
        # Save results
        save_scan_results(idle_resources, total_savings)
        
        # Summary
        total_idle = sum(len(resources) for resources in idle_resources.values())
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'total_idle_resources': total_idle,
                'potential_monthly_savings': total_savings,
                'breakdown': {k: len(v) for k, v in idle_resources.items()}
            }, default=str)
        }
        
    except Exception as e:
        print(f"Error in resource scan: {str(e)}")
        raise

def scan_idle_ec2_instances():
    """Scan for idle EC2 instances (low CPU utilization)"""
    idle_instances = []
    
    try:
        response = ec2.describe_instances(
            Filters=[
                {'Name': 'instance-state-name', 'Values': ['running']}
            ]
        )
        
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instance_id = instance['InstanceId']
                
                # Skip if has DoNotStop tag
                tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                if 'DoNotStop' in tags or tags.get('Environment') == 'Production':
                    continue
                
                # Check CPU utilization
                cpu_avg = get_cpu_utilization(instance_id, days=7)
                
                if cpu_avg < 5:  # Less than 5% CPU
                    idle_instances.append({
                        'resource_id': instance_id,
                        'resource_type': 'ec2_instance',
                        'instance_type': instance['InstanceType'],
                        'launch_time': instance['LaunchTime'].isoformat(),
                        'cpu_average': cpu_avg,
                        'state': instance['State']['Name'],
                        'tags': tags,
                        'estimated_monthly_cost': estimate_ec2_cost(instance['InstanceType'])
                    })
                    
                    # Save to DynamoDB
                    save_idle_resource(instance_id, 'ec2_instance', {
                        'cpu_average': cpu_avg,
                        'instance_type': instance['InstanceType']
                    })
        
        print(f"Found {len(idle_instances)} idle EC2 instances")
        
    except Exception as e:
        print(f"Error scanning EC2 instances: {str(e)}")
    
    return idle_instances

def scan_unattached_ebs_volumes():
    """Scan for unattached EBS volumes"""
    unattached_volumes = []
    
    try:
        response = ec2.describe_volumes(
            Filters=[
                {'Name': 'status', 'Values': ['available']}
            ]
        )
        
        for volume in response['Volumes']:
            volume_id = volume['VolumeId']
            
            # Skip if has DoNotDelete tag
            tags = {tag['Key']: tag['Value'] for tag in volume.get('Tags', [])}
            if 'DoNotDelete' in tags:
                continue
            
            create_time = volume['CreateTime']
            days_unattached = (datetime.now(create_time.tzinfo) - create_time).days
            
            if days_unattached >= 7:
                unattached_volumes.append({
                    'resource_id': volume_id,
                    'resource_type': 'ebs_volume',
                    'size_gb': volume['Size'],
                    'volume_type': volume['VolumeType'],
                    'create_time': create_time.isoformat(),
                    'days_unattached': days_unattached,
                    'tags': tags,
                    'estimated_monthly_cost': estimate_ebs_cost(volume['Size'], volume['VolumeType'])
                })
                
                save_idle_resource(volume_id, 'ebs_volume', {
                    'size_gb': volume['Size'],
                    'days_unattached': days_unattached
                })
        
        print(f"Found {len(unattached_volumes)} unattached EBS volumes")
        
    except Exception as e:
        print(f"Error scanning EBS volumes: {str(e)}")
    
    return unattached_volumes

def scan_unassociated_elastic_ips():
    """Scan for unassociated Elastic IPs"""
    unassociated_ips = []
    
    try:
        response = ec2.describe_addresses()
        
        for address in response['Addresses']:
            if 'AssociationId' not in address:
                allocation_id = address.get('AllocationId', address.get('PublicIp'))
                
                unassociated_ips.append({
                    'resource_id': allocation_id,
                    'resource_type': 'elastic_ip',
                    'public_ip': address['PublicIp'],
                    'domain': address.get('Domain', 'vpc'),
                    'estimated_monthly_cost': 3.65  # ~$0.005/hour
                })
                
                save_idle_resource(allocation_id, 'elastic_ip', {
                    'public_ip': address['PublicIp']
                })
        
        print(f"Found {len(unassociated_ips)} unassociated Elastic IPs")
        
    except Exception as e:
        print(f"Error scanning Elastic IPs: {str(e)}")
    
    return unassociated_ips

def scan_idle_rds_instances():
    """Scan for idle RDS instances"""
    idle_rds = []
    
    try:
        response = rds.describe_db_instances()
        
        for db_instance in response['DBInstances']:
            db_id = db_instance['DBInstanceIdentifier']
            
            # Check database connections
            connections = get_rds_connections(db_id, days=7)
            
            if connections < 1:  # Less than 1 connection per day on average
                idle_rds.append({
                    'resource_id': db_id,
                    'resource_type': 'rds_instance',
                    'instance_class': db_instance['DBInstanceClass'],
                    'engine': db_instance['Engine'],
                    'create_time': db_instance['InstanceCreateTime'].isoformat(),
                    'connections_average': connections,
                    'estimated_monthly_cost': estimate_rds_cost(db_instance['DBInstanceClass'])
                })
                
                save_idle_resource(db_id, 'rds_instance', {
                    'connections_average': connections,
                    'instance_class': db_instance['DBInstanceClass']
                })
        
        print(f"Found {len(idle_rds)} idle RDS instances")
        
    except Exception as e:
        print(f"Error scanning RDS instances: {str(e)}")
    
    return idle_rds

def scan_unused_load_balancers():
    """Scan for unused load balancers"""
    unused_lbs = []
    
    try:
        # Application/Network Load Balancers (ALB/NLB)
        response = elbv2.describe_load_balancers()
        
        for lb in response['LoadBalancers']:
            lb_arn = lb['LoadBalancerArn']
            lb_name = lb['LoadBalancerName']
            
            # Check target health
            target_groups = elbv2.describe_target_groups(
                LoadBalancerArn=lb_arn
            )
            
            has_healthy_targets = False
            for tg in target_groups['TargetGroups']:
                health = elbv2.describe_target_health(
                    TargetGroupArn=tg['TargetGroupArn']
                )
                if any(t['TargetHealth']['State'] == 'healthy' for t in health['TargetHealthDescriptions']):
                    has_healthy_targets = True
                    break
            
            if not has_healthy_targets:
                unused_lbs.append({
                    'resource_id': lb_arn,
                    'resource_type': 'load_balancer',
                    'name': lb_name,
                    'type': lb['Type'],
                    'scheme': lb['Scheme'],
                    'create_time': lb['CreatedTime'].isoformat(),
                    'estimated_monthly_cost': 16.20 if lb['Type'] == 'application' else 16.20
                })
                
                save_idle_resource(lb_arn, 'load_balancer', {
                    'name': lb_name,
                    'type': lb['Type']
                })
        
        print(f"Found {len(unused_lbs)} unused load balancers")
        
    except Exception as e:
        print(f"Error scanning load balancers: {str(e)}")
    
    return unused_lbs

def scan_old_snapshots():
    """Scan for old EBS snapshots"""
    old_snapshots = []
    
    try:
        response = ec2.describe_snapshots(OwnerIds=['self'])
        
        cutoff_date = datetime.now() - timedelta(days=90)
        
        for snapshot in response['Snapshots']:
            if snapshot['StartTime'] < cutoff_date.replace(tzinfo=snapshot['StartTime'].tzinfo):
                snapshot_id = snapshot['SnapshotId']
                age_days = (datetime.now(snapshot['StartTime'].tzinfo) - snapshot['StartTime']).days
                
                old_snapshots.append({
                    'resource_id': snapshot_id,
                    'resource_type': 'snapshot',
                    'volume_id': snapshot.get('VolumeId', 'N/A'),
                    'size_gb': snapshot['VolumeSize'],
                    'create_time': snapshot['StartTime'].isoformat(),
                    'age_days': age_days,
                    'estimated_monthly_cost': snapshot['VolumeSize'] * 0.05
                })
                
                save_idle_resource(snapshot_id, 'snapshot', {
                    'age_days': age_days,
                    'size_gb': snapshot['VolumeSize']
                })
        
        print(f"Found {len(old_snapshots)} old snapshots")
        
    except Exception as e:
        print(f"Error scanning snapshots: {str(e)}")
    
    return old_snapshots

def scan_old_amis():
    """Scan for old AMIs"""
    old_amis = []
    
    try:
        response = ec2.describe_images(Owners=['self'])
        
        cutoff_date = datetime.now() - timedelta(days=180)
        
        for image in response['Images']:
            # Parse creation date
            create_date = datetime.strptime(image['CreationDate'], '%Y-%m-%dT%H:%M:%S.%fZ')
            
            if create_date < cutoff_date:
                ami_id = image['ImageId']
                age_days = (datetime.now() - create_date).days
                
                old_amis.append({
                    'resource_id': ami_id,
                    'resource_type': 'ami',
                    'name': image.get('Name', 'N/A'),
                    'create_time': image['CreationDate'],
                    'age_days': age_days,
                    'estimated_monthly_cost': 0.05  # Storage cost estimate
                })
                
                save_idle_resource(ami_id, 'ami', {
                    'age_days': age_days,
                    'name': image.get('Name', 'N/A')
                })
        
        print(f"Found {len(old_amis)} old AMIs")
        
    except Exception as e:
        print(f"Error scanning AMIs: {str(e)}")
    
    return old_amis

def get_cpu_utilization(instance_id, days=7):
    """Get average CPU utilization for an instance"""
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        response = cloudwatch.get_metric_statistics(
            Namespace='AWS/EC2',
            MetricName='CPUUtilization',
            Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,  # 1 hour
            Statistics=['Average']
        )
        
        if response['Datapoints']:
            avg = sum(dp['Average'] for dp in response['Datapoints']) / len(response['Datapoints'])
            return round(avg, 2)
        
    except Exception as e:
        print(f"Error getting CPU for {instance_id}: {str(e)}")
    
    return 0

def get_rds_connections(db_id, days=7):
    """Get average database connections"""
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        response = cloudwatch.get_metric_statistics(
            Namespace='AWS/RDS',
            MetricName='DatabaseConnections',
            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=['Average']
        )
        
        if response['Datapoints']:
            avg = sum(dp['Average'] for dp in response['Datapoints']) / len(response['Datapoints'])
            return round(avg, 2)
        
    except Exception as e:
        print(f"Error getting connections for {db_id}: {str(e)}")
    
    return 0

def estimate_ec2_cost(instance_type):
    """Estimate monthly EC2 cost"""
    pricing = {
        't2.micro': 8.47,
        't2.small': 16.93,
        't2.medium': 33.87,
        't3.micro': 7.59,
        't3.small': 15.18,
        't3.medium': 30.37
    }
    return pricing.get(instance_type, 50)

def estimate_ebs_cost(size_gb, volume_type):
    """Estimate monthly EBS cost"""
    pricing = {
        'gp2': 0.10,
        'gp3': 0.08,
        'io1': 0.125,
        'io2': 0.125,
        'st1': 0.045,
        'sc1': 0.015
    }
    price_per_gb = pricing.get(volume_type, 0.10)
    return round(size_gb * price_per_gb, 2)

def estimate_rds_cost(instance_class):
    """Estimate monthly RDS cost"""
    pricing = {
        'db.t2.micro': 14.60,
        'db.t2.small': 29.20,
        'db.t3.micro': 13.14,
        'db.t3.small': 26.28
    }
    return pricing.get(instance_class, 50)

def calculate_savings(idle_resources):
    """Calculate total potential monthly savings"""
    total = 0
    
    for resource_type, resources in idle_resources.items():
        for resource in resources:
            total += resource.get('estimated_monthly_cost', 0)
    
    return round(total, 2)

def save_idle_resource(resource_id, resource_type, metadata):
    """Save idle resource to DynamoDB"""
    table = dynamodb.Table(IDLE_RESOURCES_TABLE)
    
    scan_date = datetime.now().strftime('%Y-%m-%d')
    ttl = int((datetime.now() + timedelta(days=30)).timestamp())
    
    table.put_item(
        Item={
            'resource_id': resource_id,
            'scan_date': scan_date,
            'resource_type': resource_type,
            'metadata': metadata,
            'scanned_at': datetime.now().isoformat(),
            'ttl': ttl
        }
    )

def save_scan_results(idle_resources, total_savings):
    """Save scan results to S3"""
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    
    results = {
        'timestamp': timestamp,
        'idle_resources': idle_resources,
        'total_savings': total_savings,
        'scan_date': datetime.now().isoformat()
    }
    
    key = f"scans/resource-scan-{timestamp}.json"
    
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(results, indent=2, default=str),
        ContentType='application/json'
    )
    
    print(f"Scan results saved to s3://{S3_BUCKET}/{key}")
