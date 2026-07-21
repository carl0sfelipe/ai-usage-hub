from __future__ import annotations

import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        from server.http_api import main as http_main
        http_main()
    elif len(sys.argv) > 1 and sys.argv[1] == "--dashboard":
        from server.dashboard import main as dash_main
        dash_main()
    else:
        from server.mcp_server import main as mcp_main
        mcp_main()


if __name__ == "__main__":
    main()
