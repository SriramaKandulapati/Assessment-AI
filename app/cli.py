import argparse
import json

from app.config import HOST, PORT
from app.orchestration import SCENARIOS, WorkflowError, create_run, get_run
from app.storage import init_db


def main():
    parser = argparse.ArgumentParser(prog="shortener", description="Run the URL shortener or its workflow demos")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Start the HTTP API")
    serve.add_argument("--host", default=HOST)
    serve.add_argument("--port", type=int, default=PORT)
    demo = sub.add_parser("demo", help="Execute a deterministic engineering scenario")
    demo.add_argument("scenario", choices=SCENARIOS)
    demo.add_argument("--requirement")
    demo.add_argument("--fail-stage", help="Inject a repeated stage failure to show fallback and safe stop")
    show = sub.add_parser("inspect", help="Print a persisted run")
    show.add_argument("run_id")
    args = parser.parse_args()
    init_db()
    if args.command == "serve":
        import uvicorn
        uvicorn.run("app.main:app", host=args.host, port=args.port, reload=False)
    elif args.command == "demo":
        result = create_run(args.scenario, args.requirement, args.fail_stage)
        print(json.dumps(result, indent=2))
    else:
        try:
            print(json.dumps(get_run(args.run_id), indent=2))
        except WorkflowError as exc:
            parser.error(str(exc))


if __name__ == "__main__":
    main()
