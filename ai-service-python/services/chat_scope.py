"""Resolve the material boundary for a chat request before any retrieval or planning."""

from dataclasses import dataclass

from rag.store import normalize_id
from schemas.requests import ChatRequest


@dataclass(frozen=True)
class ChatMaterialScope:
    constrained: bool
    allowed_ids: tuple[str, ...]
    primary_id: str | None
    use_skeleton: bool


def resolve_chat_material_scope(request: ChatRequest) -> ChatMaterialScope:
    # An explicit empty list is a closed scope. A task without a supplied list
    # must also fail closed until its material membership is known.
    constrained = request.allowedPaperIds is not None or bool(request.taskId)
    if not constrained:
        return ChatMaterialScope(False, (), request.pdfId, bool(request.paperSkeleton))

    allowed = tuple(dict.fromkeys(
        normalize_id(value)
        for value in (request.allowedPaperIds or [])
        if str(value or "").strip()
    ))
    requested_primary = request.primaryPaperId or request.pdfId
    primary = normalize_id(requested_primary) if str(requested_primary or "").strip() else None
    if primary not in allowed:
        primary = None
    # paperSkeleton has no independently verifiable paper id. Accept it only
    # when the legacy pdfId identifies the same in-scope primary paper.
    skeleton_id = normalize_id(request.pdfId) if request.pdfId else None
    use_skeleton = bool(request.paperSkeleton and primary and skeleton_id == primary)
    return ChatMaterialScope(True, allowed, primary, use_skeleton)
