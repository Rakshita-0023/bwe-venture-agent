from __future__ import annotations

import argparse

from analyst import run_analysis, run_ask
from crawler import run_crawl
from knowledge_base import build_knowledge_base
from utils import ensure_directories


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BWE Venture Intelligence Agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("crawl", help="Crawl BWE public website content")
    subparsers.add_parser("build-kb", help="Build local Chroma + LlamaIndex knowledge base")
    subparsers.add_parser("analyse", help="Extract structured insights and generate reports")

    ask_parser = subparsers.add_parser("ask", help="Ask grounded questions over the local knowledge base")
    ask_parser.add_argument("question", type=str, help="Question to answer")

    return parser


def main() -> None:
    ensure_directories()
    args = build_parser().parse_args()

    if args.command == "crawl":
        run_crawl()
    elif args.command == "build-kb":
        build_knowledge_base()
    elif args.command == "analyse":
        run_analysis()
    elif args.command == "ask":
        print(run_ask(args.question))


if __name__ == "__main__":
    main()
