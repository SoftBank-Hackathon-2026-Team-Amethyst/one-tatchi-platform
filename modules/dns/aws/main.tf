# 서비스 도메인의 DNS 존과 와일드카드 인증서.
# 레코드(<도메인>, yolo.<도메인> → ALB)는 cluster_addons의 external-dns가 Ingress host를 보고 만든다.
# 인증서는 LB Controller가 Ingress host로 찾아 붙이므로 ARN을 넘길 필요가 없다.
#
# 인증서 검증은 위임이 끝나야 완료된다. 처음에는 존만 만들고(-target=…aws_route53_zone.this),
# 상위 DNS에 name_servers를 등록한 뒤 나머지를 apply한다.

resource "aws_route53_zone" "this" {
  name = var.domain_name
}

resource "aws_acm_certificate" "this" {
  domain_name               = var.domain_name
  subject_alternative_names = ["*.${var.domain_name}"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# 키는 plan 때 알 수 있는 도메인 이름으로 잡는다(레코드 이름은 인증서가 생겨야 나온다).
# <도메인>과 *.<도메인>은 같은 검증 레코드를 쓰므로 allow_overwrite로 겹침을 허용한다.
resource "aws_route53_record" "validation" {
  for_each = {
    for o in aws_acm_certificate.this.domain_validation_options : o.domain_name => {
      name   = o.resource_record_name
      type   = o.resource_record_type
      record = o.resource_record_value
    }
  }

  zone_id         = aws_route53_zone.this.zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "this" {
  certificate_arn         = aws_acm_certificate.this.arn
  validation_record_fqdns = [for r in aws_route53_record.validation : r.fqdn]
}
