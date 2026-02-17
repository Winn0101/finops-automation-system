# Random suffix for unique resource names
resource "random_id" "suffix" {
  byte_length = 4
}

# Data sources
data "aws_region" "current" {}

# DynamoDB Tables
resource "aws_dynamodb_table" "cost_anomalies" {
  name           = "${var.project_name}-cost-anomalies"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "anomaly_id"
  range_key      = "detected_date"

  attribute {
    name = "anomaly_id"
    type = "S"
  }

  attribute {
    name = "detected_date"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  global_secondary_index {
    name            = "StatusIndex"
    hash_key        = "status"
    range_key       = "detected_date"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Name = "${var.project_name}-cost-anomalies"
  }
}

resource "aws_dynamodb_table" "idle_resources" {
  name           = "${var.project_name}-idle-resources"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "resource_id"
  range_key      = "scan_date"

  attribute {
    name = "resource_id"
    type = "S"
  }

  attribute {
    name = "scan_date"
    type = "S"
  }

  attribute {
    name = "resource_type"
    type = "S"
  }

  global_secondary_index {
    name            = "ResourceTypeIndex"
    hash_key        = "resource_type"
    range_key       = "scan_date"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Name = "${var.project_name}-idle-resources"
  }
}

resource "aws_dynamodb_table" "tag_compliance" {
  name           = "${var.project_name}-tag-compliance"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "resource_arn"
  range_key      = "scan_date"

  attribute {
    name = "resource_arn"
    type = "S"
  }

  attribute {
    name = "scan_date"
    type = "S"
  }

  attribute {
    name = "compliance_status"
    type = "S"
  }

  global_secondary_index {
    name            = "ComplianceIndex"
    hash_key        = "compliance_status"
    range_key       = "scan_date"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Name = "${var.project_name}-tag-compliance"
  }
}

resource "aws_dynamodb_table" "cleanup_actions" {
  name           = "${var.project_name}-cleanup-actions"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "action_id"
  range_key      = "scheduled_date"

  attribute {
    name = "action_id"
    type = "S"
  }

  attribute {
    name = "scheduled_date"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  global_secondary_index {
    name            = "StatusIndex"
    hash_key        = "status"
    range_key       = "scheduled_date"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Name = "${var.project_name}-cleanup-actions"
  }
}

# SNS Topics for Notifications
resource "aws_sns_topic" "cost_alerts" {
  name = "${var.project_name}-cost-alerts"

  tags = {
    Name = "${var.project_name}-cost-alerts"
  }
}

resource "aws_sns_topic_subscription" "cost_alerts_email" {
  topic_arn = aws_sns_topic.cost_alerts.arn
  protocol  = "email"
  endpoint  = var.owner_email
}

resource "aws_sns_topic" "cleanup_notifications" {
  name = "${var.project_name}-cleanup-notifications"

  tags = {
    Name = "${var.project_name}-cleanup-notifications"
  }
}

resource "aws_sns_topic_subscription" "cleanup_email" {
  topic_arn = aws_sns_topic.cleanup_notifications.arn
  protocol  = "email"
  endpoint  = var.owner_email
}

# S3 Bucket for Reports and Logs
resource "aws_s3_bucket" "finops_data" {
  bucket = "${var.project_name}-data-${random_id.suffix.hex}"

  tags = {
    Name = "${var.project_name}-data"
  }
}

resource "aws_s3_bucket_versioning" "finops_data" {
  bucket = aws_s3_bucket.finops_data.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "finops_data" {
  bucket = aws_s3_bucket.finops_data.id

  rule {
    id     = "cleanup-old-reports"
    status = "Enabled"

    filter {
      prefix = "reports/"
    }

    expiration {
      days = 90
    }
  }

  rule {
    id     = "archive-old-scans"
    status = "Enabled"

    filter {
      prefix = "scans/"
    }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    expiration {
      days = 180
    }
  }
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "cost_analyzer" {
  name              = "/aws/lambda/${var.project_name}-cost-analyzer"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-cost-analyzer-logs"
  }
}

resource "aws_cloudwatch_log_group" "resource_scanner" {
  name              = "/aws/lambda/${var.project_name}-resource-scanner"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-resource-scanner-logs"
  }
}

resource "aws_cloudwatch_log_group" "tag_enforcer" {
  name              = "/aws/lambda/${var.project_name}-tag-enforcer"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-tag-enforcer-logs"
  }
}

resource "aws_cloudwatch_log_group" "cleanup_executor" {
  name              = "/aws/lambda/${var.project_name}-cleanup-executor"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-cleanup-executor-logs"
  }
}

resource "aws_cloudwatch_log_group" "budget_monitor" {
  name              = "/aws/lambda/${var.project_name}-budget-monitor"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-budget-monitor-logs"
  }
}

resource "aws_cloudwatch_log_group" "report_generator" {
  name              = "/aws/lambda/${var.project_name}-report-generator"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-report-generator-logs"
  }
}

# SSM Parameters for Configuration
resource "aws_ssm_parameter" "cost_rules" {
  name  = "/${var.project_name}/config/cost-rules"
  type  = "String"
  value = file("${path.module}/../config/cost-rules.json")

  tags = {
    Name = "${var.project_name}-cost-rules"
  }
}

resource "aws_ssm_parameter" "tag_policies" {
  name  = "/${var.project_name}/config/tag-policies"
  type  = "String"
  value = file("${path.module}/../config/tag-policies.json")

  tags = {
    Name = "${var.project_name}-tag-policies"
  }
}

resource "aws_ssm_parameter" "cleanup_policies" {
  name  = "/${var.project_name}/config/cleanup-policies"
  type  = "String"
  value = file("${path.module}/../config/cleanup-policies.json")

  tags = {
    Name = "${var.project_name}-cleanup-policies"
  }
}

resource "aws_ssm_parameter" "slack_webhook" {
  count = var.slack_webhook_url != "" ? 1 : 0
  name  = "/${var.project_name}/config/slack-webhook"
  type  = "SecureString"
  value = var.slack_webhook_url

  tags = {
    Name = "${var.project_name}-slack-webhook"
  }
}
