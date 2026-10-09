# cluster_addons/gcp

Argo Rollouts · External Secrets · 기존 platform-config 차트를 설치한다. Helm provider는 호출 루트가 GKE에 연결한다. `project_id`, `cluster_name`, `readable_secret_ids`를 전달한다.

External Secrets 전용 GCP 계정은 지정한 시크릿에만 읽기 권한을 가진다. Kubernetes 계정 `external-secrets/external-secrets`와 GKE Workload Identity로 연결하며 장기 키를 만들지 않는다. ClusterSecretStore는 컨트롤러의 인증을 사용하는 `gcpsm.projectID`로 설정한다. `count`는 처음 plan에서 시크릿 ID를 몰라도 목록 길이로 결정된다.

`secret_store_name = cloud-secrets`, `ingress_class = gce`를 반환한다. GKE 기본 Ingress 컨트롤러를 사용하므로 별도 LB 컨트롤러를 설치하지 않는다. GKE Ingress는 class 어노테이션을 사용한다. 실제 노출 설정은 앱 값 파일에 둔다. 대시보드는 외부 공개하지 않는다.
