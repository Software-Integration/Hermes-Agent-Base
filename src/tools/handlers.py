import math
from datetime import datetime, timezone


def math_evaluate(arguments: dict) -> dict:
    expr = arguments.get("expression", "")
    if not isinstance(expr, str) or not expr.strip():
        return {"ok": False, "error_code": "expression_required", "reason": "expression required"}
    try:
        allowed_chars = set("0123456789+-*/(). eE")
        if any(ch not in allowed_chars for ch in expr):
            return {"ok": False, "error_code": "unsafe_expression", "reason": "unsafe expression"}
        result = eval(expr, {"__builtins__": {}}, {"math": math})
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error_code": "evaluation_failed", "reason": str(exc)}


def now_utc(arguments: dict) -> dict:
    fmt = arguments.get("format", "%Y-%m-%d %H:%M:%S")
    try:
        return {"ok": True, "value": datetime.now(timezone.utc).strftime(fmt)}
    except Exception:
        return {"ok": False, "error_code": "invalid_format", "reason": "invalid format"}
