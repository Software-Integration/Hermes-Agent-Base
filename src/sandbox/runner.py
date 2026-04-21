from __future__ import annotations

import importlib
import json
import sys


def _validate_arguments(raw_schema: str, raw_arguments: str) -> dict:
    schema = json.loads(raw_schema)
    arguments = json.loads(raw_arguments)
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    for key, type_name in schema.items():
        if key not in arguments:
            raise ValueError(f"missing argument {key}")
        if type_name == "str" and not isinstance(arguments[key], str):
            raise ValueError(f"argument {key} must be str")
    return arguments


def main() -> int:
    if len(sys.argv) != 6:
        print(json.dumps({"ok": False, "error_code": "invalid_invocation", "reason": "invalid sandbox invocation"}))
        return 1

    _, tool_name, module_name, function_name, raw_schema, raw_arguments = sys.argv
    try:
        module = importlib.import_module(module_name)
        handler = getattr(module, function_name)
        arguments = _validate_arguments(raw_schema, raw_arguments)
        result = handler(arguments)
        if not isinstance(result, dict):
            result = {"ok": False, "error_code": "non_dict_payload", "reason": "tool returned non-dict payload"}
        print(json.dumps(result))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "tool": tool_name,
                    "error_code": "sandbox_execution_failed",
                    "reason": str(exc),
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
