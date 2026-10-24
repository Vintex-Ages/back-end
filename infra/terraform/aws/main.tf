locals {
  aws_region = "us-east-2"
}

provider "aws" {
  region              = local.aws_region
  allowed_account_ids = [var.expected_account_id]
  default_tags {
    tags = {
      Project     = "Vintex"
      Environment = var.deployment
      ManagedBy   = "Terraform"
    }
  }
}

module "network" {
  source            = "../modules/shared_network"
  name_prefix       = "vintex-shared"
  vpc_cidr          = "10.80.0.0/16"
  subnet_cidr       = "10.80.1.0/24"
  availability_zone = "${local.aws_region}a"
}

module "registry" {
  source = "../modules/container_registry"
}

module "budget" {
  count           = var.enable_budget ? 1 : 0
  source          = "../modules/project_budget"
  account_id      = var.expected_account_id
  email_addresses = var.budget_email_addresses
}

# One staging state owns the network, registry and runtime resources.
module "services" {
  source     = "../modules/staging_services"
  account_id = var.expected_account_id
}

module "host" {
  source              = "../modules/staging_host"
  account_id          = var.expected_account_id
  vpc_id              = module.network.vpc_id
  subnet_id           = module.network.public_subnet_id
  media_bucket        = module.services.media_bucket
  queue_arn           = module.services.queue_arn
  log_group_arns      = module.services.log_group_arns
  depends_on          = [module.network]
  ecr_repository_arns = [for repository in module.registry.repositories : repository.arn]

  public_http_from_cloudfront = var.public_preview
}

module "scheduler" {
  source       = "../modules/staging_schedule"
  account_id   = var.expected_account_id
  instance_id  = module.host.instance_id
  instance_arn = module.host.instance_arn
}

module "preview" {
  count       = var.public_preview ? 1 : 0
  source      = "../modules/staging_preview"
  account_id  = var.expected_account_id
  instance_id = module.host.instance_id
}
