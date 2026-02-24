#!/bin/bash

set -e

echo "Cleaning up FinOps Automation System..."

cd "$(dirname "$0")/../terraform"

# Confirm destruction
echo "WARNING: This will destroy all resources!"
echo "This includes:"
echo "  - Lambda functions"
echo "  - DynamoDB tables (with all data)"
echo "  - S3 bucket (with all reports)"
echo "  - SNS topics"
echo "  - EventBridge rules"
echo "  - IAM roles"
echo ""
read -p "Are you absolutely sure? Type 'destroy' to confirm: " confirm

if [ "$confirm" != "destroy" ]; then
    echo "Cleanup cancelled"
    exit 0
fi

# Empty S3 bucket first
echo "Emptying S3 bucket..."
S3_BUCKET=$(terraform output -raw s3_bucket_name 2>/dev/null || echo "")

if [ -n "$S3_BUCKET" ]; then
    aws s3 rm s3://$S3_BUCKET --recursive || true
fi

# Destroy infrastructure
echo "Destroying infrastructure..."
terraform destroy -auto-approve

if [ $? -eq 0 ]; then
    echo "Cleanup completed successfully"
    
    # Clean up local files
    rm -f tfplan
    rm -f ../deployment-outputs.json
    rm -f /tmp/*-output.json
    rm -rf .terraform
    rm -f .terraform.lock.hcl
    rm -f ../lambda/*.zip
    
    echo "All resources have been removed"
else
    echo "Cleanup failed. Some resources may still exist."
    exit 1
fi
