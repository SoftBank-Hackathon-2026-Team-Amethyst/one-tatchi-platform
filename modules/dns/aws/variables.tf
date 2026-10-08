variable "domain_name" {
  description = "서비스 도메인. 운영은 이 이름, 테스트는 yolo.<이 이름>. 상위 DNS에서 이 이름을 출력값 name_servers로 위임한다"
  type        = string
}
