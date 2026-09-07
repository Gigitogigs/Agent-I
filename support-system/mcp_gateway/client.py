import asyncio
import concurrent.futures
import sys
import os
import json
from typing import Optional


class MCPToolClient:
    """
    A synchronous wrapper that calls the MCP server (server.py) over stdio transport.

    Design notes and known trade-offs:
    -
    - Async bridging: LangGraph executes graph nodes inside an async event loop.
      Calling asyncio.run() from within a running loop raises RuntimeError.
      To avoid this, _call_async is dispatched into a dedicated background thread
      via ThreadPoolExecutor. That thread starts its own event loop, so it never
      conflicts with LangGraph's loop.

    - One subprocess per call: Each call() spawns a fresh Python subprocess for
      server.py, initializes an MCP session, makes the tool call, and tears it down.
      Python startup + MCP handshake adds ~300-600ms of latency overhead per call.
      This is acceptable for an MVP where correctness is the priority.
      Future improvement: keep a persistent subprocess alive and reuse the session.

    - Error detection: The MCP SDK's CallToolResult does not guarantee a boolean
      .isError attribute across all versions. We check the type field of the first
      content item to determine success/error reliably.
    """

    def __init__(self, server_path: Optional[str] = None):
        if not server_path:
            server_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "server.py")
            )
        self.server_path = server_path

    async def _call_async(self, tool_name: str, arguments: dict) -> dict:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command=sys.executable,
            args=[self.server_path],
            env=os.environ.copy()
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)

                if not result.content:
                    return {"success": False, "error": "MCP server returned no content."}

                first = result.content[0]

                # Detect errors via content type, not .isError (unreliable across SDK versions)
                if first.type == "error":
                    return {"success": False, "error": getattr(first, "text", str(first))}

                if first.type == "text":
                    try:
                        return json.loads(first.text)
                    except json.JSONDecodeError as e:
                        return {"success": False, "error": f"Failed to parse MCP response as JSON: {e}"}

                return {"success": False, "error": f"Unexpected content type from MCP server: {first.type}"}

    def call(self, tool_name: str, arguments: dict) -> dict:
        """
        Synchronous entry point. Dispatches the async MCP call to a background thread
        so that it is safe to call from within LangGraph's own event loop.
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, self._call_async(tool_name, arguments))
            return future.result()
