from dataclasses import dataclass
from typing import Awaitable, Callable

from app.schemas import ToolDefinition, ToolInput, ToolResult


@dataclass(frozen=True)
class Tool:
    definition: ToolDefinition
    execute: Callable[[ToolInput], Awaitable[ToolResult]]
