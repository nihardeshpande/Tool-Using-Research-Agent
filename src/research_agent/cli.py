from __future__ import annotations

import argparse
import os

from .agent import ResearchAgent


def main() -> None:
    parser = argparse.ArgumentParser(description="Research a question with bounded web tools and citations.")
    parser.add_argument("question", nargs="+", help="Research question")
    parser.add_argument("--max-steps", type=int, default=int(os.getenv("MAX_STEPS", "6")),
                        help="Hard maximum number of tool calls (default: 6)")
    parser.add_argument("--search-results", type=int, default=int(os.getenv("SEARCH_RESULTS", "5")))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("REQUEST_TIMEOUT", "15")))
    args = parser.parse_args()
    from .tools import WebTools
    result = ResearchAgent(WebTools(args.timeout, args.search_results), args.max_steps).run(" ".join(args.question))
    print("\n" + result.answer)
    if result.sources:
        print("\nSources:")
        for i, page in enumerate(result.sources, 1):
            print(f"[{i}] {page.title} — {page.url}")
    print(f"\nTool calls: {result.steps}/{args.max_steps}")
    for note in result.notes:
        print(f"Note: {note}")


if __name__ == "__main__":
    main()
