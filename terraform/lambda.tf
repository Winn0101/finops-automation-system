# Data source for current account
data "aws_caller_identity" "current" {}

# IAM Role for Cost Analyzer Lambda
resource "aws_iam_role" "cost_analyzer_role" {
  name_prefix = "${var.project_name}-cost-analyzer-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-cost-analyzer-role"
  }
}

resource "aws_iam_role_policy" "cost_analyzer_policy" {
  name_prefix = "${var.project_name}-cost-analyzer-"
  role        = aws_iam_role.cost_analyzer_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "ce:GetCostAndUsage",
          "ce:GetCostForecast",
          "ce:GetDimensionValues"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.cost_anomalies.arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.finops_data.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.cost_alerts.arn
      }
    ]
  })
}

# Package and deploy Cost Analyzer Lambda
data "archive_file" "cost_analyzer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/cost-analyzer"
  output_path = "${path.module}/../lambda/cost-analyzer.zip"
}

resource "aws_lambda_function" "cost_analyzer" {
  filename         = data.archive_file.cost_analyzer_zip.output_path
  function_name    = "${var.project_name}-cost-analyzer"
  role            = aws_iam_role.cost_analyzer_role.arn
  handler         = "lambda_function.lambda_handler"
  source_code_hash = data.archive_file.cost_analyzer_zip.output_base64sha256
  runtime         = "python3.9"
  timeout         = 300
  memory_size     = 512

  environment {
    variables = {
      ANOMALIES_TABLE       = aws_dynamodb_table.cost_anomalies.name
      COST_ALERTS_TOPIC     = aws_sns_topic.cost_alerts.arn
      S3_BUCKET             = aws_s3_bucket.finops_data.id
      THRESHOLD_PERCENTAGE  = var.cost_anomaly_threshold
    }
  }

  tags = {
    Name = "${var.project_name}-cost-analyzer"
  }
}

# IAM Role for Resource Scanner Lambda
resource "aws_iam_role" "resource_scanner_role" {
  name_prefix = "${var.project_name}-resource-scanner-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-resource-scanner-role"
  }
}

resource "aws_iam_role_policy" "resource_scanner_policy" {
  name_prefix = "${var.project_name}-resource-scanner-"
  role        = aws_iam_role.resource_scanner_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:Describe*",
          "rds:Describe*",
          "elasticloadbalancing:Describe*",
          "cloudwatch:GetMetricStatistics"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.idle_resources.arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.finops_data.arn}/*"
      }
    ]
  })
}

# Package and deploy Resource Scanner Lambda
data "archive_file" "resource_scanner_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/resource-scanner"
  output_path = "${path.module}/../lambda/resource-scanner.zip"
}

resource "aws_lambda_function" "resource_scanner" {
  filename         = data.archive_file.resource_scanner_zip.output_path
  function_name    = "${var.project_name}-resource-scanner"
  role            = aws_iam_role.resource_scanner_role.arn
  handler         = "lambda_function.lambda_handler"
  source_code_hash = data.archive_file.resource_scanner_zip.output_base64sha256
  runtime         = "python3.9"
  timeout         = 900  # 15 minutes
  memory_size     = 1024

  environment {
    variables = {
      IDLE_RESOURCES_TABLE = aws_dynamodb_table.idle_resources.name
      S3_BUCKET            = aws_s3_bucket.finops_data.id
    }
  }

  tags = {
    Name = "${var.project_name}-resource-scanner"
  }
}

# IAM Role for Tag Enforcer Lambda
resource "aws_iam_role" "tag_enforcer_role" {
  name_prefix = "${var.project_name}-tag-enforcer-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-tag-enforcer-role"
  }
}

resource "aws_iam_role_policy" "tag_enforcer_policy" {
  name_prefix = "${var.project_name}-tag-enforcer-"
  role        = aws_iam_role.tag_enforcer_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeVolumes",
          "ec2:DescribeTags",
          "rds:DescribeDBInstances",
          "rds:ListTagsForResource",
          "s3:ListAllMyBuckets",
          "s3:GetBucketTagging"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.tag_compliance.arn
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter"
        ]
        Resource = "arn:aws:ssm:*:*:parameter/${var.project_name}/config/*"
      },
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.cleanup_notifications.arn
      }
    ]
  })
}

# Package and deploy Tag Enforcer Lambda
data "archive_file" "tag_enforcer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/tag-enforcer"
  output_path = "${path.module}/../lambda/tag-enforcer.zip"
}

resource "aws_lambda_function" "tag_enforcer" {
  filename         = data.archive_file.tag_enforcer_zip.output_path
  function_name    = "${var.project_name}-tag-enforcer"
  role            = aws_iam_role.tag_enforcer_role.arn
  handler         = "lambda_function.lambda_handler"
  source_code_hash = data.archive_file.tag_enforcer_zip.output_base64sha256
  runtime         = "python3.9"
  timeout         = 900
  memory_size     = 512

  environment {
    variables = {
      TAG_COMPLIANCE_TABLE       = aws_dynamodb_table.tag_compliance.name
      CLEANUP_NOTIFICATIONS_TOPIC = aws_sns_topic.cleanup_notifications.arn
    }
  }

  tags = {
    Name = "${var.project_name}-tag-enforcer"
  }
}

# IAM Role for Cleanup Executor Lambda
resource "aws_iam_role" "cleanup_executor_role" {
  name_prefix = "${var.project_name}-cleanup-executor-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-cleanup-executor-role"
  }
}

resource "aws_iam_role_policy" "cleanup_executor_policy" {
  name_prefix = "${var.project_name}-cleanup-executor-"
  role        = aws_iam_role.cleanup_executor_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeVolumes",
          "ec2:DescribeSnapshots",
          "ec2:DescribeImages",
          "ec2:StopInstances",
          "ec2:TerminateInstances",
          "ec2:DeleteVolume",
          "ec2:CreateSnapshot",
          "ec2:DeleteSnapshot",
          "ec2:DeregisterImage",
          "ec2:ReleaseAddress"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "elasticloadbalancing:DeleteLoadBalancer"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Query",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          aws_dynamodb_table.cleanup_actions.arn,
          "${aws_dynamodb_table.cleanup_actions.arn}/index/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter"
        ]
        Resource = "arn:aws:ssm:*:*:parameter/${var.project_name}/config/*"
      },
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.cleanup_notifications.arn
      }
    ]
  })
}

# Package and deploy Cleanup Executor Lambda
data "archive_file" "cleanup_executor_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/cleanup-executor"
  output_path = "${path.module}/../lambda/cleanup-executor.zip"
}

resource "aws_lambda_function" "cleanup_executor" {
  filename         = data.archive_file.cleanup_executor_zip.output_path
  function_name    = "${var.project_name}-cleanup-executor"
  role            = aws_iam_role.cleanup_executor_role.arn
  handler         = "lambda_function.lambda_handler"
  source_code_hash = data.archive_file.cleanup_executor_zip.output_base64sha256
  runtime         = "python3.9"
  timeout         = 900
  memory_size     = 512

  environment {
    variables = {
      CLEANUP_ACTIONS_TABLE       = aws_dynamodb_table.cleanup_actions.name
      CLEANUP_NOTIFICATIONS_TOPIC = aws_sns_topic.cleanup_notifications.arn
      DRY_RUN                     = var.cleanup_dry_run ? "true" : "false"
    }
  }

  tags = {
    Name = "${var.project_name}-cleanup-executor"
  }
}

# IAM Role for Budget Monitor Lambda
resource "aws_iam_role" "budget_monitor_role" {
  name_prefix = "${var.project_name}-budget-monitor-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-budget-monitor-role"
  }
}

resource "aws_iam_role_policy" "budget_monitor_policy" {
  name_prefix = "${var.project_name}-budget-monitor-"
  role        = aws_iam_role.budget_monitor_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "ce:GetCostAndUsage",
          "ce:GetCostForecast",
          "budgets:ViewBudget",
          "budgets:DescribeBudgets"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.finops_data.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.cost_alerts.arn
      }
    ]
  })
}

# Package and deploy Budget Monitor Lambda
data "archive_file" "budget_monitor_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/budget-monitor"
  output_path = "${path.module}/../lambda/budget-monitor.zip"
}

resource "aws_lambda_function" "budget_monitor" {
  filename         = data.archive_file.budget_monitor_zip.output_path
  function_name    = "${var.project_name}-budget-monitor"
  role            = aws_iam_role.budget_monitor_role.arn
  handler         = "lambda_function.lambda_handler"
  source_code_hash = data.archive_file.budget_monitor_zip.output_base64sha256
  runtime         = "python3.9"
  timeout         = 300
  memory_size     = 512

  environment {
    variables = {
      COST_ALERTS_TOPIC = aws_sns_topic.cost_alerts.arn
      S3_BUCKET         = aws_s3_bucket.finops_data.id
      DAILY_BUDGET      = var.daily_budget_usd
      MONTHLY_BUDGET    = var.monthly_budget_usd
      ACCOUNT_ID        = data.aws_caller_identity.current.account_id
    }
  }

  tags = {
    Name = "${var.project_name}-budget-monitor"
  }
}

# IAM Role for Report Generator Lambda
resource "aws_iam_role" "report_generator_role" {
  name_prefix = "${var.project_name}-report-generator-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-report-generator-role"
  }
}

resource "aws_iam_role_policy" "report_generator_policy" {
  name_prefix = "${var.project_name}-report-generator-"
  role        = aws_iam_role.report_generator_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "ce:GetCostAndUsage",
          "ce:GetCostForecast"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Scan",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.idle_resources.arn,
          aws_dynamodb_table.cost_anomalies.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.finops_data.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.cost_alerts.arn
      }
    ]
  })
}

# Package and deploy Report Generator Lambda
data "archive_file" "report_generator_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/report-generator"
  output_path = "${path.module}/../lambda/report-generator.zip"
}

resource "aws_lambda_function" "report_generator" {
  filename         = data.archive_file.report_generator_zip.output_path
  function_name    = "${var.project_name}-report-generator"
  role            = aws_iam_role.report_generator_role.arn
  handler         = "lambda_function.lambda_handler"
  source_code_hash = data.archive_file.report_generator_zip.output_base64sha256
  runtime         = "python3.9"
  timeout         = 900
  memory_size     = 1024

  environment {
    variables = {
      S3_BUCKET             = aws_s3_bucket.finops_data.id
      COST_ALERTS_TOPIC     = aws_sns_topic.cost_alerts.arn
      IDLE_RESOURCES_TABLE  = aws_dynamodb_table.idle_resources.name
      ANOMALIES_TABLE       = aws_dynamodb_table.cost_anomalies.name
    }
  }

  tags = {
    Name = "${var.project_name}-report-generator"
  }
}
