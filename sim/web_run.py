"""Flask Web アプリの起動スクリプト。

Usage:
    python -m sim.web_run [--data-dir ./data] [--port 5000]
"""
import argparse
from sim.web.app import run_app


def main():
    parser = argparse.ArgumentParser(description="倉庫シミュレーター Web UI")
    parser.add_argument("--data-dir", default="./data", help="データルートディレクトリ")
    parser.add_argument("--port", type=int, default=8080, help="ポート番号")
    parser.add_argument("--debug", action="store_true", help="デバッグモード")
    args = parser.parse_args()
    print(f"Web UI を起動中: http://127.0.0.1:{args.port}/")
    run_app(data_dir=args.data_dir, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
