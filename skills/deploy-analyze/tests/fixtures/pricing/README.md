# AWS Pricing 응답 픽스처

AWS GetProducts의 product · terms · priceDimensions 형태를 따른 합성 응답이다. SKU, 단가, 사용 유형과 적용 시점은 테스트용이며 실제 조회 근거나 현재 가격이 아니다.

- ec2.json: 서울 Linux · Shared t3.medium 시간 요금.
- rds.json: 서울 PostgreSQL · Single-AZ db.t4g.micro 시간 요금.
- ecr-storage.json: GB-Mo 저장소 요금.
- logs-tiered.json: GB 단위 구간 요금.

테스트는 boto3 클라이언트에 botocore Stubber를 연결하거나 클라이언트를 대체한다. AWS 자격증명이나 네트워크가 필요하지 않다. 실제 가격 조회와 보고서 대조는 T16 C7의 별도 검증이다.

C3의 gcp/에는 서비스 목록, 서울 CPU · 메모리, 전역 클러스터 관리와 구간별 저장소 가격의 합성 Catalog 응답이 있다. 단가 · SKU · 카테고리는 실제 조회 근거가 아니다. 단위 변환 · Money 정밀도 · 스코프 보존 · API 오류는 네트워크 없이 검증한다.

C7의 direct-cpu-metadata.json과 direct-cpu-price.json은 2026-10-09 공식 Google v2beta API에서 조회한 서울 E2 공개 SKU 응답이다. 가격 변화와 무관한 정규화 회귀 테스트에 사용하며 현재 가격을 지속 보증하지 않는다. 인증정보는 포함하지 않는다.

mapping/aws-products.json과 mapping/gcp-skus.json은 같은 날 공개 가격 API에서 조회한 추가 과금 항목의 실제 응답이다. 로그·송신·IPv4·메트릭·시크릿·감사 저장소 및 GCP 기본 자원의 단위·서비스 연결을 재현한다. 무료 구간은 원본 그대로 보존하고 검증되지 않은 무료 적용을 차단하는 테스트에 사용한다. 계정·토큰·시크릿 값은 포함하지 않는다.
