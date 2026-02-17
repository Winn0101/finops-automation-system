variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "finops-automation"
}

variable "owner_email" {
  description = "Email for notifications and tagging"
  type        = string
}

variable "slack_webhook_url" {
  description = "Slack webhook URL for notifications"
  type        = string
  default     = ""
  sensitive   = true
}

variable "cost_anomaly_threshold" {
  description = "Percentage threshold for cost anomaly detection"
  type        = number
  default     = 25
}

variable "daily_budget_usd" {
  description = "Daily budget in USD"
  type        = number
  default     = 10
}

variable "monthly_budget_usd" {
  description = "Monthly budget in USD"
  type        = number
  default     = 100
}

variable "cleanup_dry_run" {
  description = "Run cleanup in dry-run mode (no actual deletions)"
  type        = bool
  default     = true
}

variable "enable_auto_cleanup" {
  description = "Enable automatic resource cleanup"
  type        = bool
  default     = false
}

variable "scan_schedule" {
  description = "Cron schedule for resource scanning"
  type        = string
  default     = "cron(0 2 * * ? *)" # Daily at 2 AM UTC
}

variable "report_schedule" {
  description = "Cron schedule for cost reports"
  type        = string
  default     = "cron(0 9 * * 1 *)" # Weekly on Monday at 9 AM UTC
}
