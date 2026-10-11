# 온프레미스 기기 설정 가이드

온프레미스 기기(맥북 · Linux · WSL)를 demo-app 배포 대상으로 연결하는 순서다. 처음 기기를 붙일 때와, 이미 붙은 기기의 배포가 실패할 때 이 문서를 따른다.

명령과 운영 규칙의 자세한 설명은 [맥북 온프레미스 운영](../scripts/onprem/README.md)에 있다. 이 문서는 순서와 확인 방법만 다룬다.

## 0. 이름 정하기

기기 하나는 아래 다섯 이름을 가진다. **다섯 이름이 서로 맞아야 배포가 된다.** 배포가 `kube-access` 단계에서 실패하면 대부분 이 표가 어긋난 경우다.

| 이름 | 어디에 쓰나 | 기본 맥북 | 추가 맥북 | WSL |
|---|---|---|---|---|
| profile | `config.json`의 `profile` | `default` | `secondary` | `wsl` |
| cluster | k3d 클러스터 이름, `config.json`의 `cluster` | `onetouch` | `onetouch-hyeongrae` | `onetouch-wsl` |
| kube context | `k3d-<cluster>` | `k3d-onetouch` | `k3d-onetouch-hyeongrae` | `k3d-onetouch-wsl` |
| runner 라벨 | self-hosted runner의 고유 라벨 | `onprem` | `onprem-secondary` | `onprem-wsl` |
| 배포 대상 | 수동 실행 `target` · `targets`, `DEPLOY_TARGETS` | `onprem` | `onprem-secondary` | `onprem-wsl` |

- 표의 값은 지금 demo-app에 연결된 기기 기준이다(추가 맥북 · WSL의 profile은 예시). 새 기기는 같은 규칙으로 정한다.
- profile과 cluster는 사람 이름이 아니라 기기 식별자로 정한다. 이미 만든 클러스터는 이름을 바꾸거나 재생성하지 않는다.
- 기존 기기의 실제 값은 기기에서 `k3d cluster list`와 `kubectl config get-contexts`로 확인한다.

## 1. 준비물

| 항목 | 확인 명령 |
|---|---|
| Python 3.9+ | `python3 --version` |
| Docker (macOS는 Docker Desktop) | `docker info` |
| k3d · kubectl | `k3d version`, `kubectl version --client` |
| Terraform 1.11+ · Helm 4 | `terraform version`, `helm version` |
| jq · yq v4 · gh | `jq --version`, `yq --version`, `gh --version` |

macOS는 충전기 연결, 덮개 열림, 로그인 유지 상태로 둔다. 잠자기 방지는 아래 4단계에서 설치하는 서비스가 맡는다.

## 2. runner 등록

1. demo-app → **Settings → Actions → Runners → New self-hosted runner** 안내대로 공식 runner를 내려받는다.
2. 설치 경로와 작업 경로에 **공백을 넣지 않는다.** 예: `~/.local/share/one-tatchi/runners/wsl`
3. `./config.sh`에서 0단계의 **runner 라벨**을 추가 라벨로 넣는다. 기본 라벨(`self-hosted`, OS, 아키텍처)은 그대로 둔다.
4. macOS에서는 `svc.sh install`을 실행하지 않는다. 4단계의 서비스가 runner를 띄운다.

확인: demo-app의 Runners 화면에 기기가 `Idle`로 보이고 라벨이 맞다.

```bash
gh api repos/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runners \
  -q '.runners[] | .name + " " + .status + " " + ([.labels[].name] | join(","))'
```

## 3. 클러스터와 인프라

`config.json`을 만든다. 비밀값은 넣지 않는다. 형식과 필드는 [운영 문서의 기기별 준비](../scripts/onprem/README.md#기기별-준비)를 따른다.

```bash
python3 scripts/onprem/onpremctl.py --config /absolute/path/config.json terraform init
python3 scripts/onprem/onpremctl.py --config /absolute/path/config.json terraform apply -target=module.cluster
python3 scripts/onprem/onpremctl.py --config /absolute/path/config.json terraform apply -target=module.cluster_addons
python3 scripts/onprem/onpremctl.py --config /absolute/path/config.json terraform apply
```

- 처음 두 `-target`은 새 클러스터를 만들 때만 쓴다.
- 이미 클러스터가 있는 기기는 **기존 state가 있는 루트**를 지정한다. 클러스터는 있는데 state가 없으면 멈추고 원본 state부터 찾는다.

확인: `kubectl --context k3d-<cluster> get pods -A`에서 DB와 cloudflared가 `Running`이다.

## 4. runner 환경변수 (가장 자주 틀리는 단계)

배포 job은 runner의 환경변수 `ONPREM_CLUSTER`가 배포하려는 클러스터와 같은지 확인한다(`kube-access`). 값은 **`k3d-`를 뺀 cluster 이름**이다.

### macOS: 관리 서비스로 설치

```bash
python3 scripts/onprem/onpremctl.py --config /absolute/path/config.json install
```

LaunchAgent가 runner를 띄우면서 `ONPREM_CLUSTER`(= `config.json`의 `cluster`)와 `ONPREM_PROFILE`을 넣는다. 잠자기 방지 · 재부팅 복구 · 터널 주소 갱신 서비스도 함께 설치된다.

**runner를 `./run.sh`나 공식 `svc.sh`로 직접 띄우면 이 값이 없다.** 그러면 배포가 `selected cluster differs from installed runner profile`로 실패한다. 직접 띄운 runner는 멈추고 `install`로 다시 띄운다.

```bash
./svc.sh stop && ./svc.sh uninstall   # 공식 서비스로 띄운 적이 있으면
python3 "$HOME/Library/Application Support/one-tatchi/onprem/<profile>/bin/onpremctl.py" \
  --config "$HOME/Library/Application Support/one-tatchi/onprem/<profile>/config.json" status
```

### Linux · WSL: runner의 `.env`

`onpremctl install`은 macOS 전용이다. runner 디렉터리의 `.env`에 직접 적고 runner를 다시 시작한다.

```bash
cd ~/.local/share/one-tatchi/runners/wsl
cat >> .env <<'EOF'
ONPREM_CLUSTER=onetouch-wsl
ONPREM_PROFILE=wsl
EOF
sudo ./svc.sh stop && sudo ./svc.sh start   # 서비스로 띄웠을 때. 직접 띄웠으면 run.sh를 다시 실행
```

확인: 배포 로그의 `kube-access` 단계를 지나 `kubectl cluster-info`까지 성공한다. 미리 확인하려면 runner와 같은 사용자로 `kubectl --context k3d-<cluster> cluster-info`를 실행한다.

## 5. GitHub 변수와 배포 대상

demo-app의 **Settings → Secrets and variables → Actions → Variables**에 kube context를 넣는다.

| 기기 | 변수 | 값 |
|---|---|---|
| 기본 맥북 | `ONPREM_CLUSTER` | `k3d-onetouch` (없으면 이 값이 기본값) |
| 추가 맥북 | `ONPREM_SECONDARY_CLUSTER` | `k3d-onetouch-hyeongrae` |
| WSL | `ONPREM_WSL_CLUSTER` | `k3d-onetouch-wsl` |

변수 값은 4단계 runner 환경변수 앞에 `k3d-`를 붙인 값과 같아야 한다.

**새 종류의 기기를 추가할 때**는 demo-app `.github/scripts/deploy-targets.sh`에 배포 대상 한 줄(cluster 변수 · runner 라벨 · green 미리보기 여부)을 추가하고, `deploy.yml`과 `rollout.yml`의 `target` 선택지에 이름을 넣는다. 회귀 테스트(`.github/tests`)에도 경우를 더한다.

## 6. 배포 확인

먼저 이 기기 하나로 수동 실행해 본다. 레포 변수는 바꾸지 않는다.

```bash
gh workflow run deploy.yml -R SoftBank-Hackathon-2026-Team-Amethyst/demo-app --ref main \
  -f target=onprem-wsl -f environment=test
```

- 같은 커밋으로 이미 실행한 적이 있으면 publish가 `existing tag has different digest`로 실패한다. 새 커밋에서 실행한다.
- 성공하면 Slack 알림과 실행 요약에 test 주소(`https://<임의>.trycloudflare.com`)가 나온다. 기기에서 `onpremctl.py … status`로도 현재 주소를 볼 수 있다.
- main은 수동 승격이다. Slack의 승격 버튼을 눌러야 green이 운영 트래픽을 받는다.

## 7. 여러 대상 동시 배포에 넣기

기기 하나로 test · prod가 모두 성공한 뒤에 넣는다. 방법은 둘이다.

| 방법 | 영향 |
|---|---|
| 수동 실행 `targets=aws,gcp,onprem` | 이번 실행만. 레포 변수는 그대로 |
| 레포 변수 `DEPLOY_TARGETS=aws,gcp,onprem` | **팀 전체의 push 배포**가 모든 대상으로 간다. 바꾸기 전에 팀에 알린다 |

모든 대상의 test가 통과해야 prod로 간다([ADR-0020](adr/0020-multi-target-deploy.md)). 그래서 이 기기가 꺼져 있거나 설정이 틀리면 **다른 대상의 운영 반영도 멈춘다.** 기기를 오래 끌 때는 목록에서 먼저 뺀다.

## 8. 고정 주소와 green 미리보기 (진행 중)

지금은 Quick Tunnel이라 재시작하면 주소가 바뀌고, green 미리보기는 열리지 않는다. 고정 주소는 `T31`(onprem 항목)에서 Named Tunnel로 바꾼다.

| 용도 | prod | test |
|---|---|---|
| 서비스 | `onetatchi-onprem.soulee.dev` | `yolo-onetatchi-onprem.soulee.dev` |
| green 미리보기 | `green-onetatchi-onprem.soulee.dev` | `green-yolo-onetatchi-onprem.soulee.dev` |

순서:

1. Cloudflare Zero Trust → **Networks → Tunnels**에서 환경마다 터널을 만들고 토큰을 받는다.
2. 기기의 클러스터에 토큰 Secret(키 `token`)을 넣고, Terraform `tunnels`의 `token_secret`에 그 Secret 이름을 준다.
3. 터널의 **Public Hostname**을 두 개 붙인다. 서비스 주소 → FE Service, green 주소 → `<release>-preview-auth` Service.
4. Cognito 앱 클라이언트에 green 주소의 콜백 URL을 추가한다(`infra/envs/aws`).

green 주소가 `530`을 돌려주면 Cloudflare에 호스트는 있지만 연결된 터널(cloudflared)이 없다는 뜻이다. 2 · 3단계를 확인한다.

## 문제 해결

| 증상 (로그 · 화면) | 원인 | 해결 |
|---|---|---|
| `selected cluster differs from installed runner profile` | runner에 `ONPREM_CLUSTER`가 없거나 GitHub 변수와 다르다 | 4단계. macOS는 `onpremctl install`로 runner를 띄우고, Linux · WSL은 `.env`를 고친다. 5단계 변수와 맞춘다 |
| `onprem requires k3d context` | GitHub 변수에 `k3d-`가 빠졌다 | 5단계 값을 `k3d-<cluster>`로 |
| `onprem device and runner label differ` | 배포 대상과 runner 라벨이 다르다 | 2단계 라벨과 0단계 표를 맞춘다 |
| job이 `Queued`에서 움직이지 않는다 | 그 라벨의 runner가 꺼져 있거나 다른 job을 실행 중이다 | 2단계 확인 명령으로 `online`인지 본다. macOS는 `onpremctl … status` |
| `existing tag has different digest` | 같은 커밋으로 다시 빌드했다 | 새 커밋에서 실행하거나, 실패한 배포 job만 다시 실행한다 |
| 서비스 주소가 바뀌었다 | Quick Tunnel 재시작 | `onpremctl … status` 또는 `refresh-urls`로 현재 주소 확인. 고정은 8단계 |
| green 주소 `530` | Named Tunnel이 없거나 Public Hostname이 없다 | 8단계 |
