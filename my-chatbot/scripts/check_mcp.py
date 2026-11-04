"""python -m scripts.check_mcp [--tool pay_benefits --question "학자금 지원 기준?"]"""

import argparse
import asyncio
from uuid import uuid4

from app.mcp.client import MCPToolGateway
from app.schemas import ToolInput


async def check(args):
    gateway = MCPToolGateway()
    async with gateway.connect():
        tools = await gateway.list_tools()
        print(f'MCP stdio 연결됨: {len(tools)}개 도구')
        for tool in tools:
            print(f'  {tool.id}: {tool.name}')
        if args.question:
            if not args.tool or args.tool not in {tool.id for tool in tools}:
                raise ValueError('--question과 함께 등록된 --tool ID를 지정해주세요.')
            result = await gateway.execute(args.tool, ToolInput(
                question=args.question, employee_id=args.employee_id, conversation_id=uuid4(),
            ))
            print(f'실행 상태: {result.status} · 문서 근거 {len(result.sources)}개')
            for source in result.sources:
                print(f'  {source.document} p.{source.pages or source.page}')


def main():
    parser = argparse.ArgumentParser(description='실제 로컬 MCP 서버 연결/도구 실행 확인')
    parser.add_argument('--tool')
    parser.add_argument('--question')
    parser.add_argument('--employee-id', default='KDN0001')
    asyncio.run(check(parser.parse_args()))


if __name__ == '__main__':
    main()
