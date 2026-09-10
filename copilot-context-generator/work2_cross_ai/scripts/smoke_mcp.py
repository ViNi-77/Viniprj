"""folder-context MCP サーバの stdio スモークテスト.

サーバを実際に起動し、MCP プロトコルで initialize → tools/list →
search_files 呼び出しまでを確認する。

使い方:
    python scripts/smoke_mcp.py <資料フォルダ>
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(root: str) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=['-m', 'mcp_server.folder_context_server', '--root', root],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print('initialize: OK')

            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print(f"tools/list: {names}")
            expected = {'search_files', 'read_document', 'get_summary',
                        'search_content', 'list_recent_changes'}
            missing = expected - set(names)
            assert not missing, f"不足ツール: {missing}"

            result = await session.call_tool('search_files', {})
            text = result.content[0].text
            print('search_files 応答（先頭200字）:')
            print(text[:200])

            result = await session.call_tool('list_recent_changes', {'days': 3650})
            print('list_recent_changes: OK')

    print('\nMCP スモークテスト: すべて成功')


if __name__ == '__main__':
    root = sys.argv[1] if len(sys.argv) > 1 else '.'
    if not Path(root).is_dir():
        print(f"フォルダがありません: {root}", file=sys.stderr)
        sys.exit(2)
    asyncio.run(run(root))
