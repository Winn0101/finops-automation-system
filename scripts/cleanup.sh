#!/bin/bash

set -e

echo "  Cleaning up FinOps Automation System..."

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

cd "$(dirname "$0")/../terraform"

# Confirm destruction
echo -e "${RED}⚠️  WARNING: This will destroy all resources!${NC}"
echo -e "${YELLOW}This includes:${NC}"
echo "  - Lambda functions"
echo "  - DynamoDB tables (with all data)"
echo "  - S3 bucket (with all reports)"
echo "  - SNS topics"
echo "  - EventBridge rules"
echo "  - IAM roles"
echo ""
read -p "Are you absolutely sure? Type 'destroy' to confirm: " confirm

if [ "$confirm" != "destroy" ]; then
    echo -e "${GREEN}Cleanup cancelled${NC}"
    exit 0
fi

# Empty S3 bucket first
echo -e "${YELLOW}Emptying S3 bucket...${NC}"
S3_BUCKET=$(terraform output -raw s3_bucket_name 2>/dev/null || echo "")

if [ -n "$S3_BUCKET" ]; then
    aws s3 rm s3://$S3_BUCKET --recursive || true
fi

# Destroy infrastructure
echo -e "${YELLOW}Destroying infrastructure...${NC}"
terraform destroy -auto-approve

if [ $? -eq 0 ]; then
    echo -e "${GREEN} Cleanup completed successfully${NC}"
    
    # Clean up local files
    rm -f tfplan
    rm -f ../deployment-outputs.json
    rm -f /tmp/*-output.json
    rm -rf .terraform
    rm -f .terraform.lock.hcl
    rm -f ../lambda/*.zip
    
    echo -e "${GREEN}All resources have been removed${NC}"
else
    echo -e "${RED} Cleanup failed. Some resources may still exist.${NC}"
    exit 1
fi
