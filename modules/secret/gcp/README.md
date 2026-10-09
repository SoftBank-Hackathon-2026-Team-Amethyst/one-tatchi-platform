# secret/gcp

`names`의 각 이름으로 Secret Manager 시크릿만 만든다. 값은 외부에서 등록하며 Terraform이 읽거나 저장하지 않는다. `secret_ids`는 이름별 시크릿 이름을 반환한다. DB 자격증명 생성은 `database/gcp`가 맡는다.
