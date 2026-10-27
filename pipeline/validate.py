from decimal import Decimal, InvalidOperation
from domain.records import AdapterRecord, VALID_CATEGORIES, VALID_DATE_BASES, UNKNOWN_CATEGORY
from domain.enums import ValidationStatus

def validate(record: AdapterRecord) -> tuple:
    messages = []

    if not record.source_currency_code or not record.source_currency_code.strip():
        messages.append({"code": "MISSING_CURRENCY", "message": "source_currency_code is empty"})

    if record.effective_date_basis not in VALID_DATE_BASES:
        messages.append({
            "code": "INVALID_DATE_BASIS",
            "message": f"effective_date_basis '{record.effective_date_basis}' not in {VALID_DATE_BASES}",
        })

    if record.category not in VALID_CATEGORIES:
        messages.append({
            "code": "INVALID_CATEGORY",
            "message": f"category '{record.category}' not in {VALID_CATEGORIES}",
        })
    elif record.category == UNKNOWN_CATEGORY:
        messages.append({
            "code": "UNKNOWN_CATEGORY",
            "message": "category is UNKNOWN — review required",
        })

    buying_ok = _check_rate(record.buying_rate, "buying_rate", messages)
    selling_ok = _check_rate(record.selling_rate, "selling_rate", messages)

    if record.buying_rate is None and record.selling_rate is None:
        messages.append({
            "code": "BOTH_RATES_NULL",
            "message": "both buying_rate and selling_rate are None — at least one required",
        })

    if (record.buying_rate is not None and record.selling_rate is not None
            and record.buying_rate > record.selling_rate):
        messages.append({
            "code": "BUYING_ABOVE_SELLING",
            "message": (
                f"buying_rate {record.buying_rate} > selling_rate {record.selling_rate} — suspicious"
            ),
        })

    if record.unit_multiplier <= 0:
        messages.append({
            "code": "INVALID_UNIT_MULTIPLIER",
            "message": f"unit_multiplier must be > 0, got {record.unit_multiplier}",
        })

    fatal_codes = {"MISSING_CURRENCY", "INVALID_DATE_BASIS", "INVALID_CATEGORY",
                   "BOTH_RATES_NULL", "INVALID_RATE_ZERO", "INVALID_RATE_NEGATIVE",
                   "INVALID_UNIT_MULTIPLIER"}
    codes = {m["code"] for m in messages}

    if codes & fatal_codes:
        return ValidationStatus.REJECTED, messages
    if messages:
        return ValidationStatus.WARNING, messages
    return ValidationStatus.VALIDATED, messages

def _check_rate(value, field_name: str, messages: list) -> bool:
    if value is None:
        return True
    if not isinstance(value, Decimal):
        messages.append({
            "code": "INVALID_RATE_TYPE",
            "message": f"{field_name} must be Decimal or None, got {type(value).__name__}",
        })
        return False
    if value == Decimal(0):
        messages.append({
            "code": "INVALID_RATE_ZERO",
            "message": f"{field_name} is zero — use None for not-offered",
        })
        return False
    if value < Decimal(0):
        messages.append({
            "code": "INVALID_RATE_NEGATIVE",
            "message": f"{field_name} is negative: {value}",
        })
        return False
    return True
