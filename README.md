# Bug reports to user stories

**Adayane Coutinho**

This repository takes a weak prompt, rewrites it so a model turns a bug report into a user story, publishes the new prompt to the LangSmith Prompt Hub, and scores both versions on the same 15 examples. I built it for an AI Engineering MBA challenge.

On the recorded run, with `gemini-2.5-flash` writing and judging, the original prompt averaged **0.8797 and failed**: F1-Score was 0.73, and the bar requires every metric to clear 0.8. The rewritten prompt averaged **0.9157 and passed**, with every metric at or above 0.8. The table is in [Results](#results).

I wrote the optimized prompt, the Hub pull and push scripts, the structural tests, and the baseline runner that scores the original prompt with the same judges. The scoring loop, the judge definitions, and the dataset came with the course template, [devfullcycle/mba-ia-pull-evaluation-prompt](https://github.com/devfullcycle/mba-ia-pull-evaluation-prompt).

The original challenge statement, in Portuguese, is in [README.pt-BR.md](README.pt-BR.md).

## The problem

Someone files a bug. A product team wants a story they can estimate: who is blocked, what they need to do, why it matters, and acceptance criteria a QA engineer can execute. The report might be one sentence ("the add-to-cart button does nothing on product 1234") or a production incident with logs, a race, and a revenue number. The story has to grow with the report, and it has to stay inside the facts the report actually gives.

The starting prompt, `prompts/bug_to_user_story_v1.yml`, is also published as `leonanluppi/bug_to_user_story_v1`. It was written with those gaps on purpose: a generic assistant, `{bug_report}` pasted into the system message and again into the user message, no example, and no output contract. The pass rule for the rewrite is every metric at or above 0.8 on the same 15 examples, after the new prompt is published to the Hub. An average above 0.8 still fails when one metric is short.

The prompt, the reports, and the reference stories are in Portuguese, which is the language of the dataset.

## What I shipped

1. **Pull.** `src/pull_prompts.py` pulls `leonanluppi/bug_to_user_story_v1` from the LangSmith Prompt Hub and writes `prompts/bug_to_user_story_v1.yml`, splitting the system and user messages.
2. **Rewrite.** `prompts/bug_to_user_story_v2.yml` is the prompt that runs: a role, internal reasoning steps, three worked examples, explicit rules, and edge cases. The user message carries only the bug report.
3. **Push.** `src/push_prompts.py` rejects a prompt that is missing a required field, still contains `TODO`, or lists fewer than two techniques. It publishes `{USERNAME_LANGSMITH_HUB}/bug_to_user_story_v2` as a public Hub repo, with the description, tags, and technique list.
4. **Score the published prompt.** `src/evaluate.py` loads the JSONL file, creates a LangSmith dataset named `{LANGSMITH_PROJECT}-eval` when that name is new, pulls v2 from the Hub, and scores it. The text under test is the Hub copy, so `push_prompts.py` has to run after every edit that should count.
5. **Score v1 with the same judges.** `src/evaluate_v1_baseline.py` builds the v1 chat template from the local YAML and runs the same metrics against the same LangSmith dataset. The challenge statement prints a sample scoreboard to show the CLI. The baseline script is how this README gets a measured comparison.
6. **Lock the shape of the prompt.** `tests/test_prompts.py` checks v2 without calling a model: a non-empty system prompt, a role line (`Você é um` / `You are a`), a user-story or Markdown format, few-shot markers, no leftover `TODO`, and at least two entries in `techniques_applied`.

## Prompt design

`techniques_applied` lists three techniques.

**Few-shot examples.** Three full input/output pairs sit in the system prompt, one for each amount of detail the dataset asks for:

- a simple UI bug: the add-to-cart button on product 1234
- a quantitative bug: a dashboard that shows 50 active users when the list has 42
- a complex incident: intermittent HTTP 500s on about 5% of payments over R$1000, with a gateway timeout in the logs

The pairs show the Markdown contract and, more usefully, how long the criteria should be as the report gets longer. Two of the three reports also appear in the scored file. That overlap is in [Lessons and next steps](#lessons-and-next-steps).

**Role prompting.** The system prompt opens as a senior product manager who writes testable acceptance criteria and ranks work by business impact. The role is there so the answer names a persona and a reason, and keeps the technical facts when the report includes them.

**Chain of thought, kept off the page.** Five steps happen before the answer: who is affected, what they need to do, why it matters, which Given/When/Then checks cover the fix, and how complex the report is. The prompt then requires the story alone. The clarity judge scores concision, so a visible reasoning trace would work against that metric.

The rest of the system prompt is the contract:

- Markdown, in the form `Como um [persona], eu quero [ação], para que [benefício]`, then **Critérios de Aceitação** as Dado / Quando / Então.
- Invent nothing. The persona is specific to the report. The voice is professional and centered on the user.
- 3 to 7 acceptance criteria, with extra criteria grouped in subsections when the bug is complex.
- Keep browser, device, endpoint, error rate, and stated impact when the report has them.
- Edge cases called out in the instructions: a vague report such as "it does not work" (one criterion asks for reproduction steps), several problems in one report (cover each), and a backend job with no end user (the persona is the internal team that feels the failure).

v2 leaves the instructions in the system message. The user message is the report:

```text
Relato de Bug:
---
{bug_report}
---
```

## How evaluation works

Writing and judging are separate chat models, both at temperature 0, chosen in `.env`. The recorded run used Google Gemini for both (`LLM_PROVIDER=google`):

| Role | Variable | Model on the recorded run |
| --- | --- | --- |
| Writes the user story | `LLM_MODEL` | `gemini-2.5-flash` |
| Judges the user story | `EVAL_MODEL` | `gemini-2.5-flash` |

`.env.example` also has an OpenAI pair: `gpt-4o-mini` writes, `gpt-4o` judges. [Results](#results) are the Gemini run.

`src/evaluate.py` does six things:

1. Reads `datasets/bug_to_user_story.jsonl`.
2. Looks up a LangSmith dataset named `{LANGSMITH_PROJECT}-eval`. The recorded run used project `mba-ia`, so the dataset is `mba-ia-eval`. When that dataset already exists, the script keeps it and does not reload the file.
3. Pulls `{USERNAME_LANGSMITH_HUB}/bug_to_user_story_v2` with `langchain.hub.pull`.
4. Invokes `prompt | llm` on each example.
5. Calls three judges in `src/metrics.py` with the bug report, the model answer, and the reference story.
6. Prints five scores and exits 0 only when all five are at least 0.8.

Each judge asks the eval model for one JSON object. When that object cannot be parsed, the judge returns 0 for the example.

| Metric | Where the number comes from | What the judge weighs |
| --- | --- | --- |
| F1-Score | The judge returns a precision and a recall. The code computes `2PR / (P + R)`. | Precision: share of the answer that is correct and relevant. Recall: share of the reference that shows up in the answer. |
| Clarity | One score. The judge prompt says to average four criteria. | Organization, plain language, absence of ambiguity, concision. |
| Precision | One score. The judge prompt says to average three criteria. | No invented facts, stays on this report, agrees with the reference. |

Helpfulness and correctness are averages computed in `evaluate.py` from the three scores above:

| Metric | Formula |
| --- | --- |
| Helpfulness | `(clarity + precision) / 2` |
| Correctness | `(f1_score + precision) / 2` |

The precision field inside F1 comes from the F1 judge. The Precision metric is a separate call. Both derived metrics include that Precision metric, so the five headlines share inputs.

`src/metrics.py` also defines four judges aimed at this task: tone, acceptance-criteria quality, user-story format, and completeness. The pass/fail script calls the three generic judges only. Those four stay in the file for a later scoreboard.

LangSmith stores the dataset, and, with `LANGSMITH_TRACING=true`, the generation and judge calls as traces on the configured project. The five aggregate numbers are printed in the terminal. This README is where the recorded aggregates live.

Links from the passing run. The original write-up says they open for someone logged into the same LangSmith organization:

- [Prompt `bug_to_user_story_v2`](https://smith.langchain.com/prompts/bug_to_user_story_v2/39b1a626?organizationId=8874aa0a-aa8d-4611-91c0-768dcd2c4e98)
- [Tracing project `mba-ia`](https://smith.langchain.com/o/8874aa0a-aa8d-4611-91c0-768dcd2c4e98/projects/p/9966c095-6ff8-442a-b2a3-76360c4ad8fa)
- [Dataset `mba-ia-eval`](https://smith.langchain.com/o/8874aa0a-aa8d-4611-91c0-768dcd2c4e98/datasets/f919af7b-0397-461e-a64b-01a99265a8a2)

## Dataset

`datasets/bug_to_user_story.jsonl` has 15 lines. Each line has `inputs.bug_report`, `outputs.reference` (a full user story), and `metadata` with `domain`, `type`, and `complexity`.

| `complexity` | Count | What the reports contain |
| --- | ---: | --- |
| `simple` | 5 | One-sentence UI, validation, or display bugs |
| `medium` | 7 | Reproduction steps or one technical cause: a webhook returning HTTP 500, a sales report with no index on `data_venda`, a missing authorization check on `GET /api/users/:id`, a discount applied to a single line item, an Android list that triggers an ANR, a checkout that skips the stock check, a modal rendered under the sidebar |
| `complex` | 3 | Several faults in one report, described below |

The three complex reports:

- **Checkout.** XSS in the coupon field, `POST /api/payment/process` returning 504 on 30% of calls with "connection pool exhausted", coupon `PROMO10` used 147 times against a limit of 100, and a spinner that never ends. The report cites 150+ customers, an estimated R$15,000 in improper discounts, and 45 support tickets.
- **Executive reports.** An N+1 query on `GET /api/reports/executive-dashboard` (45 seconds against a 3-second SLA), three disagreeing MRR figures (R$150,000, R$145,000, R$147,500), a Redis TTL of 24 hours, and a CSV export that grows to 4 GB and is OOM-killed.
- **Offline-first sync.** Conflicting edits resolved by last-write-wins, a 50 MB upload that restarts from 0% after a dropped connection, operations applied out of client order, and a crash while flushing 1,500 pending changes (850 MB measured, against an iOS limit of 700 MB).

Domains in the file: e-commerce (4), SaaS (6), mobile (2), ERP (1), CRM (1), mobile + backend (1).

The reference stories on the complex rows are long. They include acceptance criteria, a technical-context section, and suggested engineering tasks. Recall, inside F1, is scored against that text, so a short and clean story can still land a low F1 when it drops the context the reference carries.

## Results

These are the figures recorded in this repository, from one v1 run (`python src/evaluate_v1_baseline.py`) and one v2 run (`python src/evaluate.py`). Same 15 examples, same model (`gemini-2.5-flash`) on both sides of the comparison. Per-metric cells are the two-decimal values recorded for that run. The averages are the four-decimal values the scripts printed. Per-example scores and intermediate iterations are not stored. Nothing here was re-measured for this write-up.

| Metric | v1 | v2 |
| --- | ---: | ---: |
| Helpfulness | 0.94 | 0.95 |
| Correctness | 0.84 | 0.89 |
| F1-Score | 0.73 | 0.84 |
| Clarity | 0.94 | 0.96 |
| Precision | 0.95 | 0.94 |
| **Average** | **0.8797** | **0.9157** |
| **Status** | **Failed** | **Passed** |

v1 cleared 0.8 on helpfulness, correctness, clarity, and precision, and its average was 0.8797. It failed because F1-Score was 0.73. Correctness on that run is 0.84, the average of F1-Score 0.73 and Precision 0.95, which is why a missed coverage score can still sit above the correctness line. v2 brought F1-Score to 0.84, every metric cleared 0.8, and the recorded average was 0.9157. That average is also the figure in the commit that added the prompt. Precision on v2 is 0.94, next to 0.95 on v1.

The sample scoreboard in the challenge statement illustrates the terminal layout. The table above is the measured run.

## Stack

- Python 3.11 or 3.12 for this project. The challenge accepts 3.9 and newer. On 3.14, `pydantic-core` may still be missing a wheel, and the install then needs a local Rust build.
- LangChain `0.3.13` and `langchain-core` `0.3.28`, for `ChatPromptTemplate`, `hub.pull`, and `hub.push`.
- LangSmith `0.2.7`, for the Prompt Hub, the evaluation dataset, and tracing.
- `langchain-google-genai` `2.0.8` on the recorded run. `langchain-openai` `0.2.14` is wired for the other provider.
- PyYAML `6.0.3`, python-dotenv `1.0.1`, Pydantic `2.13.4`, pytest `8.3.4`.

## How to run

You need a [LangSmith API key](https://smith.langchain.com) and either a [Google AI Studio key](https://aistudio.google.com/app/apikey) or an [OpenAI key](https://platform.openai.com/api-keys).

```bash
python -m venv venv
source venv/bin/activate          # Windows PowerShell: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

Values that match the recorded run:

```bash
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=mba-ia           # dataset name becomes mba-ia-eval
USERNAME_LANGSMITH_HUB=...         # Hub handle; the comment in .env.example says where to read it
GOOGLE_API_KEY=...
LLM_PROVIDER=google
LLM_MODEL=gemini-2.5-flash
EVAL_MODEL=gemini-2.5-flash
```

```bash
python src/pull_prompts.py                  # Hub → prompts/bug_to_user_story_v1.yml
python -m pytest tests/test_prompts.py -v   # structural checks, no API calls
python src/push_prompts.py                  # local v2 → a public Hub repo
python src/evaluate.py                      # score the published prompt
python src/evaluate_v1_baseline.py          # optional: same judges on local v1
```

A v2 run is 15 generations and 45 judge calls (three judges on each example). The challenge statement estimates about $1–5 on OpenAI for the whole exercise, and quotes a Gemini free-tier limit of 15 requests per minute and 1,500 per day. This repository has no separate cost log. The scripts send calls back to back, so a free-tier key can hit that per-minute cap during a full run.

When a metric comes back under 0.8, edit `prompts/bug_to_user_story_v2.yml`, push again, and re-run `evaluate.py`. The evaluator reads the Hub copy.

## Lessons and next steps

The v1 numbers are the part worth keeping. With `gemini-2.5-flash`, a thin prompt already produced clear, on-topic prose, and the run still failed on coverage of the reference. The few-shot pairs are aimed at that gap: they show the persona, the benefit, the criteria, and the technical context the reference carries, which is what the recall half of F1 rewards. Keeping the chain of thought inside the prompt is the matching choice on the clarity side, because that judge is asked to reward a concise answer.

From the code and the files, this is the follow-up work:

- **Take the demonstrations off the scored rows.** The add-to-cart report and the dashboard-count report are pasted into v2 with answers that match the dataset references. That is 2 of the 15 scored examples. The payments-timeout demonstration is original to the prompt. Per-example scores are not stored, so this repository cannot show how far those two rows moved the average. I would write demonstrations that are absent from the JSONL, or drop those two rows from the scored set.
- **Use one complexity scale.** v2 introduces the dashboard report as a medium bug. The dataset tags the same report `complexity: simple`. I would pick one scale and use it in the prompt and in the file before slicing scores by difficulty.
- **Reload the dataset when the file changes.** If `{LANGSMITH_PROJECT}-eval` already exists, `create_evaluation_dataset` returns it and leaves the examples as they were on the first upload. I would version the dataset name, or replace the examples on each run, so a later edit to the JSONL is what gets scored.
- **Score the task, and store the number next to the trace.** Tone, acceptance criteria, format, and completeness already have judge prompts in `metrics.py`. The gate is the generic trio plus two averages of those three scores. I would put the four task judges on the pass/fail line, keep clarity, precision, and F1 as diagnostics, and upload each score as LangSmith feedback. The project has the traces and the dataset. The 0.9157 average is in the terminal output and in this README.
- **Separate the writer from the judge, and run the set more than once.** This run used `gemini-2.5-flash` in both roles. `.env.example` already has a split: `gpt-4o-mini` writes, `gpt-4o` judges. Recorded F1 is 0.84, just over the 0.8 bar, from a single pass. I would repeat the set before treating that gap as stable.

The original write-up pointed at four screenshots under `docs/screenshots/`. Those files are outside this repository (`screenshots/` is gitignored). The LangSmith links above are the evidence recorded here.

## Layout

```text
prompts/bug_to_user_story_v1.yml    weak prompt, also pulled from the Hub
prompts/bug_to_user_story_v2.yml    rewritten prompt
datasets/bug_to_user_story.jsonl    15 reports and reference stories
src/pull_prompts.py                 Hub → local v1
src/push_prompts.py                 local v2 → public Hub repo
src/evaluate.py                     score the published v2 prompt
src/evaluate_v1_baseline.py         score local v1 with the same judges
src/metrics.py                      judge prompts and the F1 formula
src/utils.py                        YAML, env checks, LLM factory
tests/test_prompts.py               six structural checks on v2
README.pt-BR.md                     original challenge statement, in Portuguese
```
