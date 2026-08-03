"""Console entry point for the local stdio MCP server."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _configure_logging() -> None:
    # Protocol traffic must stay on stdout; diagnostics go to stderr only.
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    parser = argparse.ArgumentParser(
        prog="self-nomad-mcp",
        description=(
            "Run the bounded self-nomad MCP server over stdio for one fixed "
            "self repository. Requires the optional mcp extra."
        ),
    )
    parser.add_argument(
        "--repo",
        type=Path,
        required=True,
        help="Absolute path to the managed self repository (required).",
    )
    args = parser.parse_args(argv)

    repo = args.repo
    if not repo.is_absolute():
        print(
            "error: --repo must be an absolute path "
            "(MCP hosts launch servers from unpredictable working directories)",
            file=sys.stderr,
        )
        return 2

    try:
        from self_nomad.mcp_server.server import build_server
    except ImportError:
        print(
            "error: the MCP surface requires the optional dependency; "
            "install with: pip install 'self-nomad[mcp]'",
            file=sys.stderr,
        )
        return 2

    try:
        server = build_server(repo)
    except Exception as exc:  # noqa: BLE001 - process boundary
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        # MCP protocol on stdout exclusively; diagnostics already on stderr.
        server.run(transport="stdio")
    except BrokenPipeError:
        logging.getLogger("self_nomad.mcp").info("client disconnected")
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("self_nomad.mcp").error("server stopped: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
