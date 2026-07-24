# ╔══════════════════════════════════════════════════════════════════╗
# ║  ARGUS — Terraform AWS Infrastructure                          ║
# ║  Region: ap-south-1 (Mumbai — closest to Assam)                ║
# ║  Resources: VPC, EKS, MSK, RDS+TimescaleDB, ElastiCache,      ║
# ║             S3, CloudFront, Route53, IAM                       ║
# ╚══════════════════════════════════════════════════════════════════╝

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.30"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.24"
    }
  }

  backend "s3" {
    bucket         = "argus-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "argus-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "ARGUS"
      Environment = var.environment
      ManagedBy   = "terraform"
      Team        = "hydra"
    }
  }
}

# ═══════════════════════════════════════════════════════════════════
# DATA SOURCES
# ═══════════════════════════════════════════════════════════════════
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

# ═══════════════════════════════════════════════════════════════════
# VPC — 3-AZ, public + private subnets
# ═══════════════════════════════════════════════════════════════════
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.4"

  name = "argus-${var.environment}-vpc"
  cidr = var.vpc_cidr

  azs             = slice(data.aws_availability_zones.available.names, 0, 3)
  private_subnets = var.private_subnets
  public_subnets  = var.public_subnets

  enable_nat_gateway   = true
  single_nat_gateway   = var.environment != "production"
  enable_dns_hostnames = true
  enable_dns_support   = true

  # EKS subnet tags
  public_subnet_tags = {
    "kubernetes.io/role/elb"                        = 1
    "kubernetes.io/cluster/argus-${var.environment}" = "shared"
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"               = 1
    "kubernetes.io/cluster/argus-${var.environment}" = "shared"
  }
}

# ═══════════════════════════════════════════════════════════════════
# EKS CLUSTER — v1.29, managed node groups
# ═══════════════════════════════════════════════════════════════════
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.21"

  cluster_name    = "argus-${var.environment}"
  cluster_version = "1.29"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_endpoint_public_access = true

  # Cluster add-ons
  cluster_addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent = true
    }
    aws-ebs-csi-driver = {
      most_recent = true
    }
  }

  # ── Node Groups ──
  eks_managed_node_groups = {
    # General workloads: API gateway, ingestion, alert, CHORUS, etc.
    general = {
      name           = "argus-general"
      instance_types = ["m5.xlarge"]
      capacity_type  = "ON_DEMAND"

      min_size     = var.general_node_min
      max_size     = var.general_node_max
      desired_size = var.general_node_desired

      labels = {
        workload-type = "general"
      }
    }

    # GPU nodes: Causal engine, MIRROR, feature engine
    gpu = {
      name           = "argus-gpu"
      instance_types = ["g4dn.xlarge"]
      capacity_type  = "ON_DEMAND"
      ami_type       = "AL2_x86_64_GPU"

      min_size     = var.gpu_node_min
      max_size     = var.gpu_node_max
      desired_size = var.gpu_node_desired

      labels = {
        workload-type = "gpu"
      }

      taints = [{
        key    = "nvidia.com/gpu"
        value  = "true"
        effect = "NO_SCHEDULE"
      }]
    }
  }

  # IRSA for External Secrets Operator
  enable_irsa = true
}

# ═══════════════════════════════════════════════════════════════════
# MSK — Managed Apache Kafka (3 brokers)
# ═══════════════════════════════════════════════════════════════════
resource "aws_msk_cluster" "argus" {
  cluster_name           = "argus-${var.environment}"
  kafka_version          = "3.5.1"
  number_of_broker_nodes = 3

  broker_node_group_info {
    instance_type  = var.msk_instance_type
    client_subnets = module.vpc.private_subnets

    storage_info {
      ebs_storage_info {
        volume_size = var.msk_ebs_volume_size
      }
    }

    security_groups = [aws_security_group.msk.id]
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.argus.arn
    revision = aws_msk_configuration.argus.latest_revision
  }

  logging_info {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = aws_cloudwatch_log_group.msk.name
      }
    }
  }

  tags = {
    Service = "kafka"
  }
}

resource "aws_msk_configuration" "argus" {
  name              = "argus-kafka-config"
  kafka_versions    = ["3.5.1"]

  server_properties = <<PROPERTIES
auto.create.topics.enable=true
default.replication.factor=3
min.insync.replicas=2
num.partitions=12
log.retention.hours=168
message.max.bytes=10485760
PROPERTIES
}

resource "aws_cloudwatch_log_group" "msk" {
  name              = "/aws/msk/argus-${var.environment}"
  retention_in_days = 30
}

resource "aws_security_group" "msk" {
  name_prefix = "argus-msk-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 9092
    to_port         = 9098
    protocol        = "tcp"
    security_groups = [module.eks.cluster_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ═══════════════════════════════════════════════════════════════════
# RDS — PostgreSQL 15.4 + TimescaleDB (Multi-AZ in prod)
# ═══════════════════════════════════════════════════════════════════
resource "aws_db_subnet_group" "argus" {
  name       = "argus-${var.environment}"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "rds" {
  name_prefix = "argus-rds-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.cluster_security_group_id]
  }
}

resource "aws_db_parameter_group" "timescale" {
  name        = "argus-timescaledb-pg15"
  family      = "postgres15"
  description = "ARGUS TimescaleDB parameter group"

  parameter {
    name         = "shared_preload_libraries"
    value        = "timescaledb,pg_stat_statements"
    apply_method = "pending-reboot"
  }

  parameter {
    name  = "max_connections"
    value = "200"
  }

  parameter {
    name  = "work_mem"
    value = "16384"
  }

  parameter {
    name  = "timescaledb.max_background_workers"
    value = "8"
  }

  tags = {
    Project     = "argus"
    Environment = var.environment
  }
}

resource "aws_db_instance" "argus" {
  identifier = "argus-timescale-${var.environment}"

  engine         = "postgres"
  engine_version = "15.4"
  instance_class = var.rds_instance_class

  allocated_storage     = var.rds_allocated_storage
  max_allocated_storage = var.rds_max_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "argus_db"
  username = "argus"
  password = var.db_password

  parameter_group_name = aws_db_parameter_group.timescale.name

  multi_az               = var.environment == "production"
  db_subnet_group_name   = aws_db_subnet_group.argus.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  backup_retention_period = var.environment == "production" ? 30 : 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  deletion_protection = var.environment == "production"
  skip_final_snapshot = var.environment != "production"

  performance_insights_enabled = true

  tags = {
    Service = "timescaledb"
  }
}

# ═══════════════════════════════════════════════════════════════════
# ElastiCache — Redis cluster (failover in prod)
# ═══════════════════════════════════════════════════════════════════
resource "aws_elasticache_subnet_group" "argus" {
  name       = "argus-${var.environment}"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "redis" {
  name_prefix = "argus-redis-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [module.eks.cluster_security_group_id]
  }
}

resource "aws_elasticache_replication_group" "argus" {
  replication_group_id = "argus-${var.environment}"
  description          = "ARGUS Redis cluster"

  node_type            = var.redis_node_type
  num_cache_clusters   = var.environment == "production" ? 2 : 1
  port                 = 6379

  subnet_group_name  = aws_elasticache_subnet_group.argus.name
  security_group_ids = [aws_security_group.redis.id]

  engine_version       = "7.0"
  parameter_group_name = "default.redis7"

  automatic_failover_enabled = var.environment == "production"
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  snapshot_retention_limit = var.environment == "production" ? 7 : 1
  snapshot_window          = "05:00-06:00"
}

# ═══════════════════════════════════════════════════════════════════
# S3 — Model storage (versioned)
# ═══════════════════════════════════════════════════════════════════
resource "aws_s3_bucket" "models" {
  bucket = "argus-models-${var.environment}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "models" {
  bucket = aws_s3_bucket.models.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "models" {
  bucket = aws_s3_bucket.models.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "models" {
  bucket = aws_s3_bucket.models.id

  rule {
    id     = "archive-old-models"
    status = "Enabled"

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    noncurrent_version_expiration {
      noncurrent_days = 180
    }
  }
}

resource "aws_s3_bucket_public_access_block" "models" {
  bucket = aws_s3_bucket.models.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ═══════════════════════════════════════════════════════════════════
# CloudFront — Dashboard CDN
# ═══════════════════════════════════════════════════════════════════
resource "aws_s3_bucket" "dashboard" {
  bucket = "argus-dashboard-${var.environment}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "dashboard" {
  bucket = aws_s3_bucket.dashboard.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_identity" "dashboard" {
  comment = "ARGUS Dashboard OAI"
}

resource "aws_cloudfront_distribution" "dashboard" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  aliases             = var.environment == "production" ? ["dashboard.argus.flood.gov.in"] : []

  origin {
    domain_name = aws_s3_bucket.dashboard.bucket_regional_domain_name
    origin_id   = "S3-Dashboard"

    s3_origin_config {
      origin_access_identity = aws_cloudfront_origin_access_identity.dashboard.cloudfront_access_identity_path
    }
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "S3-Dashboard"
    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 86400
    max_ttl     = 31536000
    compress    = true
  }

  # SPA fallback: route 404s to index.html
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = var.environment != "production"
    acm_certificate_arn            = var.environment == "production" ? var.acm_certificate_arn : null
    ssl_support_method             = var.environment == "production" ? "sni-only" : null
  }

  tags = {
    Service = "dashboard-cdn"
  }
}

# ═══════════════════════════════════════════════════════════════════
# Route53 — DNS records (production only)
# ═══════════════════════════════════════════════════════════════════
resource "aws_route53_zone" "argus" {
  count = var.environment == "production" ? 1 : 0
  name  = "argus.flood.gov.in"
}

resource "aws_route53_record" "api" {
  count   = var.environment == "production" ? 1 : 0
  zone_id = aws_route53_zone.argus[0].zone_id
  name    = "api.argus.flood.gov.in"
  type    = "A"

  alias {
    name                   = "placeholder-nlb-dns"  # Updated by EKS LB controller
    zone_id                = "Z2IFOLAFXWLO4F"
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "dashboard" {
  count   = var.environment == "production" ? 1 : 0
  zone_id = aws_route53_zone.argus[0].zone_id
  name    = "dashboard.argus.flood.gov.in"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.dashboard.domain_name
    zone_id                = aws_cloudfront_distribution.dashboard.hosted_zone_id
    evaluate_target_health = false
  }
}

# ═══════════════════════════════════════════════════════════════════
# IAM — External Secrets Operator IRSA role
# ═══════════════════════════════════════════════════════════════════
resource "aws_iam_role" "external_secrets" {
  name = "argus-${var.environment}-external-secrets"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = module.eks.oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${module.eks.oidc_provider}:sub" = "system:serviceaccount:argus-prod:external-secrets"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "external_secrets" {
  name = "argus-secrets-access"
  role = aws_iam_role.external_secrets.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ]
      Resource = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:argus/*"
    }]
  })
}

# ═══════════════════════════════════════════════════════════════════
# AWS Secrets Manager — seed secrets
# ═══════════════════════════════════════════════════════════════════
resource "aws_secretsmanager_secret" "argus_prod" {
  name                    = "argus/production/secrets"
  description             = "ARGUS production secrets"
  recovery_window_in_days = 30
}
