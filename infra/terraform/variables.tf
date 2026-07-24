# ╔══════════════════════════════════════════════════════════════════╗
# ║  ARGUS — Terraform Variables                                    ║
# ╚══════════════════════════════════════════════════════════════════╝

# ── General ────────────────────────────────────────────────────────
variable "aws_region" {
  description = "AWS region (Mumbai — closest to Assam)"
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"
  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be development, staging, or production."
  }
}

# ── VPC ────────────────────────────────────────────────────────────
variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "private_subnets" {
  description = "Private subnet CIDRs"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "public_subnets" {
  description = "Public subnet CIDRs"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
}

# ── EKS ────────────────────────────────────────────────────────────
variable "general_node_min" {
  description = "Minimum general-purpose nodes"
  type        = number
  default     = 3
}

variable "general_node_max" {
  description = "Maximum general-purpose nodes"
  type        = number
  default     = 10
}

variable "general_node_desired" {
  description = "Desired general-purpose nodes"
  type        = number
  default     = 4
}

variable "gpu_node_min" {
  description = "Minimum GPU nodes"
  type        = number
  default     = 1
}

variable "gpu_node_max" {
  description = "Maximum GPU nodes"
  type        = number
  default     = 4
}

variable "gpu_node_desired" {
  description = "Desired GPU nodes"
  type        = number
  default     = 1
}

# ── MSK (Kafka) ───────────────────────────────────────────────────
variable "msk_instance_type" {
  description = "MSK broker instance type"
  type        = string
  default     = "kafka.m5.large"
}

variable "msk_ebs_volume_size" {
  description = "MSK EBS volume size in GB"
  type        = number
  default     = 100
}

# ── RDS (TimescaleDB) ─────────────────────────────────────────────
variable "rds_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.r6g.xlarge"
}

variable "rds_allocated_storage" {
  description = "Initial RDS storage in GB"
  type        = number
  default     = 100
}

variable "rds_max_storage" {
  description = "Maximum RDS autoscaling storage in GB"
  type        = number
  default     = 500
}

variable "db_password" {
  description = "Database master password"
  type        = string
  sensitive   = true
}

# ── ElastiCache (Redis) ───────────────────────────────────────────
variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.r6g.large"
}

# ── CloudFront / Route53 ──────────────────────────────────────────
variable "acm_certificate_arn" {
  description = "ACM certificate ARN for CloudFront (production only)"
  type        = string
  default     = ""
}
