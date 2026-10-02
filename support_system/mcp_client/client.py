import asyncio
import concurrent.futures
import sys
import os
import json
from typing import Optional


class MCPToolClient:
    """
    Synchronous client for invoking tools on a FastMCP server over stdio transport.

    Spawns the target MCP server as a subprocess and communicates with it using
    the MCP stdio protocol. The async I/O is executed in an isolated thread pool
    so this client is safe to use from inside LangGraph's (or any other framework's)
    existing event loop without causing a "loop already running" error.

    Args:
        server_path: Absolute or relative path to the MCP server script (e.g. ``server.py``).

    Example::

        client = MCPToolClient("/path/to/server.py")
        result = client.call("get_order_status", {"order_id": "ORD-123"})
    """

    def __init__(self, server_path: Optional[str] = None, server_url: Optional[str] = None,
                 auth_token: Optional[str] = None, extra_env: Optional[dict] = None):
        if not server_path and not server_url:
            raise ValueError("Must provide either server_path (stdio) or server_url (remote)")
        self.server_path = server_path
        self.server_url = server_url
        self.auth_token = auth_token
        self.extra_env = extra_env or {}

    def _normalize_result(self, result) -> dict:
        if not result.content:
            return {"success": False, "error": "MCP server returned no content."}

        first = result.content[0]
        if first.type == "error":
            return {"success": False, "error": getattr(first, "text", str(first))}
        if first.type == "text":
            try:
                return json.loads(first.text)
            except json.JSONDecodeError as e:
                return {"success": False, "error": f"Failed to parse MCP response as JSON: {e}"}

        return {"success": False, "error": f"Unexpected content type from MCP server: {first.type}"}

    async def _call_async(self, tool_name: str, arguments: dict) -> dict:
        from mcp import ClientSession
        
        if self.server_url:
            from mcp.client.streamable_http import streamable_http_client
            headers = {"Authorization": f"Bearer {self.auth_token}"} if self.auth_token else {}
            async with streamable_http_client(self.server_url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    return self._normalize_result(result)
        else:
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client

            env = os.environ.copy()
            env.update(self.extra_env)
            
            server_params = StdioServerParameters(
                command=sys.executable,
                args=[self.server_path],
                env=env
            )

            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    return self._normalize_result(result)

    def call(self, tool_name: str, arguments: dict) -> dict:
        """
        Invoke an MCP tool synchronously and return the parsed result.

        Runs the async transport layer in a dedicated ``ThreadPoolExecutor`` so
        this method can be safely called from within an already-running event
        loop (e.g. inside a LangGraph node or a Jupyter notebook).

        Args:
            tool_name: Name of the MCP tool to call (e.g. ``"get_order_status"``).
            arguments: Dict of arguments to pass to the tool.

        Returns:
            A dict containing the JSON-decoded tool response, or a
            ``{"success": False, "error": "<reason>"}`` dict if anything went wrong.

        Raises:
            Exception: Re-raises any exception thrown by the underlying async call
                (e.g. subprocess errors, connection failures).
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, self._call_async(tool_name, arguments))
            return future.result()
