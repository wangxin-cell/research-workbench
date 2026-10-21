"""Run with python -I after installing the wheel. No live research services."""
from http.server import ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path
import os
import tempfile
import threading
import urllib.request

import research_workbench
from research_workbench.core import read_json, write_json
from research_workbench.server import Application, ASSETS, DATA, make_handler
from research_workbench.workflow import import_report, load_accepted, prepare


def main():
    checkout = Path(__file__).resolve().parents[1]
    installed = Path(research_workbench.__file__).resolve()
    if installed.is_relative_to(checkout / "research_workbench"):
        raise RuntimeError("Source checkout is shadowing the installed wheel; use python -I")
    if version("research-workbench-local") != research_workbench.__version__:
        raise RuntimeError("Installed metadata and package version disagree")
    for name in ("index.html", "app.js", "styles.css"):
        if not (ASSETS / name).is_file():
            raise RuntimeError(f"Missing packaged web asset: {name}")
    # Imports must also work without the optional PDF dependency.
    from research_workbench import evidence, pdf_worker  # noqa: F401
    cases = read_json(DATA / "exploration.json")["cases"]
    case = next(c for c in cases if c["id"] == "EXP-C-GRAPH")
    base = Path(os.environ.get("WORKBENCH_TEST_TEMP", tempfile.gettempdir())).resolve()
    temp = tempfile.TemporaryDirectory(dir=base)
    root = Path(temp.name)
    app = None
    try:
        run_dir = prepare(root / "runs", case)
        answer = root / "answer.json"
        write_json(answer, read_json(DATA / "demo-report.json"))
        import_report(run_dir, answer, "manually authored package smoke fixture")
        load_accepted(run_dir)
        app = Application(root / "runs")
        with ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app)) as server:
            thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
            thread.start()
            try:
                client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                for route in ("/", "/demo", f"/reports/{run_dir.name}"):
                    with client.open(f"http://127.0.0.1:{server.server_port}{route}", timeout=5) as response:
                        if response.status != 200 or b"<" not in response.read():
                            raise RuntimeError("Installed web route did not return HTML")
            finally:
                server.shutdown()
                thread.join(timeout=2)
        print(f"Installed wheel {research_workbench.__version__}: packaged data, assets, offline workflow, and HTTP routes passed.")
    finally:
        if app is not None:
            app.pool.shutdown(wait=True)
        if not root.resolve().is_relative_to(base):
            raise RuntimeError("Refusing to clean up outside the test workspace")
        temp.cleanup()


if __name__ == "__main__":
    main()
