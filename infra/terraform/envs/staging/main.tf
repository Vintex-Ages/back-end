locals {
  aws_region = "us-east-2"
}

provider "aws" {
  region              = local.aws_region
  allowed_account_ids = [var.expected_account_id]
  default_tags {
    tags = {
      Project     = "Vintex"
      Environment = "staging"
      ManagedBy   = "Terraform"
    }
  }
}

data "aws_vpc" "shared" {
  id = var.shared_vpc_id
  lifecycle {
    postcondition {
      condition     = self.owner_id == var.expected_account_id && lookup(self.tags, "Environment", "") == "shared" && lookup(self.tags, "Project", "") == "Vintex"
      error_message = "A VPC deve pertencer à conta e à base shared Vintex."
    }
  }
}

data "aws_subnet" "shared" {
  id = var.shared_public_subnet_id
  lifecycle {
    postcondition {
      condition     = self.vpc_id == var.shared_vpc_id && self.owner_id == var.expected_account_id && self.map_public_ip_on_launch && lookup(self.tags, "Environment", "") == "shared"
      error_message = "A subnet pública deve pertencer à VPC shared e à conta esperada."
    }
  }
}

data "aws_ecr_repository" "shared" {
  for_each = toset(["vintex-backend", "freellmapi"])
  name     = each.value
}

module "services" {
  source     = "../../modules/staging_services"
  account_id = var.expected_account_id
}

module "host" {
  source              = "../../modules/staging_host"
  account_id          = var.expected_account_id
  vpc_id              = data.aws_vpc.shared.id
  subnet_id           = data.aws_subnet.shared.id
  media_bucket        = module.services.media_bucket
  queue_arn           = module.services.queue_arn
  log_group_arns      = module.services.log_group_arns
  ecr_repository_arns = [for repository in data.aws_ecr_repository.shared : repository.arn]
}

module "scheduler" {
  source       = "../../modules/staging_schedule"
  account_id   = var.expected_account_id
  instance_id  = module.host.instance_id
  instance_arn = module.host.instance_arn
}
