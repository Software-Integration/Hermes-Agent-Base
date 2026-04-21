from fastapi import HTTPException, status


class ToolPolicyViolation(HTTPException):
    def __init__(self, reason: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"tool policy violation: {reason}",
        )
