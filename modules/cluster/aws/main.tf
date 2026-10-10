locals {
  admin_entries = {
    for arn in var.admin_principal_arns : "admin-${md5(arn)}" => {
      principal_arn = arn
      policy_associations = {
        admin = {
          policy_arn   = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = { type = "cluster" }
        }
      }
    }
  }
  # helm_release plan은 릴리스 정보가 든 Secret을 읽어야 해서 AdminView(시크릿 포함 읽기)를 준다.
  viewer_entries = {
    for arn in var.viewer_principal_arns : "viewer-${md5(arn)}" => {
      principal_arn = arn
      policy_associations = {
        view = {
          policy_arn   = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSAdminViewPolicy"
          access_scope = { type = "cluster" }
        }
      }
    }
  }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.26"

  name               = var.name
  kubernetes_version = var.kubernetes_version

  vpc_id     = var.network_id
  subnet_ids = var.subnet_ids

  endpoint_public_access = true
  # 누가 apply했는지와 무관하게 권한이 같도록 생성자 자동 권한은 끄고 명시적으로 준다.
  enable_cluster_creator_admin_permissions = false
  access_entries                           = merge(local.admin_entries, local.viewer_entries)

  # plan/apply 실행자 대신 지정된 관리자에게 KMS 관리 권한을 고정한다.
  kms_key_administrators = var.admin_principal_arns

  addons = {
    # NetworkPolicy 적용(T30 · T33). 켜도 정책이 없으면 전처럼 모두 허용이다.
    vpc-cni                = { before_compute = true, configuration_values = jsonencode({ enableNetworkPolicy = "true" }) }
    eks-pod-identity-agent = { before_compute = true }
    kube-proxy             = {}
    coredns                = {}
  }

  eks_managed_node_groups = {
    default = {
      ami_type       = "AL2023_x86_64_STANDARD"
      instance_types = var.node_instance_types
      min_size       = var.node_count.min
      desired_size   = var.node_count.desired
      max_size       = var.node_count.max
    }
  }
}

locals {
  cluster_autoscaler_asg_tags = {
    "k8s.io/cluster-autoscaler/enabled"     = "true"
    "k8s.io/cluster-autoscaler/${var.name}" = "owned"
  }
}

resource "aws_autoscaling_group_tag" "cluster_autoscaler" {
  for_each = local.cluster_autoscaler_asg_tags

  autoscaling_group_name = module.eks.eks_managed_node_groups["default"].node_group_autoscaling_group_names[0]
  tag {
    key                 = each.key
    value               = each.value
    propagate_at_launch = false
  }
}
