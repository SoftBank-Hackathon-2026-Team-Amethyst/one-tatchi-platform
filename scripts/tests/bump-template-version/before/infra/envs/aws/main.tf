module "network" {
  source = "git::https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform.git//modules/network/aws?ref=v1.0.0"
}

module "cluster" {
  source = "git::https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform.git//modules/cluster/aws?ref=v1.0.0"
}

# 다른 레포 참조는 바뀌면 안 된다
module "other" {
  source = "git::https://github.com/example/other-modules.git//vpc?ref=v1.0.0"
}
