from __future__ import annotations

import re

from mz.repositories.account_repo import AccountRepository

BANK_PATTERN = re.compile(r"(.+?)(储蓄卡|信用卡)\((\d+)\)")

INSTITUTION_NORMALIZE: dict[str, str] = {
    "工商": "工商银行",
    "ICBC": "工商银行",
    "建设": "建设银行",
    "CCB": "建设银行",
    "平安": "平安银行",
    "PINGAN": "平安银行",
    "招商": "招商银行",
    "中国银行": "中国银行",
    "BOC": "中国银行",
    "农业": "农业银行",
    "ABC": "农业银行",
    "交通": "交通银行",
    "光大": "光大银行",
    "民生": "民生银行",
    "广发": "广发银行",
    "兴业": "兴业银行",
    "浦发": "浦发银行",
    "华夏": "华夏银行",
}


class AccountResolver:
    def __init__(self, repo: AccountRepository):
        self.repo = repo

    def resolve(self, payment_method_raw: str | None, source: str) -> int | None:
        if not payment_method_raw:
            return None

        # WeChat balance
        if payment_method_raw in ("零钱", "/", "微信零钱"):
            return self.repo.get_or_create(
                type="wechat_balance", name="微信零钱", institution="微信支付"
            ).id

        # Shadow placeholders from bank importers
        if payment_method_raw == "__SHADOW_WECHAT__":
            return self.repo.get_or_create(
                type="wechat_balance", name="微信支付（影子）", institution="微信支付"
            ).id
        if payment_method_raw == "__SHADOW_ALIPAY__":
            return self.repo.get_or_create(
                type="alipay_balance", name="支付宝（影子）", institution="支付宝"
            ).id

        # Bank card pattern: "平安银行储蓄卡(8223)"
        m = BANK_PATTERN.match(payment_method_raw)
        if m:
            institution_raw, kind, last_4 = m.groups()
            institution = self._normalize_institution(institution_raw)
            type_ = "bank_credit" if kind == "信用卡" else "bank_debit"
            return self.repo.get_or_create(
                type=type_,
                name=payment_method_raw,
                institution=institution,
                last_4=last_4,
                is_credit=(kind == "信用卡"),
            ).id

        # Alipay special accounts
        if "余额宝" in payment_method_raw:
            return self.repo.get_or_create(
                type="yuebao", name="余额宝", institution="支付宝"
            ).id
        if "花呗" in payment_method_raw:
            return self.repo.get_or_create(
                type="huabei", name="花呗", institution="支付宝"
            ).id
        if "零钱通" in payment_method_raw:
            return self.repo.get_or_create(
                type="lingqiantong", name="零钱通", institution="微信支付"
            ).id
        if "余额" in payment_method_raw and "银行" not in payment_method_raw:
            return self.repo.get_or_create(
                type="alipay_balance", name="支付宝余额", institution="支付宝"
            ).id

        # Fallback
        return self.repo.get_or_create(
            type="unknown", name=payment_method_raw, institution="unknown"
        ).id

    def _normalize_institution(self, raw: str) -> str:
        for k, v in INSTITUTION_NORMALIZE.items():
            if k in raw:
                return v
        return raw.strip(" -")
