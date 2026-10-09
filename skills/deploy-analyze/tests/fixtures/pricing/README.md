# AWS Pricing 응답 픽스처

AWS GetProducts의 product · terms · priceDimensions 형태를 따른 합성 응답이다. SKU, 단가, 사용 유형과 적용 시점은 테스트용이며 실제 조회 근거나 현재 가격이 아니다.

- ec2.json: 서울 Linux · Shared t3.medium 시간 요금.
- rds.json: 서울 PostgreSQL · Single-AZ db.t4g.micro 시간 요금.
- ecr-storage.json: GB-Mo 저장소 요금.
- logs-tiered.json: GB 단위 구간 요금.

테스트는 boto3 클라이언트에 botocore Stubber를 연결하거나 클라이언트를 대체한다. AWS 자격증명이나 네트워크가 필요하지 않다. 실제 가격 조회와 보고서 대조는 T16 C7의 별도 검증이다.
