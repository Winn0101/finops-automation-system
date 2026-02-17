import json
import boto3
import os
from datetime import datetime, timedelta
from decimal import Decimal

ec2 = boto3.client('ec2')
rds = boto3.client('rds')
elbv2 = boto3.client('elbv2')
dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')
ssm = boto3.client('ssm')

CLEANUP_ACTIONS_TABLE = os.environ['CLEANUP_ACTIONS_TABLE']
CLEANUP_NOTIFICATIONS_TOPIC = os.environ['CLEANUP_NOTIFICATIONS_TOPIC']
DRY_RUN = os.environ.get('DRY_RUN', 'true').lower() == 'true'

def lambda_handler(event, context):
    """
    Executes cleanup actions on idle resources
    """
    print(f"Starting cleanup execution at {datetime.now()} (DRY_RUN: {DRY_RUN})")
    
    try:
        # Load cleanup policies
        policies = load_cleanup_policies()
        
        # Get pending cleanup actions
        pending_actions = get_pending_cleanup_actions()
        
        # Execute cleanup actions
        results = {
            'executed': [],
            'failed': [],
            'skipped': []
        }
        
        for action in pending_actions:
            result = execute_cleanup_action(action, policies)
            
            if result['success']:
                results['executed'].append(result)
            elif result['skipped']:
                results['skipped'].append(result)
            else:
                results['failed'].append(result)
        
        # Send summary notification
        if results['executed'] or results['failed']:
            send_cleanup_summary(results)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'dry_run': DRY_RUN,
                'executed': len(results['executed']),
                'failed': len(results['failed']),
                'skipped': len(results['skipped'])
            })
        }
        
    except Exception as e:
        print(f"Error in cleanup execution: {str(e)}")
        raise

def load_cleanup_policies():
    """Load cleanup policies from SSM"""
    try:
        response = ssm.get_parameter(
            Name='/finops-automation/config/cleanup-policies'
        )
        return json.loads(response['Parameter']['Value'])
    except Exception as e:
        print(f"Error loading cleanup policies: {str(e)}")
        return {'cleanup_rules': {}, 'dry_run': True}

def get_pending_cleanup_actions():
    """Get pending cleanup actions from DynamoDB"""
    table = dynamodb.Table(CLEANUP_ACTIONS_TABLE)
    
    try:
        response = table.query(
            IndexName='StatusIndex',
            KeyConditionExpression='#status = :status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': 'pending'}
        )
        
        return response['Items']
    except Exception as e:
        print(f"Error getting pending actions: {str(e)}")
        return []

def execute_cleanup_action(action, policies):
    """Execute a cleanup action"""
    resource_id = action['resource_id']
    resource_type = action['resource_type']
    action_type = action['action_type']
    
    print(f"Processing: {resource_type} {resource_id} - {action_type}")
    
    result = {
        'action_id': action['action_id'],
        'resource_id': resource_id,
        'resource_type': resource_type,
        'action_type': action_type,
        'success': False,
        'skipped': False,
        'message': '',
        'savings': action.get('estimated_savings', 0)
    }
    
    try:
        if resource_type == 'ec2_instance':
            if action_type == 'stop':
                result = stop_ec2_instance(resource_id, result)
            elif action_type == 'terminate':
                result = terminate_ec2_instance(resource_id, result)
        
        elif resource_type == 'ebs_volume':
            if action_type == 'snapshot_and_delete':
                result = snapshot_and_delete_volume(resource_id, result)
            elif action_type == 'delete':
                result = delete_volume(resource_id, result)
        
        elif resource_type == 'elastic_ip':
            if action_type == 'release':
                result = release_elastic_ip(resource_id, result)
        
        elif resource_type == 'snapshot':
            if action_type == 'delete':
                result = delete_snapshot(resource_id, result)
        
        elif resource_type == 'ami':
            if action_type == 'deregister':
                result = deregister_ami(resource_id, result)
        
        elif resource_type == 'load_balancer':
            if action_type == 'delete':
                result = delete_load_balancer(resource_id, result)
        
        else:
            result['skipped'] = True
            result['message'] = f"Unsupported resource type: {resource_type}"
        
        # Update action status in DynamoDB
        update_action_status(action['action_id'], result)
        
    except Exception as e:
        result['message'] = str(e)
        print(f"Error executing action: {str(e)}")
    
    return result

def stop_ec2_instance(instance_id, result):
    """Stop an EC2 instance"""
    if DRY_RUN:
        result['success'] = True
        result['message'] = f"[DRY RUN] Would stop instance {instance_id}"
        print(result['message'])
    else:
        try:
            ec2.stop_instances(InstanceIds=[instance_id])
            result['success'] = True
            result['message'] = f"Successfully stopped instance {instance_id}"
            print(result['message'])
        except Exception as e:
            result['message'] = f"Failed to stop instance: {str(e)}"
    
    return result

def terminate_ec2_instance(instance_id, result):
    """Terminate an EC2 instance"""
    if DRY_RUN:
        result['success'] = True
        result['message'] = f"[DRY RUN] Would terminate instance {instance_id}"
        print(result['message'])
    else:
        try:
            # Create snapshot first
            response = ec2.describe_instances(InstanceIds=[instance_id])
            instance = response['Reservations'][0]['Instances'][0]
            
            for bdm in instance.get('BlockDeviceMappings', []):
                if 'Ebs' in bdm:
                    volume_id = bdm['Ebs']['VolumeId']
                    ec2.create_snapshot(
                        VolumeId=volume_id,
                        Description=f"Pre-termination snapshot of {instance_id}"
                    )
            
            # Terminate
            ec2.terminate_instances(InstanceIds=[instance_id])
            result['success'] = True
            result['message'] = f"Successfully terminated instance {instance_id}"
            print(result['message'])
        except Exception as e:
            result['message'] = f"Failed to terminate instance: {str(e)}"
    
    return result

def snapshot_and_delete_volume(volume_id, result):
    """Create snapshot and delete EBS volume"""
    if DRY_RUN:
        result['success'] = True
        result['message'] = f"[DRY RUN] Would snapshot and delete volume {volume_id}"
        print(result['message'])
    else:
        try:
            # Create snapshot
            snapshot_response = ec2.create_snapshot(
                VolumeId=volume_id,
                Description=f"Pre-deletion snapshot of {volume_id}"
            )
            snapshot_id = snapshot_response['SnapshotId']
            
            # Wait for snapshot to complete
            waiter = ec2.get_waiter('snapshot_completed')
            waiter.wait(SnapshotIds=[snapshot_id])
            
            # Delete volume
            ec2.delete_volume(VolumeId=volume_id)
            
            result['success'] = True
            result['message'] = f"Snapshotted ({snapshot_id}) and deleted volume {volume_id}"
            print(result['message'])
        except Exception as e:
            result['message'] = f"Failed to snapshot/delete volume: {str(e)}"
    
    return result

def delete_volume(volume_id, result):
    """Delete EBS volume"""
    if DRY_RUN:
        result['success'] = True
        result['message'] = f"[DRY RUN] Would delete volume {volume_id}"
        print(result['message'])
    else:
        try:
            ec2.delete_volume(VolumeId=volume_id)
            result['success'] = True
            result['message'] = f"Successfully deleted volume {volume_id}"
            print(result['message'])
        except Exception as e:
            result['message'] = f"Failed to delete volume: {str(e)}"
    
    return result

def release_elastic_ip(allocation_id, result):
    """Release Elastic IP"""
    if DRY_RUN:
        result['success'] = True
        result['message'] = f"[DRY RUN] Would release Elastic IP {allocation_id}"
        print(result['message'])
    else:
        try:
            ec2.release_address(AllocationId=allocation_id)
            result['success'] = True
            result['message'] = f"Successfully released Elastic IP {allocation_id}"
            print(result['message'])
        except Exception as e:
            result['message'] = f"Failed to release Elastic IP: {str(e)}"
    
    return result

def delete_snapshot(snapshot_id, result):
    """Delete EBS snapshot"""
    if DRY_RUN:
        result['success'] = True
        result['message'] = f"[DRY RUN] Would delete snapshot {snapshot_id}"
        print(result['message'])
    else:
        try:
            ec2.delete_snapshot(SnapshotId=snapshot_id)
            result['success'] = True
            result['message'] = f"Successfully deleted snapshot {snapshot_id}"
            print(result['message'])
        except Exception as e:
            result['message'] = f"Failed to delete snapshot: {str(e)}"
    
    return result

def deregister_ami(ami_id, result):
    """Deregister AMI"""
    if DRY_RUN:
        result['success'] = True
        result['message'] = f"[DRY RUN] Would deregister AMI {ami_id}"
        print(result['message'])
    else:
        try:
            ec2.deregister_image(ImageId=ami_id)
            result['success'] = True
            result['message'] = f"Successfully deregistered AMI {ami_id}"
            print(result['message'])
        except Exception as e:
            result['message'] = f"Failed to deregister AMI: {str(e)}"
    
    return result

def delete_load_balancer(lb_arn, result):
    """Delete load balancer"""
    if DRY_RUN:
        result['success'] = True
        result['message'] = f"[DRY RUN] Would delete load balancer {lb_arn}"
        print(result['message'])
    else:
        try:
            elbv2.delete_load_balancer(LoadBalancerArn=lb_arn)
            result['success'] = True
            result['message'] = f"Successfully deleted load balancer {lb_arn}"
            print(result['message'])
        except Exception as e:
            result['message'] = f"Failed to delete load balancer: {str(e)}"
    
    return result

def update_action_status(action_id, result):
    """Update cleanup action status in DynamoDB"""
    table = dynamodb.Table(CLEANUP_ACTIONS_TABLE)
    
    status = 'completed' if result['success'] else 'failed'
    if result.get('skipped'):
        status = 'skipped'
    
    # Parse action_id to get scheduled_date
    parts = action_id.split('-')
    scheduled_date = '-'.join(parts[:3])  # YYYY-MM-DD
    
    table.update_item(
        Key={
            'action_id': action_id,
            'scheduled_date': scheduled_date
        },
        UpdateExpression='SET #status = :status, executed_at = :executed, result_message = :message',
        ExpressionAttributeNames={'#status': 'status'},
        ExpressionAttributeValues={
            ':status': status,
            ':executed': datetime.now().isoformat(),
            ':message': result['message']
        }
    )

def send_cleanup_summary(results):
    """Send cleanup summary notification"""
    subject = f"🧹 Cleanup Summary: {len(results['executed'])} actions executed"
    
    message = "AWS Resource Cleanup Summary\n\n"
    message += f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n\n"
    
    if results['executed']:
        message += f"Successfully Executed ({len(results['executed'])}):\n"
        message += "-" * 50 + "\n"
        total_savings = 0
        for result in results['executed']:
            message += f"✓ {result['resource_type']}: {result['resource_id']}\n"
            message += f"  Action: {result['action_type']}\n"
            message += f"  Savings: ${result.get('savings', 0)}/month\n\n"
            total_savings += result.get('savings', 0)
        message += f"Total Monthly Savings: ${total_savings:.2f}\n\n"
    
    if results['failed']:
        message += f"Failed ({len(results['failed'])}):\n"
        message += "-" * 50 + "\n"
        for result in results['failed']:
            message += f"✗ {result['resource_type']}: {result['resource_id']}\n"
            message += f"  Error: {result['message']}\n\n"
    
    if results['skipped']:
        message += f"Skipped ({len(results['skipped'])}):\n"
        message += "-" * 50 + "\n"
        for result in results['skipped']:
            message += f"○ {result['resource_type']}: {result['resource_id']}\n"
            message += f"  Reason: {result['message']}\n\n"
    
    sns.publish(
        TopicArn=CLEANUP_NOTIFICATIONS_TOPIC,
        Subject=subject,
        Message=message
    )
    
    print(f"Cleanup summary sent")
