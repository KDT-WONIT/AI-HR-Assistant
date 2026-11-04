import importlib
import pkgutil
import app.tools
from app.config import settings
from app.tools.base import Tool


def discover_tools() -> dict[str, Tool]:
    found = {}
    for item in pkgutil.iter_modules(app.tools.__path__):
        if item.name.startswith('_') or item.name in {'base', 'registry', 'execution'}:
            continue
        module = importlib.import_module(f'app.tools.{item.name}')
        tool = getattr(module, 'tool', None)
        if not isinstance(tool, Tool):
            continue
        if tool.definition.id in found:
            raise ValueError(f'도구 ID 중복: {tool.definition.id}')
        found[tool.definition.id] = tool
    if settings.enabled_tools:
        missing = set(settings.enabled_tools) - found.keys()
        if missing:
            raise ValueError(f'ENABLED_TOOLS에 등록되지 않은 도구가 있습니다: {sorted(missing)}')
        found = {name: found[name] for name in settings.enabled_tools}
    if not found:
        raise ValueError('사용할 수 있는 도구가 없습니다.')
    return found


TOOLS = discover_tools()

