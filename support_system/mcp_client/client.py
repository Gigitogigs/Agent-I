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

    def __init__(self, server_path: str):
        self.server_path = server_path

    async def _call_async(self, tool_name: str, arguments: dict) -> dict:
        """
        Internal async implementation of a single MCP tool call.

        Opens a fresh stdio session to the server subprocess, initialises the
        MCP handshake, invokes the requested tool, and normalises the raw MCP
        response into a plain dict with a ``success`` boolean.

        Args:
            tool_name: Name of the MCP tool to invoke (must be registered on the server).
            arguments: Keyword arguments forwarded verbatim to the tool.

        Returns:
            A dict containing the tool's JSON-decoded response on success, or a
            ``{"success": False, "error": "<reason>"}`` dict on failure.
        """
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
