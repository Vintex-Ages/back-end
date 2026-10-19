locals {
  aws_region = "us-east-2"
  shared     = var.deployment == "shared"
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
  count             = local.shared ? 1 : 0
  source            = "../modules/shared_network"
  name_prefix       = "vintex-shared"
  vpc_cidr          = "10.80.0.0/16"
  subnet_cidr       = "10.80.1.0/24"
  availability_zone = "${local.aws_region}a"
}

module "registry" {
  count  = local.shared ? 1 : 0
  source = "../modules/container_registry"
}

module "budget" {
  count           = local.shared ? 1 : 0
  source          = "../modules/project_budget"
  account_id      = var.expected_account_id
  email_addresses = var.budget_email_addresses
}

# Only staging reads shared. A first shared plan never needs an existing state.
data "terraform_remote_state" "shared" {
  count   = local.shared ? 0 : 1
  backend = "s3"
  config = {
    bucket              = var.state_bucket
    key                 = "vintex/shared/terraform.tfstate"
    region              = local.aws_region
    allowed_account_ids = [var.expected_account_id]
  }
  lifecycle {
    postcondition {
      condition     = self.outputs.account_id == var.expected_account_id && self.outputs.aws_region == local.aws_region
      error_message = "Aplique shared na mesma conta e região antes da staging."
    }
  }
}

data "aws_vpc" "shared" {
  count = local.shared ? 0 : 1
  id    = data.terraform_remote_state.shared[0].outputs.vpc_id
  lifecycle {
    postcondition {
      condition     = self.owner_id == var.expected_account_id && lookup(self.tags, "Environment", "") == "shared" && lookup(self.tags, "Project", "") == "Vintex"
      error_message = "A VPC deve pertencer à conta e à base shared Vintex."
    }
  }
}

data "aws_subnet" "shared" {
  count = local.shared ? 0 : 1
  id    = data.terraform_remote_state.shared[0].outputs.public_subnet_id
  lifecycle {
    postcondition {
      condition     = self.vpc_id == data.aws_vpc.shared[0].id && self.owner_id == var.expected_account_id && self.map_public_ip_on_launch && lookup(self.tags, "Environment", "") == "shared"
      error_message = "A subnet pública deve pertencer à VPC shared e à conta esperada."
    }
  }
}

data "aws_ecr_repository" "shared" {
  for_each = local.shared ? toset([]) : toset(["vintex-backend", "freellmapi"])
  name     = each.value
}

module "services" {
  count      = local.shared ? 0 : 1
  source     = "../modules/staging_services"
  account_id = var.expected_account_id
}

module "host" {
  count               = local.shared ? 0 : 1
  source              = "../modules/staging_host"
  account_id          = var.expected_account_id
  vpc_id              = data.aws_vpc.shared[0].id
  subnet_id           = data.aws_subnet.shared[0].id
  media_bucket        = module.services[0].media_bucket
  queue_arn           = module.services[0].queue_arn
  log_group_arns      = module.services[0].log_group_arns
  ecr_repository_arns = [for repository in data.aws_ecr_repository.shared : repository.arn]
}

module "scheduler" {
  count        = local.shared ? 0 : 1
  source       = "../modules/staging_schedule"
  account_id   = var.expected_account_id
  instance_id  = module.host[0].instance_id
  instance_arn = module.host[0].instance_arn
}
