# Tool-Using Research Agent

A small Python research agent that searches the public web, fetches pages, and answers with citations linked to successfully fetched sources. It has two tools (`web_search` and `fetch_page`), a strict tool-call budget, and graceful fallbacks for failed or empty results.

## How it works

The default planner is deterministic and needs no model account: it searches the question, fetches available results until it reaches the step limit, and extracts a question-relevant sentence from fetched pages. Set an OpenAI-compatible model to let a model choose between search, fetch, and finish actions. The optional model can use OpenAI, a compatible hosted service, or a local endpoint such as Ollama. Both modes share the same allowlist, fetched-source citation checks, and hard budget.

Every answer citation `[n]` points to the numbered fetched sources printed below the answer. Model-generated sentences without a valid citation are removed. If nothing was fetched, the agent says it cannot provide a source-grounded answer. The extractive default is deliberately conservative and may return snippets rather than a polished synthesis.

## Requirements

- Python 3.10 or newer
- Internet connection for DuckDuckGo search and source fetching
- Optional: an OpenAI-compatible chat completions endpoint for model-directed planning and synthesis

## Setup

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
```

Environment variables are optional. Export them in your shell or load `.env` with your preferred environment loader. No dotenv dependency is required.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MAX_STEPS` | `6` | Maximum calls to any research tool in a run |
| `SEARCH_RESULTS` | `5` | Maximum search results returned |
| `REQUEST_TIMEOUT` | `15` | Timeout in seconds for search/fetch requests |
| `RESEARCH_AGENT_MODEL` | unset | Model ID; unset means deterministic extractive mode. For OpenRouter, use its `provider/model` ID. |
| `OPENAI_API_KEY` | unset | Key for an OpenAI-compatible endpoint |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible API root; for Ollama, commonly `http://localhost:11434/v1` |
| `OPENROUTER_API_KEY` | unset | OpenRouter key; takes precedence over `OPENAI_API_KEY` |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter API root |
| `OPENROUTER_SITE_URL` | unset | Optional site URL sent as OpenRouter's `HTTP-Referer` header |
| `OPENROUTER_APP_NAME` | `Tool-Using Research Agent` | Optional app title sent as OpenRouter's `X-Title` header |

## Run

```bash
research-agent "What are the main causes of coral bleaching?" --max-steps 6
```

Or run from the source checkout without installing the entry point:

```bash
python -m research_agent.cli "What is the James Webb Space Telescope designed to study?"
```

With an OpenAI-compatible model configured, the model selects tools and writes the synthesis. Example for OpenRouter:

```powershell
$env:RESEARCH_AGENT_MODEL = "<provider>/<model>"
$env:OPENROUTER_API_KEY = "your-openrouter-api-key"
$env:OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
research-agent "How do heat pumps work?" --max-steps 6
```

Choose a currently available model ID from your [OpenRouter models list](https://openrouter.ai/models); model IDs and availability can change. You can put these values in `.env` and export/load them in your shell. For example, on macOS/Linux:

```bash
export RESEARCH_AGENT_MODEL="<provider>/<model>"
export OPENROUTER_API_KEY="your-openrouter-api-key"
export OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
research-agent "How do heat pumps work?" --max-steps 6
```

For an Ollama server instead (use a model installed locally):

```powershell
$env:RESEARCH_AGENT_MODEL = "qwen2.5:7b"
$env:OPENAI_API_KEY = "ollama"
$env:OPENAI_BASE_URL = "http://localhost:11434/v1"
research-agent "How do heat pumps work?" --max-steps 6
```

The tool budget counts search and fetch calls. A result with `--max-steps 1` can search but cannot fetch, so it will correctly decline to provide a sourced answer. Set the limit high enough to fetch a few sources (for example, 6).

## Example runs

The excerpts below illustrate the output format; web results and page contents vary over time.

### 1. Coral bleaching

```text
$ research-agent "What causes coral bleaching?" --max-steps 4

Coral bleaching occurs when stressed corals expel the symbiotic algae living in their tissues [1]
High ocean temperatures are a major stressor associated with mass bleaching events [2]

Sources:
[1] Coral bleaching — https://oceanservice.noaa.gov/facts/coral_bleach.html
[2] Coral reefs and climate change — https://www.noaa.gov/education/resource-collections/ocean-coasts/coral-reef

Tool calls: 3/4
```

### 2. James Webb Space Telescope

```text
$ research-agent "What does the James Webb Space Telescope study?" --max-steps 4

Webb observes the universe in infrared light and studies the early universe, galaxies, stars, and planetary systems [1]

Sources:
[1] Webb telescope overview — https://science.nasa.gov/mission/webb/

Tool calls: 2/4
```

### 3. Heat pumps, including an empty-result fallback

```text
$ research-agent "How does a heat pump heat a home?" --max-steps 1

I could not fetch any sources, so I can’t provide a source-grounded answer.

Tool calls: 1/1
Note: Stopped at the hard limit of 1 tool calls.
```

Increase the budget to allow fetching pages for a cited answer:

```text
$ research-agent "How does a heat pump heat a home?" --max-steps 4

A heat pump moves heat rather than generating it by combustion, transferring energy between indoor and outdoor air [1]

Sources:
[1] Heat pump systems — https://www.energy.gov/energysaver/heat-pump-systems

Tool calls: 2/4
```

## Tests

```bash
pytest
```

Tests use fake tools and make no network requests. They cover source citations, empty search, failed fetches, invalid input, and the hard step cap.

## Project layout

```text
.
├── .env.example
├── pyproject.toml
├── requirements.txt
├── src/research_agent/
│   ├── agent.py       # bounded planner loop, citation guard, extractive answer
│   ├── cli.py         # command line interface
│   └── tools.py       # DuckDuckGo search and HTML page fetcher
└── tests/test_agent.py
```

## Walkthrough recording script (about 2 minutes)

1. **Intro (0:00–0:15):** “This is a local research agent. It has a search tool and a page-fetch tool, and every answer cites pages it actually fetched.” Show the repository layout and README.
2. **Setup (0:15–0:35):** Show the environment creation and `pip install -e ".[dev]"`. Mention that the extractive mode requires no model key.
3. **Run a research question (0:35–1:05):** Run `research-agent "What causes coral bleaching?" --max-steps 4`. Point out citation numbers and matching source URLs.
4. **Show the budget/failure behavior (1:05–1:30):** Run a question with `--max-steps 1`; explain that search consumes the only call, leaving no fetched evidence, so the agent declines to make factual claims.
5. **Show the implementation and tests (1:30–1:55):** Briefly show the `ResearchAgent.run` loop, `max_steps` guard, citation validation, and run `pytest`.
6. **Close (1:55–2:00):** “The loop is bounded, tools fail gracefully, and uncited model statements are filtered.”
