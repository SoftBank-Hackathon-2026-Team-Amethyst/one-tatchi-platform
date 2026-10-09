# 0007: 같은 App Chart에서 GKE 기본 Ingress 사용

상태: 채택 (T4)

## 배경

기존 App Chart는 ALB 어노테이션과 IngressClass를 고정한다. GKE 기본 Ingress는 `kubernetes.io/ingress.class: gce` 어노테이션과 서비스 NEG 설정을 사용한다.

## 결정

- 공통 차트에 선택적인 `ingress.annotations` · `service.annotations`를 추가한다. 기존 기본값 `className: alb`와 ALB 생성 동작은 유지한다.
- ALB 어노테이션은 className이 alb일 때만 생성한다. GCP 값 파일은 className을 비우고 gce 및 NEG 어노테이션을 전달한다.
- 기존 FE → BE 내부 프록시는 유지하고 FE만 외부에 노출한다. active · preview는 GKE Ingress 두 개의 별도 IP를 사용한다. GCP에는 AWS 도메인 · ALB 그룹 값을 전달하지 않는다.
- 도메인이 없는 데모는 HTTP로 검증하며 기존 AWS HTTPS/DNS는 유지한다. 실제 개인정보를 처리하는 운영은 별도 도메인 · TLS 설정 후 사용한다.

## 영향

GCP에서는 LB가 active/preview와 test/prod별로 만들어지므로 추가 비용이 발생한다. 포트 8080으로 preview를 조회하는 AWS 주소 규칙을 GCP에 적용하지 않는다. 기존 AWS · onprem 렌더링과 새 GCP 렌더링을 비교해 공통 차트의 회귀를 확인한다.

참고: [GKE Ingress](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/load-balance-ingress).
