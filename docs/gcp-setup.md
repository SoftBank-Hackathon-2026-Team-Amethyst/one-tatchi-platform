# GCP 접속 설정

팀원이 자기 구글 계정으로 GCP 콘솔과 CLI를 쓰는 방법. 서비스 계정 키(JSON)는 만들지 않고, 각자 `gcloud` 로그인으로만 쓴다. GitHub Actions는 Workload Identity Federation으로 들어간다(T4).

## 프로젝트

| 항목 | 값 |
|---|---|
| 프로젝트 ID | `one-tatchi-gejkm` |
| 콘솔 | https://console.cloud.google.com/home/dashboard?project=one-tatchi-gejkm |
| 작업 리전 | `asia-northeast3` (서울) |
| 결제 | 원가연의 해커톤 결제 계정 |
| 켜 둔 API | Compute, GKE, Cloud SQL, Artifact Registry, Secret Manager, IAM · IAM Credentials · STS(Workload Identity), Resource Manager, Service Networking, Monitoring, Logging, Billing Budgets |

## 권한

| 이름 | 구글 계정 | 역할 | 이유 |
|---|---|---|---|
| 원가연 | (프로젝트 소유자) | Owner | 프로젝트 · 결제 관리 |
| 배규태 | `bktpbktp@gmail.com` | Owner | T4(GCP 구현체) 담당. 서비스 계정 · IAM까지 Terraform으로 만든다 |
| 이소울 | `alus20x@gmail.com` | Editor | 리소스 생성 · 조회. 권한 변경은 못 한다 |
| 김형래 | `hyeongrae.99@gmail.com` | Editor | 위와 같음 |
| 배준범 | (계정 없음) | — | 필요하면 구글 계정을 만들어 원가연에게 요청 |

권한 변경은 원가연에게 요청한다. Owner는 초대 메일을 **수락해야** 적용된다.

## 1. gcloud 설치

```bash
gcloud --version   # Google Cloud SDK x.y.z 이면 통과
```

없으면 설치한다.

- macOS: `brew install --cask gcloud-cli`
- Windows: `winget install Google.CloudSDK`
- Linux / WSL: [설치 안내](https://cloud.google.com/sdk/docs/install)

## 2. 로그인과 기본값

```bash
gcloud auth login                              # 브라우저에서 위 표의 내 구글 계정으로 로그인
gcloud auth application-default login          # Terraform 등 도구가 쓸 자격증명
gcloud config set project one-tatchi-gejkm
gcloud config set compute/region asia-northeast3
```

## 3. 확인

```bash
gcloud projects describe one-tatchi-gejkm --format='value(projectId,lifecycleState)'
# one-tatchi-gejkm  ACTIVE 이면 끝
```

## 매일 쓰기

```bash
# GKE 접속 (클러스터가 생긴 뒤)
gcloud container clusters get-credentials <클러스터> --region asia-northeast3

# 다른 GCP 프로젝트와 섞어 쓰면 설정을 따로 둔다
gcloud config configurations create onetatchi
gcloud config configurations activate onetatchi
```

Terraform은 `application-default` 자격증명을 그대로 쓴다.

## 규칙

- **서비스 계정 키(JSON)를 만들지 않는다.** CI는 Workload Identity Federation, 사람은 `gcloud` 로그인으로만 쓴다.
- **자격증명을 공유하지 않는다.** `~/.config/gcloud` 내용, 토큰을 채팅이나 레포에 올리지 않는다.
- **서울 리전만 쓴다.** `asia-northeast3`
- **비용을 확인한다.** 안 쓰는 GKE 노드 · Cloud SQL은 꺼 두거나 지운다.

## 문제 해결

| 증상 | 해결 |
|---|---|
| `PERMISSION_DENIED` | 권한 할당 전이거나 Owner 초대를 아직 수락하지 않았다. 메일함 확인, 원가연에게 요청 |
| `API ... has not been used in project` | 위 표에 없는 API다. 원가연에게 켜 달라고 요청 |
| Terraform이 `could not find default credentials` | `gcloud auth application-default login` |
| 다른 프로젝트에 리소스가 생김 | `gcloud config get-value project`로 현재 프로젝트 확인 |
