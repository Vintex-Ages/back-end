resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${var.name_prefix}-vpc" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-igw" }
}

resource "aws_subnet" "egress" {
  for_each = {
    for index, zone in var.availability_zones : zone => var.public_subnet_cidrs[index]
  }

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = each.value
  map_public_ip_on_launch = false

  tags = { Name = "${var.name_prefix}-egress-${each.key}" }
}

resource "aws_route_table" "egress" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-egress" }
}

resource "aws_route" "internet" {
  route_table_id         = aws_route_table.egress.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "egress" {
  for_each = aws_subnet.egress

  subnet_id      = each.value.id
  route_table_id = aws_route_table.egress.id
}

# Nenhum security group recebe ingress público. O VPC Link alcança somente a
# porta privada da API; o worker não recebe conexões de entrada.
resource "aws_security_group" "api" {
  name        = "${var.name_prefix}-api"
  description = "API acessivel somente pelo VPC Link"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-api" }
}

resource "aws_security_group" "worker" {
  name        = "${var.name_prefix}-worker"
  description = "Worker sem ingress"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-worker" }
}

resource "aws_security_group" "vpc_link" {
  name        = "${var.name_prefix}-vpc-link"
  description = "VPC Link acessa somente a porta privada da API"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-vpc-link" }
}

resource "aws_vpc_security_group_ingress_rule" "api_from_vpc_link" {
  security_group_id            = aws_security_group.api.id
  referenced_security_group_id = aws_security_group.vpc_link.id
  ip_protocol                  = "tcp"
  from_port                    = var.api_port
  to_port                      = var.api_port
  description                  = "Somente VPC Link para API"
}

resource "aws_vpc_security_group_egress_rule" "vpc_link_to_api" {
  security_group_id            = aws_security_group.vpc_link.id
  referenced_security_group_id = aws_security_group.api.id
  ip_protocol                  = "tcp"
  from_port                    = var.api_port
  to_port                      = var.api_port
  description                  = "Somente API privada"
}

resource "aws_vpc_security_group_egress_rule" "api_https" {
  security_group_id = aws_security_group.api.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "HTTPS de saida"
}

resource "aws_vpc_security_group_egress_rule" "worker_https" {
  security_group_id = aws_security_group.worker.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "HTTPS de saida"
}
