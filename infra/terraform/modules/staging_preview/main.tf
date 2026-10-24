# IP fixo da instância: o DNS público dela muda a cada stop/start (Scheduler
# 10h-22h), e o CloudFront precisa de um nome de origem estável. A cobrança do
# IPv4 público é por hora, com a instância ligada ou não.
resource "aws_eip" "preview" {
  domain = "vpc"
  tags = {
    Name        = "vintex-staging-preview"
    Environment = "staging"
    Project     = "Vintex"
  }
}

resource "aws_eip_association" "preview" {
  instance_id   = var.instance_id
  allocation_id = aws_eip.preview.id
}
