# EventBridge Rule for Daily Cost Analysis
resource "aws_cloudwatch_event_rule" "daily_cost_analysis" {
  name                = "${var.project_name}-daily-cost-analysis"
  description         = "Trigger cost analysis daily"
  schedule_expression = "cron(0 3 * * ? *)"  # 3 AM UTC daily

  tags = {
    Name = "${var.project_name}-daily-cost-analysis"
  }
}

resource "aws_cloudwatch_event_target" "daily_cost_analysis_target" {
  rule      = aws_cloudwatch_event_rule.daily_cost_analysis.name
  target_id = "CostAnalyzerLambda"
  arn       = aws_lambda_function.cost_analyzer.arn
}

resource "aws_lambda_permission" "allow_eventbridge_cost_analysis" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cost_analyzer.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_cost_analysis.arn
}

# EventBridge Rule for Resource Scanning
resource "aws_cloudwatch_event_rule" "resource_scan" {
  name                = "${var.project_name}-resource-scan"
  description         = "Trigger resource scanning"
  schedule_expression = var.scan_schedule

  tags = {
    Name = "${var.project_name}-resource-scan"
  }
}

resource "aws_cloudwatch_event_target" "resource_scan_target" {
  rule      = aws_cloudwatch_event_rule.resource_scan.name
  target_id = "ResourceScannerLambda"
  arn       = aws_lambda_function.resource_scanner.arn
}

resource "aws_lambda_permission" "allow_eventbridge_resource_scan" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.resource_scanner.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.resource_scan.arn
}

# EventBridge Rule for Tag Enforcement
resource "aws_cloudwatch_event_rule" "tag_enforcement" {
  name                = "${var.project_name}-tag-enforcement"
  description         = "Trigger tag enforcement daily"
  schedule_expression = "cron(0 4 * * ? *)"  # 4 AM UTC daily

  tags = {
    Name = "${var.project_name}-tag-enforcement"
  }
}

resource "aws_cloudwatch_event_target" "tag_enforcement_target" {
  rule      = aws_cloudwatch_event_rule.tag_enforcement.name
  target_id = "TagEnforcerLambda"
  arn       = aws_lambda_function.tag_enforcer.arn
}

resource "aws_lambda_permission" "allow_eventbridge_tag_enforcement" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.tag_enforcer.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.tag_enforcement.arn
}

# EventBridge Rule for Cleanup Execution (only if enabled)
resource "aws_cloudwatch_event_rule" "cleanup_execution" {
  count               = var.enable_auto_cleanup ? 1 : 0
  name                = "${var.project_name}-cleanup-execution"
  description         = "Trigger cleanup execution daily"
  schedule_expression = "cron(0 5 * * ? *)"  # 5 AM UTC daily

  tags = {
    Name = "${var.project_name}-cleanup-execution"
  }
}

resource "aws_cloudwatch_event_target" "cleanup_execution_target" {
  count     = var.enable_auto_cleanup ? 1 : 0
  rule      = aws_cloudwatch_event_rule.cleanup_execution[0].name
  target_id = "CleanupExecutorLambda"
  arn       = aws_lambda_function.cleanup_executor.arn
}

resource "aws_lambda_permission" "allow_eventbridge_cleanup" {
  count         = var.enable_auto_cleanup ? 1 : 0
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cleanup_executor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.cleanup_execution[0].arn
}

# EventBridge Rule for Budget Monitoring
resource "aws_cloudwatch_event_rule" "budget_monitoring" {
  name                = "${var.project_name}-budget-monitoring"
  description         = "Trigger budget monitoring every 6 hours"
  schedule_expression = "cron(0 */6 * * ? *)"  # Every 6 hours

  tags = {
    Name = "${var.project_name}-budget-monitoring"
  }
}

resource "aws_cloudwatch_event_target" "budget_monitoring_target" {
  rule      = aws_cloudwatch_event_rule.budget_monitoring.name
  target_id = "BudgetMonitorLambda"
  arn       = aws_lambda_function.budget_monitor.arn
}

resource "aws_lambda_permission" "allow_eventbridge_budget" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.budget_monitor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.budget_monitoring.arn
}

# EventBridge Rule for Weekly Reports
resource "aws_cloudwatch_event_rule" "weekly_report" {
  name                = "${var.project_name}-weekly-report"
  description         = "Trigger weekly report generation"
  schedule_expression = var.report_schedule

  tags = {
    Name = "${var.project_name}-weekly-report"
  }
}

resource "aws_cloudwatch_event_target" "weekly_report_target" {
  rule      = aws_cloudwatch_event_rule.weekly_report.name
  target_id = "ReportGeneratorLambda"
  arn       = aws_lambda_function.report_generator.arn

  input = jsonencode({
    report_type = "weekly"
  })
}

resource "aws_lambda_permission" "allow_eventbridge_report" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.report_generator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.weekly_report.arn
}
