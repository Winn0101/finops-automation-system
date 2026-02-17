# FinOps Automation & Cloud Cost Optimization System

A comprehensive AWS FinOps automation platform that detects waste, enforces policies, and optimizes cloud costs automatically.

##  Features

- **Automated Cost Analysis**: Daily analysis with anomaly detection
- **Idle Resource Detection**: Identifies EC2, RDS, EBS, ELB, and more
- **Tagging Policy Enforcement**: Ensures compliance with tagging standards
- **Automated Cleanup**: Optional cleanup of idle resources (with dry-run mode)
- **Budget Monitoring**: Alerts when spending exceeds thresholds
- **Weekly Reports**: Comprehensive HTML, JSON, and CSV reports
- **Email & Slack Notifications**: Real-time alerts for cost anomalies

##  Cost Estimate

**Monthly Cost**: ~$5-10 (mostly within AWS Free Tier)

- Lambda: Free tier (1M requests/month)
- DynamoDB: Free tier (25GB storage)
- S3: <$1
- CloudWatch: Free tier (10 metrics)
- SNS: <$1
- EventBridge: Free

## 📋 Prerequisites

- AWS Account with Cost Explorer enabled
- AWS CLI configured
- Terraform >= 1.0
- Python 3.9+

##  Quick Start

### 1. Enable Cost Explorer

**IMPORTANT**: Must be done 24 hours before deployment
```bash
# Enable in AWS Console:
# AWS Cost Management → Cost Explorer → Enable Cost Explorer
```

### 2. Clone and Configure
```bash
cd ~/finops-automation-system

# Update configuration
nano terraform/terraform.tfvars
# Change: owner_email = "your-email@example.com"
```

### 3. Deploy
```bash
./scripts/deploy.sh
```

### 4. Confirm SNS Subscriptions

Check your email and confirm both SNS subscription links.

### 5. Test the System
```bash
./scripts/test.sh
```

##  What Gets Created

### Lambda Functions (6)
- **cost-analyzer**: Analyzes costs and detects anomalies
- **resource-scanner**: Scans for idle/underutilized resources
- **tag-enforcer**: Enforces tagging policies
- **cleanup-executor**: Executes cleanup actions
- **budget-monitor**: Monitors spending against budgets
- **report-generator**: Generates comprehensive reports

### DynamoDB Tables (4)
- **cost-anomalies**: Tracks detected cost anomalies
- **idle-resources**: Catalog of idle resources
- **tag-compliance**: Tag compliance records
- **cleanup-actions**: Cleanup action history

### Scheduled Jobs
- Cost Analysis: Daily at 3 AM UTC
- Resource Scan: Daily at 2 AM UTC
- Tag Enforcement: Daily at 4 AM UTC
- Budget Monitor: Every 6 hours
- Weekly Report: Monday at 9 AM UTC

##  Configuration

### Cost Rules (`config/cost-rules.json`)
```json
{
  "anomaly_detection": {
    "threshold_percentage": 25,
    "lookback_days": 30
  },
  "idle_resource_rules": {
    "ec2": {
      "cpu_threshold": 5,
      "observation_days": 7
    }
  }
}
```

### Tag Policies (`config/tag-policies.json`)

Required tags:
- `Environment`: Production, Staging, Development, Testing
- `Owner`: Email address
- `CostCenter`: Cost center code
- `Project`: Project name (warning only)

### Cleanup Policies (`config/cleanup-policies.json`)

Configures cleanup behavior for each resource type.

##  Viewing Results

### S3 Reports
```bash
# List reports
aws s3 ls s3://$(terraform output -raw s3_bucket_name)/reports/

# Download latest HTML report
aws s3 cp s3://$(terraform output -raw s3_bucket_name)/reports/ ./reports/ --recursive --exclude "*" --include "*.html"
```

### DynamoDB Data
```bash
# View idle resources
aws dynamodb scan --table-name finops-automation-idle-resources

# View cost anomalies
aws dynamodb scan --table-name finops-automation-cost-anomalies

# View tag compliance
aws dynamodb scan --table-name finops-automation-tag-compliance
```

### CloudWatch Logs
```bash
# Cost Analyzer logs
aws logs tail /aws/lambda/finops-automation-cost-analyzer --follow

# Resource Scanner logs
aws logs tail /aws/lambda/finops-automation-resource-scanner --follow
```

##  Safety Features

### Dry Run Mode

By default, cleanup runs in **DRY RUN** mode - no actual deletions occur.

To enable live cleanup:
1. Edit `terraform.tfvars`: `cleanup_dry_run = false`
2. Edit `terraform.tfvars`: `enable_auto_cleanup = true`
3. Run `terraform apply`

### Exclude Tags

Protect resources from cleanup by adding tags:
- `DoNotStop`: Prevents EC2 stop/terminate
- `DoNotDelete`: Prevents resource deletion
- `Environment: Production`: Excluded from idle detection

##  Notifications

### Email Alerts

You'll receive emails for:
- Cost anomalies (>25% deviation)
- Budget threshold breaches (80%, 100%)
- Tag compliance violations
- Weekly cost reports
- Cleanup actions (when enabled)

### Slack Integration (Optional)
```bash
# Add Slack webhook URL
nano terraform/terraform.tfvars
# Add: slack_webhook_url = "https://hooks.slack.com/..."

terraform apply
```

##  Manual Triggers

### Run Cost Analysis
```bash
aws lambda invoke \
    --function-name finops-automation-cost-analyzer \
    /tmp/output.json && cat /tmp/output.json | jq
```

### Run Resource Scan
```bash
aws lambda invoke \
    --function-name finops-automation-resource-scanner \
    /tmp/output.json && cat /tmp/output.json | jq
```

### Generate Report
```bash
aws lambda invoke \
    --function-name finops-automation-report-generator \
    /tmp/output.json && cat /tmp/output.json | jq
```

##  Customization

### Adjust Budgets
```hcl
# terraform.tfvars
daily_budget_usd   = 15
monthly_budget_usd = 200
```

### Change Schedules
```hcl
# terraform.tfvars
scan_schedule   = "cron(0 1 * * ? *)"  # 1 AM daily
report_schedule = "cron(0 8 * * 1 *)"  # Monday 8 AM
```

### Modify Detection Thresholds

Edit `config/cost-rules.json`:
```json
{
  "idle_resource_rules": {
    "ec2": {
      "cpu_threshold": 10,
      "observation_days": 14
    }
  }
}
```

Then update SSM:
```bash
aws ssm put-parameter \
    --name /finops-automation/config/cost-rules \
    --value file://config/cost-rules.json \
    --type String \
    --overwrite
```

##  Testing
```bash
# Run all tests
./scripts/test.sh

# Test individual Lambda
aws lambda invoke \
    --function-name finops-automation-cost-analyzer \
    --payload '{}' \
    /tmp/test.json
```

##  Cleanup
```bash
./scripts/cleanup.sh
# Type 'destroy' to confirm
```

##  Example Reports

After deployment, you'll receive:

### Weekly Email Report
```
AWS FinOps Weekly Report

COST SUMMARY
Total Spend: $47.23
Daily Average: $1.57
Trend: decreasing (-12.3%)

TOP SERVICES
EC2: $23.45 (49.6%)
RDS: $15.20 (32.2%)
S3: $5.12 (10.8%)

IDLE RESOURCES
Total: 5 resources
Potential Savings: $28.50/month

RECOMMENDATIONS
[HIGH] Clean up 5 idle resources
  Potential Savings: $28.50/month
```

### HTML Dashboard

Beautiful HTML report with:
- Cost trends and charts
- Service breakdown
- Idle resource details
- Actionable recommendations

## 🔧 Troubleshooting

### Cost Explorer Not Enabled

**Error**: `AccessDeniedException: Cost Explorer is not enabled`

**Fix**: Enable in AWS Console, wait 24 hours

### Lambda Timeout

**Error**: Lambda timeout errors

**Fix**: Increase timeout in `terraform/lambda.tf`:
```hcl
timeout = 900  # 15 minutes
```

### No Idle Resources Found

**Reason**: Your resources are being used efficiently!

Or:
- Check CloudWatch metrics are being collected
- Verify instances have been running for >7 days
- Review thresholds in `config/cost-rules.json`

### Email Not Received

1. Check spam folder
2. Verify SNS subscription confirmed
3. Check SNS topic subscriptions:
```bash
aws sns list-subscriptions-by-topic \
    --topic-arn $(terraform output -raw cost_alerts_topic_arn)
```

##  Architecture
```
EventBridge Rules (Schedules)
    ↓
Lambda Functions
    ↓
AWS APIs (Cost Explorer, EC2, RDS, etc.)
    ↓
DynamoDB (Data Storage)
    ↓
S3 (Reports)
    ↓
SNS (Notifications)
```

##  Development

### Adding New Resource Types

1. Edit `lambda/resource-scanner/lambda_function.py`
2. Add new `scan_*` function
3. Update `lambda_handler` to call new function
4. Update `config/cost-rules.json` with new rules
5. Deploy: `terraform apply`

### Custom Notification Channels

Add notification logic to Lambda functions:
- Slack: Use webhook in environment variable
- PagerDuty: Add PD integration
- Microsoft Teams: Add Teams webhook

##  Contributing

This is a personal project template. Feel free to:
- Fork and customize
- Add new features
- Share improvements

##  License

MIT License - Use freely for personal or commercial projects

##  Credits

Built as part of AWS infrastructure learning project.

##  Support

For issues or questions:
1. Check CloudWatch logs
2. Review DynamoDB tables
3. Verify IAM permissions
4. Check AWS service quotas

##  Learning Resources

- [AWS Cost Explorer API](https://docs.aws.amazon.com/cost-management/latest/APIReference/Welcome.html)
- [FinOps Foundation](https://www.finops.org/)
- [AWS Well-Architected Framework - Cost Optimization](https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/welcome.html)

---

**Happy Cost Optimizing! 💰**
