#!/bin/bash

set -e

echo " Testing FinOps Automation System..."

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get outputs
cd "$(dirname "$0")/../terraform"

if [ ! -f "../deployment-outputs.json" ]; then
    echo -e "${YELLOW}Fetching outputs...${NC}"
    terraform output -json > ../deployment-outputs.json
fi

# Extract values
COST_ANALYZER=$(terraform output -json | jq -r '.lambda_functions.value.cost_analyzer')
RESOURCE_SCANNER=$(terraform output -json | jq -r '.lambda_functions.value.resource_scanner')
TAG_ENFORCER=$(terraform output -json | jq -r '.lambda_functions.value.tag_enforcer')
BUDGET_MONITOR=$(terraform output -json | jq -r '.lambda_functions.value.budget_monitor')
REPORT_GENERATOR=$(terraform output -json | jq -r '.lambda_functions.value.report_generator')
S3_BUCKET=$(terraform output -json | jq -r '.s3_bucket_name.value')

echo -e "${GREEN}Testing Lambda functions...${NC}"

# Test 1: Cost Analyzer
echo -e "${YELLOW}Test 1: Running Cost Analyzer...${NC}"
aws lambda invoke \
    --function-name "$COST_ANALYZER" \
    --log-type Tail \
    /tmp/cost-analyzer-output.json > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Cost Analyzer executed successfully${NC}"
    cat /tmp/cost-analyzer-output.json | jq '.'
else
    echo -e "${RED}✗ Cost Analyzer failed${NC}"
fi

echo ""

# Test 2: Resource Scanner
echo -e "${YELLOW}Test 2: Running Resource Scanner...${NC}"
aws lambda invoke \
    --function-name "$RESOURCE_SCANNER" \
    --log-type Tail \
    /tmp/resource-scanner-output.json > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Resource Scanner executed successfully${NC}"
    cat /tmp/resource-scanner-output.json | jq '.'
else
    echo -e "${RED}✗ Resource Scanner failed${NC}"
fi

echo ""

# Test 3: Tag Enforcer
echo -e "${YELLOW}Test 3: Running Tag Enforcer...${NC}"
aws lambda invoke \
    --function-name "$TAG_ENFORCER" \
    --log-type Tail \
    /tmp/tag-enforcer-output.json > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Tag Enforcer executed successfully${NC}"
    cat /tmp/tag-enforcer-output.json | jq '.'
else
    echo -e "${RED}✗ Tag Enforcer failed${NC}"
fi

echo ""

# Test 4: Budget Monitor
echo -e "${YELLOW}Test 4: Running Budget Monitor...${NC}"
aws lambda invoke \
    --function-name "$BUDGET_MONITOR" \
    --log-type Tail \
    /tmp/budget-monitor-output.json > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Budget Monitor executed successfully${NC}"
    cat /tmp/budget-monitor-output.json | jq '.'
else
    echo -e "${RED}✗ Budget Monitor failed${NC}"
fi

echo ""

# Test 5: Report Generator
echo -e "${YELLOW}Test 5: Running Report Generator...${NC}"
aws lambda invoke \
    --function-name "$REPORT_GENERATOR" \
    --log-type Tail \
    /tmp/report-generator-output.json > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Report Generator executed successfully${NC}"
    cat /tmp/report-generator-output.json | jq '.'
else
    echo -e "${RED}✗ Report Generator failed${NC}"
fi

echo ""

# Check S3 for reports
echo -e "${YELLOW}Checking S3 for generated reports...${NC}"
REPORT_COUNT=$(aws s3 ls s3://$S3_BUCKET/reports/ | wc -l)
echo -e "${GREEN}Found $REPORT_COUNT report(s) in S3${NC}"

if [ $REPORT_COUNT -gt 0 ]; then
    echo -e "${YELLOW}Latest reports:${NC}"
    aws s3 ls s3://$S3_BUCKET/reports/ --recursive | tail -5
fi

echo ""

# Check DynamoDB tables
echo -e "${YELLOW}Checking DynamoDB tables...${NC}"

ANOMALIES_TABLE=$(terraform output -json | jq -r '.dynamodb_tables.value.cost_anomalies')
IDLE_TABLE=$(terraform output -json | jq -r '.dynamodb_tables.value.idle_resources')
TAG_TABLE=$(terraform output -json | jq -r '.dynamodb_tables.value.tag_compliance')

ANOMALIES_COUNT=$(aws dynamodb scan --table-name "$ANOMALIES_TABLE" --select COUNT | jq -r '.Count')
IDLE_COUNT=$(aws dynamodb scan --table-name "$IDLE_TABLE" --select COUNT | jq -r '.Count')
TAG_COUNT=$(aws dynamodb scan --table-name "$TAG_TABLE" --select COUNT | jq -r '.Count')

echo -e "${GREEN}Cost Anomalies: $ANOMALIES_COUNT${NC}"
echo -e "${GREEN}Idle Resources: $IDLE_COUNT${NC}"
echo -e "${GREEN}Tag Compliance Records: $TAG_COUNT${NC}"

echo ""
echo -e "${GREEN}==================================${NC}"
echo -e "${GREEN}Testing Complete!${NC}"
echo -e "${GREEN}==================================${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Check your email for SNS notifications"
echo "2. Download reports from S3:"
echo "   aws s3 cp s3://$S3_BUCKET/reports/ ./reports/ --recursive"
echo "3. View detailed logs:"
echo "   aws logs tail /aws/lambda/$COST_ANALYZER --follow"
echo "4. View data in DynamoDB:"
echo "   aws dynamodb scan --table-name $IDLE_TABLE"
