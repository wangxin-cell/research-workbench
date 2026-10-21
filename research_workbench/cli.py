import argparse
from pathlib import Path
import sys

from .core import ValidationError, load_case
from .provider import ResponsesProvider
from .workflow import blind_pair, import_report, prepare, run


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evidence-linked research ideation with auditable local runs")
    commands = parser.add_subparsers(dest="command", required=True)
    ui = commands.add_parser("serve", help="Open a local browser workbench")
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument("--runs", type=Path, default=Path("runs"))
    search = commands.add_parser("search", help="Find arXiv paper abstracts")
    search.add_argument("query")
    search.add_argument("--out", type=Path, required=True)
    for name in ("check", "prepare", "run"):
        child = commands.add_parser(name)
        child.add_argument("input", type=Path)
        child.add_argument("--case")
        if name != "check":
            child.add_argument("--out", type=Path, default=Path("runs"))
        if name == "run":
            child.add_argument("--model", required=True)
            child.add_argument("--workflow", choices=["baseline", "reviewed"], default="reviewed")
            child.add_argument("--timeout", type=float, default=120)
            child.add_argument("--max-output-tokens", type=int, default=6000)
    child = commands.add_parser("import")
    child.add_argument("run_dir", type=Path)
    child.add_argument("report", type=Path)
    child.add_argument("--model-label", required=True)
    child = commands.add_parser("blind")
    child.add_argument("first", type=Path)
    child.add_argument("second", type=Path)
    child.add_argument("--out", type=Path, required=True)
    child.add_argument("--plan", type=Path, help="Frozen case-specific review criteria")
    child = commands.add_parser("review-plan", help="Snapshot review criteria before generating reports")
    child.add_argument("input", type=Path)
    child.add_argument("--case")
    child.add_argument("--criteria", type=Path, required=True)
    child.add_argument("--out", type=Path, required=True)
    child = commands.add_parser("review-submit", help="Validate and preserve an evidence-anchored review")
    child.add_argument("reviewer_dir", type=Path)
    child.add_argument("rating", type=Path)
    child.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            from .server import serve
            serve(args.runs, args.port)
            return 0
        elif args.command == "search":
            from .retrieval import ArxivSearch
            from .core import write_json
            if args.out.exists():
                raise ValidationError("Output already exists; choose a new file")
            receipt = ArxivSearch().search(args.query)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            write_json(args.out, receipt)
            result = args.out
        elif args.command == "import":
            result = import_report(args.run_dir, args.report, args.model_label)
        elif args.command == "blind":
            result = blind_pair(args.first, args.second, args.out, args.plan)
        elif args.command == "review-plan":
            from .evaluation import create_review_plan
            result = create_review_plan(load_case(args.input, args.case), args.criteria, args.out)
        elif args.command == "review-submit":
            from .evaluation import submit_review
            result = submit_review(args.reviewer_dir, args.rating, args.out)
        else:
            case = load_case(args.input, args.case)
            if args.command == "check":
                print(f"Valid input: {case['id']} ({len(case['sources'])} sources). Evidence meaning and novelty are not evaluated.")
                return 0
            if args.command == "prepare":
                result = prepare(args.out, case)
            else:
                provider = ResponsesProvider(args.model, args.timeout, args.max_output_tokens)
                result = run(args.out, case, provider, args.workflow)
        print(result.resolve())
        return 0
    except (ValidationError, ValueError, RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
