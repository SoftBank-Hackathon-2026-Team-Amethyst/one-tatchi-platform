# Runtime Status API

EKS, GKE, K3s의 **현재 BE Pod 목록과 사용량**을 조회한다. Pod 존재 여부는 Kubernetes API,
CPU·메모리는 Metrics API(`kubectl top`과 같은 데이터)에서 읽는다. Prometheus 이력 수집·HPA 설정은 유지한다.

## 설치와 릴리스

1. 플랫폼 PR을 머지한 뒤 새 semver 태그를 릴리스한다. `release.yml`은 amd64/arm64 이미지를 먼저
   게시하고 OCI index digest를 `runtime-status` Chart 기본값에 고정해 패키징한다.
2. 앱의 기존 template-update 절차로 **실제로 발행된 태그**의 워크플로·App Chart를 참조한다.
   릴리스 전 브랜치나 아직 없는 태그를 운영 입력으로 쓰지 않는다.
3. 앱 `.deploy/config.yaml`에 `runtime_status_values: deploy/values-runtime-status.yaml`을 추가한다.
   해당 값 파일에는 `serviceName: demo-app-be`를 넣는다. workflow 입력 `runtime-status-values`가
   있으면 config 경로보다 우선한다. 두 값 모두 비어 있으면 기존 배포와 같다.
4. FE 값에는 `podNamespaceEnv: true`를 켠다. App Chart가 `POD_NAMESPACE`를 Downward API로 제공한다.
   같은 이름을 `.Values.env`에 중복 지정하지 않는다. FE는 `/api/runtime`만 조회 서비스로 프록시한다.
5. test의 런타임 API를 확인하고 AWS·GCP·온프레미스 각각 검증한 뒤 prod에 적용한다.

조회 Chart는 앱 rollout 직전에 namespace마다 `runtime-status` 릴리스로 설치된다.
`serviceName`은 Chart 렌더링 시 고정되며 브라우저로부터 namespace나 selector를 받지 않는다.
이 v1은 namespace당 BE 서비스 하나를 지원한다. 서비스가 여러 개인 경우 Chart 확장이 필요하다.

## API 계약

`GET /api/runtime`은 `inventoryStatus`, `inventoryObservedAt`, `pods[]`를 반환한다.
각 Pod은 `uid/name/version/revision`, `trafficRole`(active/preview/inactive),
`phase/ready/terminating/restartCount`, `resources`, `metrics`를 가진다.

- 목록은 5초, 사용량은 15초마다 독립 수집하고 요청에는 캐시만 반환한다. 각 Kubernetes 요청 제한은 3초다.
- `resources`는 `cpuRequestMillicores/cpuLimitMillicores/memoryRequestBytes/memoryLimitBytes`다.
  일반 컨테이너·일반 사이드카를 합산하고, 한 컨테이너라도 설정이 없으면 해당 합계는 null이다.
  init container, Pod overhead, 노드 사용량은 합산하지 않는다.
- `metrics`는 `status/observedAt/windowSeconds/cpuMillicores/memoryBytes`다.
  CPU는 측정 구간 평균 millicores, 메모리는 working set bytes다. Node.js RSS나 heap 사용량과 다르다.
  일부 컨테이너 메트릭이 없으면 전체 사용량을 null로 표시한다.
- 조회 실패 또는 목록 15초·메트릭 45초 초과 시 `stale`이다. 실패 시 마지막 성공 데이터를 유지한다.
  최초 목록 조회도 실패하면 503, 목록은 있고 메트릭만 없으면 200과 `unavailable`/null을 반환한다.
  성공한 빈 목록만 실제 Pod 없음으로 취급한다.
- UID가 바뀌면 이전 캐시를 버린다. 메트릭 구간이 새 Pod 생성 전과 겹치면 그 샘플을 사용하지 않는다.
- active·preview Service의 selector로 역할을 판정한다. selector가 같으면 active를 우선한다.
  보존 중인 이전 revision, Pending, NotReady, Terminating Pod도 목록에 남긴다.
- 버전은 App Chart의 `one-tatchi.dev/app-version` annotation으로 읽는다. 이전 Pod은 null일 수 있다.
- `/healthz`는 프로세스 생존만 검사한다. upstream 장애를 이유로 재시작해서 캐시를 지우지 않는다.

목록 조회 권한은 Kubernetes RBAC 특성상 namespace 전체 Pod에 적용된다. 서비스가 서버에서 라벨을
필터링하고 API 응답은 허용 필드로 재구성한다. 원본 Pod spec·환경변수·Secret·노드 정보·상세 인증 오류는
외부 응답에 포함하지 않는다. 조회 서비스는 전용 ServiceAccount를 사용하고 일반 앱의 토큰 mount는 꺼 둔다.

## 플랫폼별 Metrics API 점검

- AWS: 현재 `cluster_addons/aws`의 Metrics Server Helm 설치를 재사용한다.
- GCP: GKE 관리 Metrics Server를 사용하며 별도로 설치하지 않는다.
- 온프레미스: K3s 기본 Metrics Server를 사용한다. `onpremctl doctor/status`도 API 응답을 확인한다.

각 클러스터의 kubecontext를 선택한 뒤 다음을 실행한다.

```sh
python3 scripts/onprem/resource_metrics.py --namespace test --wait-seconds 90
kubectl top pods -n test --containers
kubectl auth can-i list pods --as=system:serviceaccount:test:runtime-status -n test
kubectl auth can-i list pods --as=system:serviceaccount:test:runtime-status -n prod # no
kubectl auth can-i get secrets --as=system:serviceaccount:test:runtime-status -n test # no
```

Metrics API가 없으면 배포 단계는 경고를 남기고 Pod 목록만 제공한다.
인증서 오류는 CA·serving certificate·접근 경로를 고친다. TLS 검증을 끄거나 Metrics Server를 중복 설치하지 않는다.

## 검증

`npm test --prefix runtime-status`, `npm run lint --prefix runtime-status`,
`python3 -B -m unittest discover -s charts/runtime-status/tests -v`,
`python3 -B -m unittest discover -s scripts/onprem/tests -p test_resource_metrics.py -v`.
CI는 Chart 렌더링·IaC 검사·컨테이너 이미지 검사도 수행한다.
실제 세 클러스터의 조회, 부하 변화, 스케일 변경, Blue·Green 전환은 릴리스 이후 test에서 검증한다.
