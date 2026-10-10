output "issuer_url" {
  description = "App Chart previewAuth.issuerUrl"
  value       = "https://cognito-idp.${data.aws_region.current.region}.amazonaws.com/${aws_cognito_user_pool.this.id}"
}

output "secret_id" {
  description = "App Chart previewAuth.remoteKey. External Secrets 읽기 허용 목록(cluster_addons readable_secret_arns)에도 넣는다"
  value       = aws_secretsmanager_secret.this.arn
}

output "saml_acs_url" {
  description = "IdP SAML 앱의 ACS URL"
  value       = "https://${aws_cognito_user_pool_domain.this.domain}.auth.${data.aws_region.current.region}.amazoncognito.com/saml2/idpresponse"
}

output "saml_audience" {
  description = "IdP SAML 앱의 Audience (SP entity ID)"
  value       = "urn:amazon:cognito:sp:${aws_cognito_user_pool.this.id}"
}
