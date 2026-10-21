**Research Workbench detailed usage**

Run the commands below from the repository root. For the short introduction, see the [project README](../README.md).

Turn a few papers and your research constraints into a traceable research decision: explore, revise, stop, or gather evidence. This is an early local Python implementation for a proposed open-source research-topic tool. The project name is provisional.

The current prototype includes a local browser interface, arXiv abstract search, selected PDF evidence passages, research constraints, source-linked research cards, offline prompt export and answer import, and optional model API generation. A separate review workflow snapshots case-specific criteria and preserves evidence-anchored, anonymous human judgments. It does not verify semantic entailment or establish novelty.

Python 3.11 or later is required. Abstracts, notes, and model workflows use the standard library; no package installation is needed when running those features from this directory. PDF extraction is optional:

```powershell
python -m pip install ".[pdf]"
```

Use the same Python environment to install and start the workbench:

```powershell
python -m research_workbench serve
```

Open `http://127.0.0.1:8765` in your browser. Start with an example or enter a question and constraints. Search arXiv by keywords or paper link, then select the abstracts to include. Without an API key you can export a prompt, send it to your chosen model, and import the JSON response. The included display example is manually authored and is not evidence of model quality. Run files stay in `runs/`; stop the local server with Ctrl+C.

Searches use arXiv metadata and abstracts, not full text. Search terms are sent to arXiv, and selected results and retrieval receipts are saved with a run. The service binds to loopback only. Broader literature coverage remains future work.

Choose **从 PDF 选择证据** to import a local PDF, enter its paper title and source link, choose a page, and select the exact text to add. You can add multiple passages from the same paper. Only selected text and its provenance enter the model request; the original PDF and other pages stay local. Page numbers use the file's one-based page order, which can differ from printed page numbers.

The tool checks selected text against the saved extracted page, records SHA-256 fingerprints, and copies original PDFs and extracted pages into each run's `evidence/` folder before analysis. Report citations lead to the selected passage, page, and original-file download. Anonymous review packets include those same originals. A project JSON includes passages, not PDF binaries; on another machine, import the identical PDFs into that run root before preparing a new analysis.

Limits are 8 MB, 80 pages, 100,000 characters per page, 500,000 characters per document, and 30,000 characters per selected passage. Parsing runs in a separate process with a 20-second timeout; it is not an OS sandbox or hard memory limit. Encrypted, textless, over-limit, and failed documents are rejected. There is no OCR. Columns, tables, formulas, and existing OCR text can extract incorrectly: check the original layout. See [pypdf's extraction limitations](https://pypdf.readthedocs.io/en/stable/user/extract-text.html). A matching fingerprint does not verify the paper's source URL, transcription accuracy, semantic support, or full-paper coverage.

This update changes the analysis instructions. Previously exported prompts must be prepared again before importing an answer with the updated version; already accepted runs remain readable.

The same fixed-material workflow is available from the command line:

```powershell
python -m research_workbench check examples/exploration.json --case EXP-C-GRAPH
python -m research_workbench prepare examples/exploration.json --case EXP-C-GRAPH
```

The second command prints a new run directory. Its prompt.txt contains only the selected input and report contract. Give that prompt to a model of your choice, save its JSON answer, then import it:

```powershell
python -m research_workbench import runs/YOUR_RUN answer.json --model-label "model name reported by operator"
```

Open report.html in the run directory. An imported response is explicitly recorded as imported, with unverified model identity and unknown usage. examples/demo-report.json is a manually authored display fixture for EXP-C-GRAPH, not a model-evaluation result.

For a live API run, set OPENAI_API_KEY in your own local environment and select a model that supports Responses structured outputs:

```powershell
python -m research_workbench run examples/exploration.json --case EXP-C-GRAPH --model YOUR_MODEL --workflow baseline
python -m research_workbench run examples/exploration.json --case EXP-C-GRAPH --model YOUR_MODEL --workflow reviewed
```

The reviewed workflow makes up to two sequential calls. The baseline makes one. --max-output-tokens is a per-call limit, not a currency budget; reviewed runs can cost more. Input tokens and actual usage must also be considered when comparing budgets. Calls time out after 120 seconds by default and are not retried automatically. A timeout can still incur charges. No live API call has been verified in this environment.

The adapter sends supplied material to the fixed OpenAI Responses endpoint with store set to false. This flag is not a claim of zero retention under every provider policy. Keys are read from the environment and are not written to run files. Local run files contain research inputs and should be handled accordingly. See the [Responses structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses) for the interface used here.

Every accepted report has source-ID and shape checks. A valid source ID does not prove that the source supports the statement. Novelty, semantic support, and human review remain explicitly unevaluated.

To compare reports against criteria, first create a rule snapshot before generating the two runs:

```powershell
python -m research_workbench review-plan examples/exploration.json --case EXP-C-GRAPH --criteria examples/review-criteria.json --out private/graph-plan.json
```

Then generate or import two reports for the same input and create an anonymous review packet:

```powershell
python -m research_workbench blind runs/FIRST runs/SECOND --plan private/graph-plan.json --out private/comparison-01
```

Share only `private/comparison-01/reviewer`. Read `review-instructions.txt` and `criteria.json`, inspect A/B reports, and fill `rating.json`. Each judgment needs a rationale and valid output location, such as `/findings/0/statement`. All proposed candidates must be assessed. Save each reviewer's result to a different file:

```powershell
python -m research_workbench review-submit private/comparison-01/reviewer private/comparison-01/reviewer/rating.json --out private/reviewer-01.json
```

The result preserves every judgment and derives `pass`, `needs_revision`, `fail`, or `unresolved`. A severe error overrides pass labels; unknown and partial judgments cannot become a pass. Dimensions can be excluded only in the original criteria via a `not_applicable` map with reasons. Rule snapshots and review receipts cannot overwrite existing files.

The packet records whether local rule timestamps precede both run timestamps. This is not external preregistration or a guarantee against deliberate file tampering. A rule snapshot created after the runs is explicitly marked as such. Existing runs are never relabeled as scientifically verified by a review submission: the receipt contains operator-entered judgments and unverified reviewer identity. See [评审操作说明](评审操作说明.md) for the rating format and interpretation.

`organizer-mapping.json` is outside the reviewer folder and reveals identities. Style can still reveal a system, so this is identity-hidden presentation, not proof of complete blinding. Model requests never include evaluation labels; an agent with unrestricted directory access can still read local files. Place model inputs in an isolated directory when using a tool-enabled agent. Keep independent held-out cases outside the public development repository.

The four examples and the sample review criteria are constructed from public literature and already exposed to development. They are calibration materials, not representative user evidence or held-out test cases. Their research judgments still need domain review.

Run the tests:

```powershell
python -m unittest discover -s tests -v
```

If a sandbox prevents use of the system temporary directory, set WORKBENCH_TEST_TEMP to an existing writable scratch directory. Install the optional PDF extra to run the parser and upload tests; otherwise those tests are explicitly skipped. The tests use synthetic PDF fixtures, provider doubles, and review judgments; passing them does not measure scientific idea quality.

The next milestones are actual model validation and baseline comparisons, domain review of selected evidence, and independent user cases. Publication and any claim about adoption require further evidence.
