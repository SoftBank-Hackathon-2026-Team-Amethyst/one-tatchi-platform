"""Project one verified cost result into the budget table and review summary."""

import copy
from decimal import Decimal, localcontext

from pricing_calculate import calculate, compare_costs
from pricing_contract import fields, input_hash, require, usage, string, utc_time

START = "<!-- pricing-summary:start -->"
END = "<!-- pricing-summary:end -->"
TARGETS = {"aws": "AWS", "gcp": "GCP", "onprem": "온프레미스"}
BUDGET = {"over": "예산 초과", "within": "예산 범위 안", "may_exceed": "예산 초과 가능", "unknown": "판정 미정"}
ISSUES = {
    "authentication_failed": "인증 실패", "permission_denied": "조회 권한 없음", "api_disabled": "가격 API 비활성",
    "timeout": "조회 시간 초과", "rate_limited": "조회 요청 제한", "not_found": "일치하는 가격 없음",
    "ambiguous_sku": "가격 후보를 하나로 확정하지 못함", "unsupported_resource": "미지원 자원 또는 과금 조건",
    "unsupported_unit": "미지원 과금 단위", "invalid_provider_response": "가격 응답 확인 실패",
    "unknown_usage": "월 사용량 또는 상한 미정", "unknown_incremental_usage": "앱 추가 사용량 또는 상관관계 미정",
    "unbounded_usage": "사용량 상한 미정", "unknown_capacity": "수용량·증설 검토 필요",
    "unknown_operating_cost": "온프레미스 운영 비용 미산정", "unconfirmed_catalog": "정확한 카탈로그 항목 미확인",
    "unsupported_aggregation": "월 합계로 처리할 수 없는 구간 집계", "unknown_aggregation_baseline": "계정·프로젝트의 기존 사용량 미정",
    "unknown_savings": "완전한 대안 견적이 없어 절감액 미산정",
}


def escaped(value):
    value = str(value).replace("\r", " ").replace("\n", " ")
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for char in ("\\", "|", "`", "*", "_", "[", "]"):
        value = value.replace(char, "\\" + char)
    return value


def number(value):
    text = format(Decimal(value), ",f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def money(value, currency="USD"):
    if value is None:
        return "미산정"
    def labelled(amount):
        return ("USD " + number(amount)) if currency == "USD" else number(amount) + "원"
    low, high = value["min"], value["max"]
    if high is None:
        return labelled(low) + " 이상 (상한 미정)"
    if Decimal(low) == Decimal(high):
        return labelled(low)
    return labelled(low) + " ~ " + labelled(high)


def total_text(candidate, incremental=False):
    summary = candidate["summary"]
    value = summary["known_incremental_usd" if incremental else "known_total_usd"]
    complete = summary["incremental_complete" if incremental else "total_complete"]
    formatted = money(value)
    return formatted if complete or value is None else "확인된 소계 " + formatted + "; 추가 비용 미정"


def verified_costs(data, prices, costs, assessment=None):
    expected = calculate(data, prices, assessment)
    require(isinstance(costs, dict), "costs: expected object")
    actual = copy.deepcopy(costs)
    require("generated_at" in actual, "costs: missing generation timestamp")
    utc_time(actual["generated_at"], "generated_at")
    actual.pop("generated_at")
    expected.pop("generated_at")
    require(actual == expected, "costs: stale or inconsistent calculation; rerun calculate")


def verified_savings(costs, alternative, savings):
    require((alternative is None) == (savings is None), "report: savings and alternative costs must be provided together")
    if savings is None:
        return {}
    expected = compare_costs(costs, alternative)
    require(isinstance(savings, dict) and "generated_at" in savings, "savings: invalid comparison result")
    actual = copy.deepcopy(savings); utc_time(actual["generated_at"], "savings.generated_at"); actual.pop("generated_at")
    expected.pop("generated_at")
    require(actual == expected, "savings: stale or inconsistent comparison; rerun compare")
    return {candidate["candidate_id"]: candidate for candidate in savings["candidates"]}


def warning(candidate):
    state = candidate["budget"]["status"]
    title = BUDGET[state]
    if state == "over":
        return title + ": " + "알려진 비용 하한만으로도 예산 상한을 넘습니다."
    if state == "may_exceed":
        return title + ": 사용량 범위에 따라 예산 상한을 넘을 수 있습니다."
    if state == "unknown":
        return title + ": 예산·환율·미산정 비용·구성 조건을 확인해야 합니다."
    return title + ": 완전하게 계산된 비교 범위의 비용 상한이 예산 상한 이하입니다."


def savings_text(candidate_id, savings):
    row = savings.get(candidate_id)
    if row is None:
        return "절감액 미산정: 별도 대안 견적이 없습니다. 노드·DB·NAT 등 큰 비용 항목의 대안을 검토하고, 가용성·규제 조건을 확인한 뒤 별도로 계산해야 합니다."
    if row["monthly_savings"] is None:
        return "절감액 미산정: 기준 또는 대안의 비교 범위가 완전하지 않습니다."
    return "대안 견적 대비 월 차액: " + money(row["monthly_savings"]) + " (음수는 대안 비용 증가; 자원 견적 차이이며 성능·운영 비용 검증은 별도)."


def recommendation_summary(candidate, prices, data, savings, costs_hash):
    cid = candidate["candidate_id"]
    scope = "전체 비용" if candidate["budget"]["basis"] == "total" else "앱 추가 증분 비용"
    lines = [START, "### 예상 월 비용", "",
             "- 배포 후보: " + TARGETS[candidate["target"]] + " (" + escaped(cid) + ")",
             "- 구성: " + ("명시된 구성" if candidate["configuration_status"] == "confirmed" else "가정이 포함된 구성"),
             "- 전체 자원 비용: " + total_text(candidate),
             "- 앱 추가 증분: " + total_text(candidate, True),
             "- 전체 원화: " + money(candidate["summary"]["total_krw"], "KRW"),
             "- 앱 추가 원화: " + money(candidate["summary"]["incremental_krw"], "KRW"),
             "- 예산 비교 범위: " + scope,
             "- " + warning(candidate),
             "- " + savings_text(cid, savings),
             "- 단가 조회/시도 시각 (UTC): " + prices["queried_at"],
             "- 입력·단가·계산 근거: " + input_hash(data)[:12] + " / " + input_hash(prices)[:12] + " / " + costs_hash[:12]]
    if data["fx"] is None:
        lines.append("- 환율: 미정. USD를 임의로 원화로 바꾸지 않았습니다.")
    else:
        fx = data["fx"]
        lines.append("- 환율: USD 1 = " + number(fx["usd_to_krw"]) + "원; 기준일 " + fx["as_of"] + "; 출처 " + escaped(fx["source"]))
    if candidate["target"] == "onprem":
        lines.append("- 온프레미스 클라우드 요금과 전기·장비·인건비를 구분합니다. 클라우드 0원이 전체 운영 비용 0원은 아닙니다.")
    lines.extend(["", END])
    return "\n".join(lines) + "\n"


def render_reports(data, prices, costs, candidate_id, assessment=None, alternative=None, savings=None):
    with localcontext() as context:
        context.prec = 80
        verified_costs(data, prices, costs, assessment)
        differences = verified_savings(costs, alternative, savings)
        by_id = {candidate["candidate_id"]: candidate for candidate in costs["candidates"]}
        require(candidate_id in by_id, "report: selected candidate is missing")
        budget_range = data["monthly_budget"]
        if budget_range is None:
            budget = "월 예산 미정"
        else:
            budget = number(budget_range["min"]) + "원 ~ " + (number(budget_range["max"]) + "원" if budget_range["max"] is not None else "상한 미정")
        lines = ["# 예산 분석", "", "## 예산 범위", "", budget,
                 "", "기본 단가는 공개 종량제 USD 기준이며 세금·크레딧·약정·계정별 할인은 제외합니다.",
                 "", "## 후보별 예상 월 비용", "",
                 "| 대상 · 후보 | 구성 | 고정비 (USD 소계) | 변동비 (USD 소계) | 전체 (USD) | 앱 추가 (USD) | 전체 원화 | 예산 판정 | 조회/시도 시각 (UTC) |",
                 "|---|---|---|---|---|---|---|---|---|"]
        for candidate in costs["candidates"]:
            summary = candidate["summary"]
            cells = [TARGETS[candidate["target"]] + " · " + escaped(candidate["candidate_id"]),
                     "명시" if candidate["configuration_status"] == "confirmed" else "가정 포함",
                     money(summary["fixed_usd"]), money(summary["variable_usd"]), total_text(candidate), total_text(candidate, True),
                     money(summary["total_krw"], "KRW"), BUDGET[candidate["budget"]["status"]] + (" (전체)" if candidate["budget"]["basis"] == "total" else " (증분)"), prices["queried_at"]]
            lines.append("| " + " | ".join(cells) + " |")
        lines.extend(["", "부분 결과의 소계는 전체 합계가 아닙니다. 상한과 미산정 항목을 함께 확인하세요.", "", "## 환율 근거", ""])
        if data["fx"] is None:
            lines.append("- 환율 미정: USD 견적은 보존하며 원화 예산을 확정하지 않습니다.")
        else:
            fx = data["fx"]
            lines.append("- USD 1 = " + number(fx["usd_to_krw"]) + "원; 기준일 " + fx["as_of"] + "; 출처 " + escaped(fx["source"]))
        lines.extend(["", "## 예산 경고와 절감안", ""])
        for candidate in costs["candidates"]:
            lines.extend(["- " + escaped(candidate["candidate_id"]) + ": " + warning(candidate),
                          "  - " + savings_text(candidate["candidate_id"], differences)])
        lines.extend(["", "## 미산정 항목과 실패 사유", ""])
        if not costs["issues"]:
            lines.append("- 없음")
        for error in costs["issues"]:
            label = ISSUES.get(error["code"], "확인 필요")
            lines.append("- " + escaped(error["candidate_id"]) + " / " + escaped(error["item_id"] or "구성") + ": " + label + "; " + escaped(error["message"]))
        lines.extend(["", "## 가격 근거", "", "| 후보 | 비용 항목 | SKU | 출처 | 단위 | 가격 적용 시점 |", "|---|---|---|---|---|---|"])
        for candidate in prices["candidates"]:
            for item in candidate["items"]:
                p = item["price"]
                if p is not None:
                    lines.append("| " + " | ".join(escaped(value) for value in (candidate["candidate_id"], item["item_id"], p["sku"], p["source"], p["unit"], p["effective_at"])) + " |")
        lines.extend(["", "## 근거 파일의 해시", "", "- 입력: `" + input_hash(data) + "`", "- 단가: `" + input_hash(prices) + "`", "- 계산: `" + input_hash(costs) + "`"])
        if assessment is not None:
            lines.append("- 자원 평가: `" + input_hash(assessment) + "`")
            for candidate in assessment["candidates"]:
                operating = candidate["operating_costs"]
                require(isinstance(operating, dict) and set(operating) <= {"power", "hardware", "labor"}, "report: invalid operating-cost categories")
                for value in operating.values():
                    fields(value, "monthly_krw source", "operating cost")
                    usage(value["monthly_krw"], "operating cost")
                    fields(value["source"], "path ref note", "operating cost source")
                    string(value["source"]["note"], "operating cost note")
                if operating:
                    lines.extend(["", "## 온프레미스 별도 운영 비용", "", "클라우드 비용에 합산하지 않은 별도 값입니다. 전체 운영 예산은 별도로 확인해야 합니다.", ""])
                    for name, value in candidate["operating_costs"].items():
                        lines.append("- " + {"power":"전기", "hardware":"장비", "labor":"인건비"}[name] + ": " + money(value["monthly_krw"], "KRW") + "; " + escaped(value["source"]["note"]))
        lines.extend(["", "## 가정", ""])
        for candidate in costs["candidates"]:
            for assumption in candidate["assumptions"]:
                lines.append("- " + escaped(candidate["candidate_id"]) + ": " + escaped(assumption))
        selected = by_id[candidate_id]
        summary = recommendation_summary(selected, prices, data, differences, input_hash(costs))
        errors = [error for error in costs["issues"] if error["candidate_id"] == candidate_id]
        if errors:
            section = "- 미산정·확인 필요 항목: " + "; ".join(dict.fromkeys(ISSUES.get(error["code"], "확인 필요") for error in errors)) + "\n"
            summary = summary.replace("\n\n" + END, "\n" + section + "\n" + END)
        return "\n".join(lines) + "\n", summary


def update_report(existing, summary):
    require(existing.count(START) == existing.count(END) == 1, "report: exactly one pricing marker pair is required")
    start, end = existing.index(START), existing.index(END)
    require(start < end, "report: pricing markers are reversed")
    return existing[:start] + summary.rstrip("\n") + existing[end + len(END):]
