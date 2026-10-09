# ci_identity/gcp

GitHub WIF의 plan/deploy provider와 서비스 계정을 만든다. 장기 키는 만들지 않는다. `project_id`, GitHub 숫자 `repository_id` · `repository_owner_id`, immutable `oidc_subject_prefix`, `state_bucket`을 입력한다.

출력 `plan_identity`와 `deploy_identity`는 서비스 계정 이메일이다. deploy 인증은 `workload_identity_provider`, plan 인증은 `plan_workload_identity_provider`를 사용한다. 상세 신뢰와 권한은 [ADR 0006](../../../docs/adr/0006-gcp-ci-state.md)을 따른다. bootstrap 외 다른 루트에서 이 모듈을 다시 만들지 않는다.
