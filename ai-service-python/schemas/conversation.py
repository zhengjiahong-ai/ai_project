"""Validated input to the task-scoped conversation capability adapter."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Capability = Literal['chat', 'background', 'critique', 'compare']


class ConversationCapabilityRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    taskId: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1, max_length=20000)
    capability: Literal['chat', 'background', 'critique', 'compare', 'compose'] = 'chat'
    allowedPaperIds: list[str] = Field(max_length=128)
    primaryPaperId: str | None = None
    targetPaperIds: list[str] | None = Field(default=None, max_length=4)
    critiqueContext: dict | None = None
    strictScope: bool = False
    history: list[dict[str, str]] = Field(default_factory=list, max_length=100)
    steps: list[Capability] = Field(default_factory=list, max_length=3)

    @model_validator(mode='after')
    def validate_scope_and_plan(self):
        if not self.message.strip():
            raise ValueError('问题不能为空')
        if len(set(self.allowedPaperIds)) != len(self.allowedPaperIds) or any(not value.strip() for value in self.allowedPaperIds):
            raise ValueError('材料标识无效或重复')
        if self.primaryPaperId is not None and self.primaryPaperId not in self.allowedPaperIds:
            raise ValueError('主论文不属于指定材料')
        if self.targetPaperIds is not None and (not self.targetPaperIds or len(set(self.targetPaperIds)) != len(self.targetPaperIds)
                or any(value not in self.allowedPaperIds for value in self.targetPaperIds)):
            raise ValueError('批判对象须属于对话材料')
        if self.critiqueContext is not None:
            scope = self.critiqueContext.get('scope') or {}
            if not isinstance(scope, dict) or any(value not in self.allowedPaperIds for value in scope.get('targetPaperIds', [])):
                raise ValueError('追问材料超出当前范围')
        if self.capability == 'compose':
            if len(self.steps) < 2 or len(set(self.steps)) != len(self.steps):
                raise ValueError('组合任务须指定二至三个不同能力')
        elif self.steps:
            raise ValueError('单能力请求不能附加执行步骤')
        plan = self.steps if self.capability == 'compose' else [self.capability]
        if any(step != 'chat' for step in plan) and not self.allowedPaperIds:
            raise ValueError('请先选择任务材料')
        if 'compare' in plan and len(self.allowedPaperIds) < 2:
            raise ValueError('比较至少需要两篇论文')
        return self
