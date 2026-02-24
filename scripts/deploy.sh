#!/bin/bash

set -e

echo "Starting FinOps Automation System Deployment..."

# Check prerequisites
echo "Checking prerequisites..."

if ! command -v aws &> /dev/null; then
    echo "AWS CLI not found. Please install it first."
    exit 1
fi

if ! command -v terraform &> /dev/null; then
    echo "Terraform not found. Please install it first."
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "Python 3 not found. Please install it first."
    exit 1
fi

# Verify AWS credentials
echo "Verifying AWS credentials..."
aws sts get-caller-identity > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "AWS credentials not configured. Run 'aws configure' first."
    exit 1
fi

echo "Prerequisites check passed"

# Check if Cost Explorer is enabled (using current dates)
echo "Checking Cost Explorer API..."

# Get yesterday's date and today's date
YESTERDAY=$(date -u -d "yesterday" +%Y-%m-%d 2>/dev/null || date -u -v-1d +%Y-%m-%d 2>/dev/null)
TODAY=$(date -u +%Y-%m-%d)

aws ce get-cost-and-usage \
    --time-period Start=$YESTERDAY,End=$TODAY \
    --granularity MONTHLY \
    --metrics BlendedCost > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo "Cost Explorer API is not responding!"
    echo "This could mean:"
    echo "1. Cost Explorer is not enabled"
    echo "2. Cost Explorer was just enabled (wait 24 hours for data)"
    echo "3. Insufficient IAM permissions"
    echo ""
    echo "To enable Cost Explorer:"
    echo "1. Go to AWS Cost Management Console"
    echo "2. Click 'Cost Explorer' in the left menu"
    echo "3. Click 'Enable Cost Explorer'"
    echo ""
    read -p "Continue anyway? (yes/no): " continue_deploy
    if [ "$continue_deploy" != "yes" ]; then
        echo "Deployment cancelled"
        exit 1
    fi
else
    echo "Cost Explorer API is accessible"
fi

# Navigate to terraform directory
cd "$(dirname "$0")/../terraform"

# Check if terraform.tfvars exists and has email configured
if [ ! -f "terraform.tfvars" ]; then
    echo "terraform.tfvars not found!"
    exit 1
fi

if grep -q "your-email@example.com" terraform.tfvars; then
    echo "Please update owner_email in terraform.tfvars before deploying"
    exit 1
fi

# Initialize Terraform
echo "Initializing Terraform..."
terraform init

# Validate configuration
echo "Validating Terraform configuration..."
terraform validate
if [ $? -ne 0 ]; then
    echo "Terraform validation failed"
    exit 1
fi

echo "Validation passed"

# Plan deployment
echo "Creating deployment plan..."
terraform plan -out=tfplan

# Confirm deployment
echo "Ready to deploy FinOps Automation System"
echo "This will create:"
echo "  • 4 DynamoDB tables"
echo "  • 6 Lambda functions"
echo "  • 2 SNS topics"
echo "  • 1 S3 bucket"
echo "  • 6 EventBridge rules"
echo "  • 3 SSM parameters"
echo "  • Multiple IAM roles and policies"
echo ""
echo "Estimated monthly cost: ~$5-10 (mostly within free tier)"
echo ""
read -p "Do you want to proceed? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Deployment cancelled"
    exit 0
fi

# Apply deployment
echo "Deploying infrastructure..."
terraform apply tfplan

# Check if deployment was successful
if [ $? -eq 0 ]; then
    echo "Deployment completed successfully!"
    
    # Get outputs
    echo "Fetching deployment outputs..."
    terraform output -json > ../deployment-outputs.json
    
    echo "=================================="
    echo "Deployment Information:"
    echo "=================================="
    
    # Display key information
    terraform output dashboard_info
    
    echo "=================================="
    echo "IMPORTANT NEXT STEPS:"
    echo "1. Check your email and confirm SNS subscriptions (2 emails)"
    echo "2. Test the system:"
    echo "      cd $(dirname "$0")"
    echo "      ./test.sh"
    echo ""
    echo "3. View first scan results (after 5-10 minutes):"
    echo "      aws dynamodb scan --table-name finops-automation-idle-resources --limit 5"
    echo ""
    echo "4. Download reports from S3 (after scans complete):"
    echo "      aws s3 ls s3://\$(cd terraform && terraform output -raw s3_bucket_name)/reports/"
    echo ""
    echo "5. Adjust configuration as needed:"
    echo "      - Budgets: Edit terraform.tfvars"
    echo "      - Thresholds: Edit config/*.json"
    echo "      - Enable cleanup: Set enable_auto_cleanup = true"
    echo ""
    echo "Tip: All cleanup actions run in DRY-RUN mode by default (safe)"
    
else
    echo "Deployment failed"
    exit 1
fi
