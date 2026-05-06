"""统一错误码体系与异常处理。"""

from fastapi import HTTPException, status


class AppError(HTTPException):
    """应用统一异常基类。"""

    def __init__(self, code: str, message: str, status_code: int = 400, detail: dict | None = None):
        super().__init__(
            status_code=status_code,
            detail={
                "code": code,
                "message": message,
                "status": status_code,
                "details": detail or {},
            },
        )


# ── 认证相关 ──
class UnauthorizedError(AppError):
    def __init__(self, message: str = "未授权，请先登录"):
        super().__init__("UNAUTHORIZED", message, status.HTTP_401_UNAUTHORIZED)


class ForbiddenError(AppError):
    def __init__(self, message: str = "权限不足"):
        super().__init__("FORBIDDEN", message, status.HTTP_403_FORBIDDEN)


# ── 资源相关 ──
class NotFoundError(AppError):
    def __init__(self, resource: str = "资源", resource_id: str = ""):
        msg = f"{resource} 不存在" + (f"：{resource_id}" if resource_id else "")
        super().__init__("NOT_FOUND", msg, status.HTTP_404_NOT_FOUND)


# ── 状态机相关 ──
class InvalidTransitionError(AppError):
    def __init__(self, from_state: str, to_state: str, reason: str = ""):
        msg = f"不允许从 {from_state} 迁移到 {to_state}"
        if reason:
            msg += f"：{reason}"
        super().__init__("INVALID_TRANSITION", msg)


class BlockerExistsError(AppError):
    def __init__(self, blockers: list[dict]):
        super().__init__(
            "BLOCKER_EXISTS",
            f"存在 {len(blockers)} 个未解决的阻塞项，无法推进",
            detail={"blockers": blockers},
        )


class PreconditionError(AppError):
    def __init__(self, failed_conditions: list[str]):
        super().__init__(
            "PRECONDITION_FAILED",
            f"前置条件未满足：{', '.join(failed_conditions)}",
            detail={"failed_conditions": failed_conditions},
        )


# ── 审批相关 ──
class ApprovalError(AppError):
    def __init__(self, message: str):
        super().__init__("APPROVAL_ERROR", message)


class ReasonRequiredError(AppError):
    def __init__(self):
        super().__init__("REASON_REQUIRED", "高风险内容（L2/L3）的签发或退回必须填写理由")


# ── 版本快照相关 ──
class BundleSupersededError(AppError):
    def __init__(self, bundle_id: str):
        super().__init__(
            "BUNDLE_SUPERSEDED",
            f"送审快照包 {bundle_id} 已失效，底层内容已变更，请重新提交送审",
        )


# ── Source Vault ──
class SourceVaultAccessDenied(AppError):
    def __init__(self):
        super().__init__(
            "SOURCE_VAULT_ACCESS_DENIED",
            "无权访问来源保密库",
            status.HTTP_403_FORBIDDEN,
        )
