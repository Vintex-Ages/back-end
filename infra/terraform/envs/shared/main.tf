locals {
  aws_region = "us-east-2"
}

provider "aws" {
  region              = local.aws_region
  allowed_account_ids = [var.expected_account_id]

  default_tags {
    tags = {
      Project     = "Vintex"
      Environment = "shared"
      ManagedBy   = "Terraform"
    }
  }
}

module "network" {
  source            = "../../modules/shared_network"
  name_prefix       = "vintex-shared"
  vpc_cidr          = "10.80.0.0/16"
  subnet_cidr       = "10.80.1.0/24"
  availability_zone = "${local.aws_region}a"
}

module "registry" {
  source = "../../modules/container_registry"
}

module "budget" {
  source          = "../../modules/project_budget"
  account_id      = var.expected_account_id
  email_addresses = var.budget_email_addresses
}
