terraform {
  required_version = ">= 1.16"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.66.0"
    }
  }
  # Bucket, key and account are supplied at init, never credentials.
  backend "s3" {}
}
