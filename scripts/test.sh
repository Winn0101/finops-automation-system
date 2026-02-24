#!/bin/bash

set -e

echo "Testing FinOps Automation System..."

# Get outputs
cd "$(dirname "$0")/../terraform"

if [ ! -f "../deployment-outputs.json" ]; then
    echo "Fetching outputs..."
    terraform output -json > ../deployment-outputs.json
fi

# Extract values
COST_ANALYZER=$(terraform output -json | jq -r '.lambda_functions.value.cost_analyzer')
RESOURCE_SCANNER=$(terraform output -json | jq -r '.lambda_functions.value.resource_scanner')
TAG_ENFORCER=$(terraform output -json | jq -r '.lambda_functions.value.tag_enforcer')
BUDGET_MONITOR=$(terraform output -json | jq -r '.lambda_functions.value.budget_monitor')
REPORT_GENERATOR=$(terraform output -json | jq -r '.lambda_functions.value.report_generator')
S3_BUCKET=$(terraform output -json | jq -r '.s3_bucket_name.value')

echo "Testing Lambda functions..."

# Test 1: Cost Analyzer
echo "Test 1: Running Cost Analyzer..."
aws lambda invoke \
    --function-name "$COST_ANALYZER" \
    --log-type Tail \
    /tmp/cost-analyzer-output.json > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "Cost Analyzer executed successfully"
    cat /tmp/cost-analyzer-output.json | jq '.'
else
    echo "Cost Analyzer failed"
fi

echo ""

# Test 2: Resource Scanner
echo "Test 2: Running Resource Scanner..."
aws lambda invoke \
    --function-name "$RESOURCE_SCANNER" \
    --log-type Tail \
    /tmp/resource-scanner-output.json > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "Resource Scanner executed successfully"
    cat /tmp/resource-scanner-output.json | jq '.'
else
    echo "Resource Scanner failed"
fi

echo ""

# Test 3: Tag Enforcer
echo "Test 3: Running Tag Enforcer..."
aws lambda invoke \
    --function-name "$TAG_ENFORCER" \
    --log-type Tail \
    /tmp/tag-enforcer-output.json > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "Tag Enforcer executed successfully"
    cat /tmp/tag-enforcer-output.json | jq '.'
else
    echo "Tag Enforcer failed"
fi

echo ""

# Test 4: Budget Monitor
echo "Test 4: Running Budget Monitor..."
aws lambda invoke \
    --function-name "$BUDGET_MONITOR" \
    --log-type Tail \
    /tmp/budget-monitor-output.json > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "Budget Monitor executed successfully"
    cat /tmp/budget-monitor-output.json | jq '.'
else
    echo "Budget Monitor failed"
fi

echo ""

# Test 5: Report Generator
echo "Test 5: Running Report Generator..."
aws lambda invoke \
    --function-name "$REPORT_GENERATOR" \
    --log-type Tail \
    /tmp/report-generator-output.json > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "Report Generator executed successfully"
    cat /tmp/report-generator-output.json | jq '.'
else
    echo "Report Generator failed"
fi

echo ""

# Check S3 for reports
echo "Checking S3 for generated reports..."
REPORT_COUNT=$(aws s3 ls s3://$S3_BUCKET/reports/ | wc -l)
echo "Found $REPORT_COUNT report(s) in S3"

if [ $REPORT_COUNT -gt 0 ]; then
    echo "Latest reports:"
    aws s3 ls s3://$S3_BUCKET/reports/ --recursive | tail -5
fi

echo ""

# Check DynamoDB tables
echo "Checking DynamoDB tables..."

ANOMALIES_TABLE=$(terraform output -json | jq -r '.dynamodb_tables.value.cost_anomalies')
IDLE_TABLE=$(terraform output -json | jq -r '.dynamodb_tables.value.idle_resources')
TAG_TABLE=$(terraform output -json | jq -r '.dynamodb_tables.value.tag_compliance')

ANOMALIES_COUNT=$(aws dynamodb scan --table-name "$ANOMALIES_TABLE" --select COUNT | jq -r '.Count')
IDLE_COUNT=$(aws dynamodb scan --table-name "$IDLE_TABLE" --select COUNT | jq -r '.Count')
TAG_COUNT=$(aws dynamodb scan --table-name "$TAG_TABLE" --select COUNT | jq -r '.Count')

echo "Cost Anomalies: $ANOMALIES_COUNT"
echo "Idle Resources: $IDLE_COUNT"
echo "Tag Compliance Records: $TAG_COUNT"

echo ""
echo "=================================="
echo "Testing Complete!"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. Check your email for SNS notifications"
echo "2. Download reports from S3:"
echo "   aws s3 cp s3://$S3_BUCKET/reports/ ./reports/ --recursive"
echo "3. View detailed logs:"
echo "   aws logs tail /aws/lambda/$COST_ANALYZER --follow"
echo "4. View data in DynamoDB:"
echo "   aws dynamodb scan --table-name $IDLE_TABLE"
