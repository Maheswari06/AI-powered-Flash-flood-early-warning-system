# ╔══════════════════════════════════════════════════════════════════╗
# ║  ARGUS — Terraform Outputs                                     ║
# ╚══════════════════════════════════════════════════════════════════╝

# ── EKS ────────────────────────────────────────────────────────────
output "eks_cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS cluster API endpoint"
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_certificate_authority" {
  description = "EKS cluster CA certificate"
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

output "eks_oidc_provider_arn" {
  description = "EKS OIDC provider ARN (for IRSA)"
  value       = module.eks.oidc_provider_arn
}

# ── MSK ────────────────────────────────────────────────────────────
output "msk_bootstrap_brokers" {
  description = "MSK bootstrap broker endpoints (TLS)"
  value       = aws_msk_cluster.argus.bootstrap_brokers_tls
}

output "msk_zookeeper_connect" {
  description = "MSK ZooKeeper connection string"
  value       = aws_msk_cluster.argus.zookeeper_connect_string
}

# ── RDS ────────────────────────────────────────────────────────────
output "rds_endpoint" {
  description = "RDS TimescaleDB endpoint"
  value       = aws_db_instance.argus.endpoint
}

output "rds_address" {
  description = "RDS hostname"
  value       = aws_db_instance.argus.address
}

# ── ElastiCache ───────────────────────────────────────────────────
output "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  value       = aws_elasticache_replication_group.argus.primary_endpoint_address
}

# ── S3 ─────────────────────────────────────────────────────────────
output "model_bucket_name" {
  description = "S3 bucket for model artifacts"
  value       = aws_s3_bucket.models.id
}

output "dashboard_bucket_name" {
  description = "S3 bucket for dashboard static assets"
  value       = aws_s3_bucket.dashboard.id
}

# ── CloudFront ─────────────────────────────────────────────────────
output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.dashboard.id
}

output "cloudfront_domain_name" {
  description = "CloudFront domain name"
  value       = aws_cloudfront_distribution.dashboard.domain_name
}

# ── Route53 ────────────────────────────────────────────────────────
output "route53_zone_id" {
  description = "Route53 hosted zone ID"
  value       = var.environment == "production" ? aws_route53_zone.argus[0].zone_id : "N/A"
}

# ── IAM ────────────────────────────────────────────────────────────
output "external_secrets_role_arn" {
  description = "IAM role ARN for External Secrets Operator"
  value       = aws_iam_role.external_secrets.arn
}

# ── VPC ────────────────────────────────────────────────────────────
output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = module.vpc.private_subnets
}
