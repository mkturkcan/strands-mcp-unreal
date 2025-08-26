#!/usr/bin/env python3
import os
import sys
import json
import traceback
from pathlib import Path

OUT = Path(__file__).with_name("strands_inspect.txt")

def add_dll_dirs():
    proj_root = Path(__file__).resolve().parents[2]
    site = proj_root / "Intermediate" / "PipInstall" / "Lib" / "site-packages"
    for sub in ["", "numpy/.libs", "numpy/core", "cv2"]:
        p = (site / sub) if sub else site
        try:
            if p.is_dir():
                os.add_dll_directory(str(p))
        except Exception:
            pass

def main():
    add_dll_dirs()
    info = {}
    try:
        import strands  # type: ignore
        info["strands_module"] = str(getattr(strands, "__file__", "built-in/extension"))
        info["has_Agent_top_level"] = hasattr(strands, "Agent")
        info["dir_strands_sample"] = [a for a in dir(strands) if not a.startswith("_")][:200]
    except Exception as e:
        info["strands_import_error"] = f"{type(e).__name__}: {e}"
        info["strands_traceback"] = traceback.format_exc()

    # Probe common submodules for Agent symbol
    submods = [
        "strands.agent",
        "strands.agents",
        "strands.core",
        "strands.runtime",
        "strands.api",
        "strands.tools",
        "strands.tools.mcp",
    ]
    info["submodules"] = {}
    import importlib
    for m in submods:
        try:
            mod = importlib.import_module(m)
            info["submodules"][m] = {
                "ok": True,
                "file": str(getattr(mod, "__file__", "built-in/extension")),
                "has_Agent": hasattr(mod, "Agent"),
                "exports_sample": [a for a in dir(mod) if a == "Agent"],
            }
        except Exception as e:
            info["submodules"][m] = {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
            }

    # Also check exact path for MCP client module presence
    try:
        mcp_client = importlib.import_module("strands.tools.mcp.mcp_client")
        info["mcp_client"] = {
            "ok": True,
            "file": str(getattr(mcp_client, "__file__", "")),
            "attrs": [a for a in dir(mcp_client) if not a.startswith("_")],
        }
    except Exception as e:
        info["mcp_client"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    OUT.write_text(json.dumps(info, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
