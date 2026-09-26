output "bucket_name" {
  description = "Bucket privado de mídia."
  value       = aws_s3_bucket.media.bucket
}

output "prefixes" {
  description = "Prefixos lógicos propostos para fotos, vídeos curtos e comprovantes Pix."
  value = {
    photo   = "products/photos/"
    video   = "products/videos/"
    receipt = "payments/receipts/"
  }
}

output "public_access_block" {
  description = "Configuração do bloqueio de acesso público do bucket."
  value = {
    block_public_acls       = aws_s3_bucket_public_access_block.media.block_public_acls
    block_public_policy     = aws_s3_bucket_public_access_block.media.block_public_policy
    ignore_public_acls      = aws_s3_bucket_public_access_block.media.ignore_public_acls
    restrict_public_buckets = aws_s3_bucket_public_access_block.media.restrict_public_buckets
  }
}
