# 관리형 서비스 없이 맥북의 Docker 안에 k3s를 띄운다 (k3d).
# k3d를 다루는 공식 provider가 없어 CLI를 호출한다. 이름이 바뀌면 지우고 다시 만든다.
resource "terraform_data" "cluster" {
  input = {
    name     = var.name
    image    = "rancher/k3s:${var.kubernetes_version}"
    agents   = var.node_count
    api_port = var.api_port
  }

  provisioner "local-exec" {
    # 외부 노출은 Cloudflare Tunnel(cluster_addons)이 맡으므로 Traefik · ServiceLB는 끈다.
    # 노드 컨테이너는 Docker가 다시 켜질 때 같이 살아난다(restart unless-stopped).
    command = <<-EOT
      k3d cluster get ${self.input.name} >/dev/null 2>&1 || k3d cluster create ${self.input.name} \
        --image ${self.input.image} \
        --agents ${self.input.agents} \
        --api-port 127.0.0.1:${self.input.api_port} \
        --k3s-arg "--disable=traefik@server:*" \
        --k3s-arg "--disable=servicelb@server:*" \
        --kubeconfig-update-default=false \
        --kubeconfig-switch-context=false \
        --wait
    EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = "k3d cluster delete ${self.input.name}"
  }
}
