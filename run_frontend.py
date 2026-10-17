#!/usr/bin/env python3
"""
Apni Kheti - Local Frontend Server
Runs a lightweight HTTP server serving the clean Apni Kheti application at http://localhost:3000
"""

import http.server
import socketserver
import os
import sys

# Force UTF-8 stdout if possible on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PORT = 3000
DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def log_message(self, format, *args):
        try:
            sys.stdout.write(f"[{self.log_date_time_string()}] {args[0]} {args[1]}\n")
        except Exception:
            pass

def main():
    os.chdir(DIRECTORY)
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        url = f"http://localhost:{PORT}"
        print("=" * 60)
        print("Apni Kheti Frontend Running")
        print(f"Local URL: {url}")
        print(f"Serving Directory: {DIRECTORY}")
        print("Press Ctrl+C to stop the server.")
        print("=" * 60)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")

if __name__ == "__main__":
    main()
