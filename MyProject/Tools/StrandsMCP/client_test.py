#!/usr/bin/env python3
import json
import anyio
import logging
import traceback
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession

# Enable detailed logging to diagnose client/server exchange
logging.basicConfig(level=logging.DEBUG)
for name in ["mcp", "mcp.client", "httpx", "anyio"]:
    logging.getLogger(name).setLevel(logging.DEBUG)


async def main():
    # Connect to the Streamable HTTP MCP server
    async with streamablehttp_client("http://127.0.0.1:8000/mcp", terminate_on_close=False) as (read_stream, write_stream, _get_session_id):
        session = ClientSession(read_stream, write_stream)

        # Initialize session
        # Timeout to avoid hanging if something goes wrong
        with anyio.fail_after(15):
            init = await session.initialize()
        print("Initialized. Protocol version:", init.protocolVersion)

        # List available tools
        with anyio.fail_after(15):
            tools_result = await session.list_tools()
        tool_names = [t.name for t in tools_result.tools]
        print("Discovered tools:", tool_names)

        # Smoke-test: call jump if present
        if "jump" in tool_names:
            print("Calling tools/call 'jump' ...")
            with anyio.fail_after(15):
                call_result = await session.call_tool("jump", {})
            # Convert result to JSON for readable output
            try:
                print("jump call result (raw):", call_result)
                print("jump call result (json):", json.dumps(call_result.model_dump(mode="json"), indent=2))
            except Exception:
                # Fallback: best-effort printing if model_dump is not available
                print("jump call result (no model_dump available):", call_result)
        else:
            print("Tool 'jump' not found; skipping call test.")

if __name__ == "__main__":
    try:
        anyio.run(main)
    except KeyboardInterrupt:
        print("Client cancelled.")
    except BaseException as e:
        # Handles ExceptionGroup and regular exceptions
        print("Client error:", repr(e))
        traceback.print_exc()
