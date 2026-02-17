output "s3_bucket_name" {
  description = "S3 bucket for FinOps data"
  value       = aws_s3_bucket.finops_data.id
}

output "cost_alerts_topic_arn" {
  description = "SNS topic ARN for cost alerts"
  value       = aws_sns_topic.cost_alerts.arn
}

output "cleanup_notifications_topic_arn" {
  description = "SNS topic ARN for cleanup notifications"
  value       = aws_sns_topic.cleanup_notifications.arn
}

output "dynamodb_tables" {
  description = "DynamoDB table names"
  value = {
    cost_anomalies  = aws_dynamodb_table.cost_anomalies.name
    idle_resources  = aws_dynamodb_table.idle_resources.name
    tag_compliance  = aws_dynamodb_table.tag_compliance.name
    cleanup_actions = aws_dynamodb_table.cleanup_actions.name
  }
}

output "lambda_functions" {
  description = "Lambda function names"
  value = {
    cost_analyzer     = aws_lambda_function.cost_analyzer.function_name
    resource_scanner  = aws_lambda_function.resource_scanner.function_name
    tag_enforcer      = aws_lambda_function.tag_enforcer.function_name
    cleanup_executor  = aws_lambda_function.cleanup_executor.function_name
    budget_monitor    = aws_lambda_function.budget_monitor.function_name
    report_generator  = aws_lambda_function.report_generator.function_name
  }
}

output "eventbridge_rules" {
  description = "EventBridge rule names"
  value = {
    daily_cost_analysis = aws_cloudwatch_event_rule.daily_cost_analysis.name
    resource_scan       = aws_cloudwatch_event_rule.resource_scan.name
    tag_enforcement     = aws_cloudwatch_event_rule.tag_enforcement.name
    budget_monitoring   = aws_cloudwatch_event_rule.budget_monitoring.name
    weekly_report       = aws_cloudwatch_event_rule.weekly_report.name
  }
}

output "configuration_parameters" {
  description = "SSM Parameter Store paths"
  value = {
    cost_rules      = aws_ssm_parameter.cost_rules.name
    tag_policies    = aws_ssm_parameter.tag_policies.name
    cleanup_policies = aws_ssm_parameter.cleanup_policies.name
  }
}

output "useful_commands" {
  description = "Useful AWS CLI commands"
  value = <<-EOT
    # View cost anomalies
    aws dynamodb scan --table-name ${aws_dynamodb_table.cost_anomalies.name}
    
    # View idle resources
    aws dynamodb scan --table-name ${aws_dynamodb_table.idle_resources.name}
    
    # View tag compliance
    aws dynamodb scan --table-name ${aws_dynamodb_table.tag_compliance.name}
    
    # Manually trigger cost analysis
    aws lambda invoke --function-name ${aws_lambda_function.cost_analyzer.function_name} /tmp/output.json
    
    # Manually trigger resource scan
    aws lambda invoke --function-name ${aws_lambda_function.resource_scanner.function_name} /tmp/output.json
    
    # Generate report manually
    aws lambda invoke --function-name ${aws_lambda_function.report_generator.function_name} /tmp/output.json
    
    # View reports in S3
    aws s3 ls s3://${aws_s3_bucket.finops_data.id}/reports/
    
    # Download latest report
    aws s3 cp s3://${aws_s3_bucket.finops_data.id}/reports/ . --recursive --exclude "*" --include "*.html"
    
    # View Lambda logs
    aws logs tail /aws/lambda/${var.project_name}-cost-analyzer --follow
  EOT
}

output "dashboard_info" {
  description = "Information about accessing dashboards and reports"
  value = <<-EOT
    FinOps Automation System Deployed Successfully!
    
       Email Notifications:
       - Cost Alerts: Check ${var.owner_email} for SNS subscription confirmation
       - Cleanup Notifications: Check ${var.owner_email} for SNS subscription confirmation
    
       Reports Location:
       - S3 Bucket: ${aws_s3_bucket.finops_data.id}
       - Reports Path: s3://${aws_s3_bucket.finops_data.id}/reports/
    
       Schedules:
       - Cost Analysis: Daily at 3:00 AM UTC
       - Resource Scan: ${var.scan_schedule}
       - Tag Enforcement: Daily at 4:00 AM UTC
       - Budget Monitor: Every 6 hours
       - Weekly Report: ${var.report_schedule}
    
       Budget Settings:
       - Daily Budget: $${var.daily_budget_usd}
       - Monthly Budget: $${var.monthly_budget_usd}
       - Cleanup Mode: ${var.cleanup_dry_run ? "DRY RUN" : "LIVE"}
       - Auto Cleanup: ${var.enable_auto_cleanup ? "ENABLED" : "DISABLED"}
    
       View data in AWS Console:
       - DynamoDB: https://console.aws.amazon.com/dynamodbv2/home?region=${var.aws_region}#tables
       - Lambda: https://console.aws.amazon.com/lambda/home?region=${var.aws_region}#/functions
       - S3: https://s3.console.aws.amazon.com/s3/buckets/${aws_s3_bucket.finops_data.id}
       - CloudWatch: https://console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}
  EOT
}
