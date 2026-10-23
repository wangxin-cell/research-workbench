# Contributing to Research Workbench

The first priority is helping a researcher make a better next decision from evidence they can inspect. A smaller, reproducible correction is more useful than a new feature with no clear research task.

Issues and pull requests may be written in English or Chinese.

## Report a problem

For your first attempt, use the first-try template to tell us where you reached and one concrete obstacle or useful moment. A generated report is not required. The [first-session guide](docs/first-try.md) describes a short trial and how to keep usability feedback separate from research-quality claims.

Use the bug-report template for software failures. Include the command or UI step, expected behavior, observed behavior, Python version, operating system, and a minimal input when possible.

Use the research-feedback template for an unsupported claim, missed related work, bad resource estimate, or impractical experiment. Identify the report statement and the material that supports or contradicts it. A report that recommends stopping can be useful; a confident but unsupported idea is a failure.

Public issues are not a place for API keys, private review packets, confidential research, personal data, or full copyrighted PDFs. Replace private inputs with a minimal synthetic reproduction or public source links. Run folders are not automatically anonymized.

## Work on the code

Python 3.11 or later is required. From the checkout:

```sh
python -m pip install -e ".[pdf]"
python -m unittest discover -s tests -v
python -m research_workbench serve
```

The default service is available at `http://127.0.0.1:8765`. No model key is required for the included demonstration or offline import/export. Automated tests must use mocked providers; do not add paid calls or depend on live arXiv responses.

Set `WORKBENCH_TEST_TEMP` to an existing writable directory if your environment restricts the system temporary directory. Without the optional PDF extra, parser and upload tests are explicitly skipped.

Keep a pull request focused on a concrete problem. Explain the resulting behavior and relevant verification. Add regression coverage for consequential failures; prose-only changes do not need new tests. For interface changes, include a screenshot made with synthetic or public materials.

## Add a research case

A case describes a decision under constraints, not just a list of papers. Provide:

- The user's question and available time, compute, skills, and data.
- Public source identifiers and the exact supplied reading scope: abstract, notes, or selected passages.
- The decision or failure the case is intended to expose.
- The evidence behind any expected judgment, and whether a domain researcher has reviewed it.

Keep scoring criteria separate from model inputs. Mark constructed or developer-exposed cases as such. Do not label an example as a real user study, independent review, or held-out case without the corresponding evidence.

Do not commit private held-out cases to the public repository. Variations of the same paper family should not be split across development and held-out sets. A new wording of a known case does not create independent evidence.

## Compare model workflows

Freeze criteria before generating reports, keep research materials identical, and report actual model names, settings, calls, usage, and human review procedures. One call and two calls do not have equal costs; state the comparison budget.

Keep failures and unknown judgments in the results. A valid JSON report, working citation link, or passed software test does not establish scientific correctness. Follow the [detailed guide](docs/guide.md) for local review packets and retain the original judgments.

The current examples and manually authored reports are demonstrations. Do not use them to advertise measured research performance.
