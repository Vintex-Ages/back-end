terraform {
  required_version = ">= 1.16"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.66.0"
    }
  }

  # O responsável fornece bucket e allowed_account_ids via arquivo local.
  # O bucket é pré-criado, versionado, privado e criptografado.
  backend "s3" {
    key          = "vintex/shared/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }
}
