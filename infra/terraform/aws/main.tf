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
  count             = 1
  source            = "../modules/shared_network"
  name_prefix       = "vintex-shared"
  vpc_cidr          = "10.80.0.0/16"
  subnet_cidr       = "10.80.1.0/24"
  availability_zone = "${local.aws_region}a"
}

module "registry" {
  count  = 1
  source = "../modules/container_registry"
}

module "budget" {
  count           = 1
  source          = "../modules/project_budget"
  account_id      = var.expected_account_id
  email_addresses = var.budget_email_addresses
}

# One staging state owns the network, registry and runtime resources.
module "services" {
  count      = 1
  source     = "../modules/staging_services"
  account_id = var.expected_account_id
}

module "host" {
  count               = 1
  source              = "../modules/staging_host"
  account_id          = var.expected_account_id
  vpc_id              = module.network[0].vpc_id
  subnet_id           = module.network[0].public_subnet_id
  media_bucket        = module.services[0].media_bucket
  queue_arn           = module.services[0].queue_arn
  log_group_arns      = module.services[0].log_group_arns
  depends_on          = [module.network]
  ecr_repository_arns = [for repository in module.registry[0].repositories : repository.arn]
}

module "scheduler" {
  count        = 1
  source       = "../modules/staging_schedule"
  account_id   = var.expected_account_id
  instance_id  = module.host[0].instance_id
  instance_arn = module.host[0].instance_arn
}
