#!/bin/bash

set -e

echo " Starting FinOps Automation System Deployment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v aws &> /dev/null; then
    echo -e "${RED}AWS CLI not found. Please install it first.${NC}"
    exit 1
fi

if ! command -v terraform &> /dev/null; then
    echo -e "${RED}Terraform not found. Please install it first.${NC}"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 not found. Please install it first.${NC}"
    exit 1
fi

# Verify AWS credentials
echo -e "${YELLOW}Verifying AWS credentials...${NC}"
aws sts get-caller-identity > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo -e "${RED}AWS credentials not configured. Run 'aws configure' first.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Prerequisites check passed${NC}"

# Check if Cost Explorer is enabled (using current dates)
echo -e "${YELLOW}Checking Cost Explorer API...${NC}"

# Get yesterday's date and today's date
YESTERDAY=$(date -u -d "yesterday" +%Y-%m-%d 2>/dev/null || date -u -v-1d +%Y-%m-%d 2>/dev/null)
TODAY=$(date -u +%Y-%m-%d)

aws ce get-cost-and-usage \
    --time-period Start=$YESTERDAY,End=$TODAY \
    --granularity MONTHLY \
    --metrics BlendedCost > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo -e "${RED}⚠️  Cost Explorer API is not responding!${NC}"
    echo -e "${YELLOW}This could mean:${NC}"
    echo "1. Cost Explorer is not enabled"
    echo "2. Cost Explorer was just enabled (wait 24 hours for data)"
    echo "3. Insufficient IAM permissions"
    echo ""
    echo -e "${YELLOW}To enable Cost Explorer:${NC}"
    echo "1. Go to AWS Cost Management Console"
    echo "2. Click 'Cost Explorer' in the left menu"
    echo "3. Click 'Enable Cost Explorer'"
    echo ""
    read -p "Continue anyway? (yes/no): " continue_deploy
    if [ "$continue_deploy" != "yes" ]; then
        echo -e "${RED}Deployment cancelled${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ Cost Explorer API is accessible${NC}"
fi

# Navigate to terraform directory
cd "$(dirname "$0")/../terraform"

# Check if terraform.tfvars exists and has email configured
if [ ! -f "terraform.tfvars" ]; then
    echo -e "${RED}terraform.tfvars not found!${NC}"
    exit 1
fi

if grep -q "your-email@example.com" terraform.tfvars; then
    echo -e "${RED}Please update owner_email in terraform.tfvars before deploying${NC}"
    exit 1
fi

# Initialize Terraform
echo -e "${YELLOW}Initializing Terraform...${NC}"
terraform init

# Validate configuration
echo -e "${YELLOW}Validating Terraform configuration...${NC}"
terraform validate
if [ $? -ne 0 ]; then
    echo -e "${RED}Terraform validation failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Validation passed${NC}"

# Plan deployment
echo -e "${YELLOW}Creating deployment plan...${NC}"
terraform plan -out=tfplan

# Confirm deployment
echo -e "${YELLOW}Ready to deploy FinOps Automation System${NC}"
echo -e "${BLUE}This will create:${NC}"
echo "  • 4 DynamoDB tables"
echo "  • 6 Lambda functions"
echo "  • 2 SNS topics"
echo "  • 1 S3 bucket"
echo "  • 6 EventBridge rules"
echo "  • 3 SSM parameters"
echo "  • Multiple IAM roles and policies"
echo ""
echo -e "${YELLOW}Estimated monthly cost: ~\$5-10 (mostly within free tier)${NC}"
echo ""
read -p "Do you want to proceed? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo -e "${RED}Deployment cancelled${NC}"
    exit 0
fi

# Apply deployment
echo -e "${YELLOW}Deploying infrastructure...${NC}"
terraform apply tfplan

# Check if deployment was successful
if [ $? -eq 0 ]; then
    echo -e "${GREEN}  Deployment completed successfully!${NC}"
    
    # Get outputs
    echo -e "${YELLOW}Fetching deployment outputs...${NC}"
    terraform output -json > ../deployment-outputs.json
    
    echo -e "${GREEN}==================================${NC}"
    echo -e "${GREEN}Deployment Information:${NC}"
    echo -e "${GREEN}==================================${NC}"
    
    # Display key information
    terraform output dashboard_info
    
    echo -e "${GREEN}==================================${NC}"
    echo -e "${YELLOW}⚠️  IMPORTANT NEXT STEPS:${NC}"
    echo "1. ✉️  Check your email and confirm SNS subscriptions (2 emails)"
    echo "2.   Test the system:"
    echo "      cd $(dirname "$0")"
    echo "      ./test.sh"
    echo ""
    echo "3.   View first scan results (after 5-10 minutes):"
    echo "      aws dynamodb scan --table-name finops-automation-idle-resources --limit 5"
    echo ""
    echo "4.   Download reports from S3 (after scans complete):"
    echo "      aws s3 ls s3://\$(cd terraform && terraform output -raw s3_bucket_name)/reports/"
    echo ""
    echo "5. ⚙️  Adjust configuration as needed:"
    echo "      - Budgets: Edit terraform.tfvars"
    echo "      - Thresholds: Edit config/*.json"
    echo "      - Enable cleanup: Set enable_auto_cleanup = true"
    echo ""
    echo -e "${BLUE}  Tip: All cleanup actions run in DRY-RUN mode by default (safe)${NC}"
    
else
    echo -e "${RED} Deployment failed${NC}"
    exit 1
fi
