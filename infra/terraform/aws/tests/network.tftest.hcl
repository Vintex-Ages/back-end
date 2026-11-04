mock_provider "aws" {}

run "rede_publica_ec2" {
  command = plan
  module {
    source = "../modules/shared_network"
  }
  variables {
    name_prefix       = "vintex-shared"
    vpc_cidr          = "10.80.0.0/16"
    subnet_cidr       = "10.80.1.0/24"
    availability_zone = "us-east-2a"
  }
  override_resource {
    target          = aws_vpc.this
    override_during = plan
    values          = { id = "vpc-test" }
  }
  override_resource {
    target          = aws_subnet.public
    override_during = plan
    values          = { id = "subnet-test" }
  }
  override_resource {
    target          = aws_internet_gateway.this
    override_during = plan
    values          = { id = "igw-test" }
  }
  override_resource {
    target          = aws_route_table.public
    override_during = plan
    values          = { id = "rtb-test" }
  }

  assert {
    condition     = aws_vpc.this.cidr_block == "10.80.0.0/16" && aws_vpc.this.enable_dns_support && aws_vpc.this.enable_dns_hostnames
    error_message = "A VPC deve ter CIDR dedicado e resolução DNS para SSM/ECR."
  }
  assert {
    condition = (aws_subnet.public.vpc_id == output.vpc_id && aws_subnet.public.cidr_block == "10.80.1.0/24" &&
    aws_subnet.public.availability_zone == "us-east-2a" && aws_subnet.public.map_public_ip_on_launch)
    error_message = "A subnet pública deve atribuir IP público aos hosts EC2 em Ohio."
  }
  assert {
    condition = (aws_route.internet.destination_cidr_block == "0.0.0.0/0" && aws_route.internet.gateway_id == aws_internet_gateway.this.id &&
    aws_route.internet.route_table_id == aws_route_table.public.id && aws_internet_gateway.this.vpc_id == output.vpc_id)
    error_message = "A saída pública deve usar a rota e o Internet Gateway da VPC."
  }
  assert {
    condition = (aws_route_table_association.public.subnet_id == output.public_subnet_id &&
    aws_route_table_association.public.route_table_id == aws_route_table.public.id)
    error_message = "A tabela de rotas pública deve estar associada à subnet."
  }
}
