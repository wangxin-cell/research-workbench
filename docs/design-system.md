# Interface design

Research Workbench is a reading and decision workspace. Keep the research question, supplied evidence, resource constraints, and next experiment legible. Do not add novelty scores, decorative charts, or claims of research quality to make the interface feel more complete.

The October 2026 refresh used UI UX Pro Max as design guidance, installed from `nextlevelbuilder/ui-ux-pro-max-skill` at commit `623a9a9037d006ea727f8213f084d02a6b6f11b5`. Its flat-design, contrast, form feedback, and responsive recommendations informed this implementation. Suggested marketing-page layouts were not applicable. The skill is a development aid, not an application dependency.

## Shared visual rules

| Role | Value |
| --- | --- |
| Main text | `#18302d` |
| Secondary text | `#586c67` |
| Primary action and links | `#176b5b` |
| Page background | `#f5f7f5` |
| Surface | `#ffffff` |
| Surface divider | `#dce5e0` |
| Input border | `#7d9185` |
| Placeholder text | `#6b7a70` |
| Caution text / background | `#85571b` / `#fff5df` |

Use system fonts: Segoe UI, Microsoft YaHei, PingFang SC, and system-ui. Reports must remain self-contained and readable offline, so there are no remote fonts, icon libraries, or scripts. Use consistent inline outline SVGs in the workspace. Labels must remain visible. Prefer 8px spacing increments, 12–16px surface radii, and restrained borders over decorative effects.

The workspace collapses to one column below 1001px; the fixed sidebar becomes a top navigation area below 761px. History remains reachable through a disclosure. Inputs use 16px text on small screens. Dialogs retain native keyboard focus management and visible close controls. Respect reduced motion and preserve focus indicators.

## Workflow presentation

- With no API key configured, exporting a prompt is the primary action. Exported snapshots lead to prompt download and response import. API settings remain available in a disclosure.
- A configured key is described as configured, not as a verified model connection. Direct generation still explains where selected material is sent and that API costs apply.
- Report sections distinguish source facts, derivations, and inferences. Candidate cards show overlap, potential differences, first tests, and uncertainties. Source links jump to the actual supplied content.
- Form errors appear inside the open dialog. Errors after a dialog has closed appear on the page.

## Validation of this refresh

The existing 58 tests passed with PDF support enabled. JavaScript syntax and Git whitespace checks passed. Browser checks covered 375, 390, 768, 1024, and 1440px widths, with no document-level horizontal overflow observed. The report also fit a 319px iframe viewport.

The four constructed cases loaded successfully. Manual browser checks exercised offline prompt preparation, malformed JSON feedback, importing the existing manually authored report, citation navigation, PDF upload and excerpt selection, Escape dismissal, and invalidation of a prepared snapshot after editing inputs. Browser console checks found no warnings or errors in this flow. Screenshots show the actual local interface.

These checks verify software behavior and presentation. They do not validate research usefulness. Live paid model calls, every arXiv network failure, a screen-reader audit, and a physical print inspection were not part of this visual refresh.
