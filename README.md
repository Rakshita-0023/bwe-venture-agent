# BWE Venture Intelligence Agent

Local-first AI research system for Bold World Engineering / BWE Studio. It crawls the public website, extracts ventures and blog-style insights, builds a local knowledge base, answers grounded questions with Ollama, and generates thesis reports for product-fit exploration.

## Quickstart

```bash
cd bwe-venture-agent

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

ollama serve
ollama pull llama3.1
ollama pull nomic-embed-text

python src/cli.py crawl
python src/cli.py analyse
python src/cli.py align
python src/cli.py style-guide
python src/cli.py build-kb
python src/cli.py ask "What does Bold World Engineering do?"
python src/cli.py ask "What product thesis fits BWE best?" --voice bwe
streamlit run src/app.py
```

## What It Does

- Crawls public BWE pages and stores clean page data locally
- Extracts venture records and blog/insight summaries without hallucinating missing fields
- Builds a local ChromaDB-backed knowledge base
- Uses LlamaIndex + Ollama for grounded Q&A
- Generates markdown research reports
- Ranks ventures by personal alignment to a technical/product profile
- Extracts a reusable BWE voice/style guide from blogs and case studies
- Supports a BWE-style grounded answer mode
- Serves a simple Streamlit dashboard for demos

## Architecture

1. `src/crawler.py`
   Crawls internal public pages from `https://boldworldengineering.com/`, respects `robots.txt`, and stores cleaned page records in `data/processed/pages.json`. Because BWE uses a client-rendered frontend, the crawler also enriches the scrape with public venture/blog/case-study data exposed by the live site.
2. `src/extractor.py`
   Reads crawled pages and produces structured `ventures.json` and `blogs.json`.
3. `src/knowledge_base.py`
   Loads scraped content into a local Chroma vector store with LlamaIndex and Ollama embeddings.
4. `src/analyst.py`
   Produces research reports, personal venture alignment, and grounded answers using the local knowledge base and local files.
5. `src/app.py`
   Streamlit dashboard for overview, ventures, blogs, reports, personal venture fit, and BWE voice mode.
6. `src/style_analyzer.py`
   Extracts the observed BWE writing style into a local style guide and powers the BWE-style answer mode.
7. `src/cli.py`
   Command entry point for `crawl`, `analyse`, `align`, `style-guide`, `build-kb`, and `ask`.

## Folder Structure

```txt
bwe-venture-agent/
  README.md
  requirements.txt
  data/
    raw/
    processed/
    reports/
    chroma_db/
  src/
    app.py
    style_analyzer.py
    cli.py
    crawler.py
    extractor.py
    knowledge_base.py
    analyst.py
    config.py
    utils.py
```

## Setup

Python `3.12` is recommended for the smoothest dependency install.

```bash
cd bwe-venture-agent
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Ollama Setup

Install Ollama from [ollama.com](https://ollama.com/) and make sure the local server is running:

```bash
ollama serve
```

Pull a model:

```bash
ollama pull llama3.1
ollama pull nomic-embed-text
```

If `llama3.1` is not installed, the app can use another local model by setting:

```bash
export BWE_OLLAMA_MODEL=gemma3:1b
export BWE_OLLAMA_EMBED_MODEL=nomic-embed-text
```

## Run The Pipeline

```bash
python src/cli.py crawl
python src/cli.py analyse
python src/cli.py align
python src/cli.py style-guide
python src/cli.py build-kb
python src/cli.py ask "What does Bold World Engineering do?"
python src/cli.py ask "What ventures are listed?"
python src/cli.py ask "Which ventures align with me most?"
python src/cli.py ask "What product thesis fits BWE best?" --voice bwe
streamlit run src/app.py --server.address 127.0.0.1 --server.port 8501
```

On the latest verified run for this project, Ollama used:

- Completion model: `llama3.1`
- Embedding model: `nomic-embed-text`

If `llama3.1` is not installed locally, the app falls back to another installed completion model such as `gemma3:1b`.

## Commands

```bash
python src/cli.py crawl
python src/cli.py analyse
python src/cli.py align
python src/cli.py style-guide
python src/cli.py build-kb
python src/cli.py ask "What does Bold World Engineering do?"
python src/cli.py ask "What ventures are listed?"
python src/cli.py ask "Which ventures align with me most?"
python src/cli.py ask "What product thesis fits BWE best?" --voice bwe
streamlit run src/app.py
```

## Dashboard

The Streamlit dashboard includes:

- `Overview`
- `Ventures`
- `Blog Intelligence`
- `Ask Agent`
- `My Venture Fit`
- `Product Thesis`
- `BWE Voice Mode`

The Ask section loads the existing local knowledge-base logic and returns grounded answers with sources. The BWE Voice Mode tab adds a second answer path that preserves grounding but rewrites the answer in a BWE-style venture-studio tone based on the extracted local style guide.

Open locally at:

- [http://127.0.0.1:8501](http://127.0.0.1:8501)

## Output Files

- Page data: `data/processed/pages.json`
- Ventures: `data/processed/ventures.json`
- Blogs: `data/processed/blogs.json`
- Personal alignment data: `data/processed/personal_alignment.json`
- Personal profile: `data/personal_profile.md`
- Vector DB: `data/chroma_db/`
- Reports:
  - `data/reports/bwe_overview.md`
  - `data/reports/venture_list.md`
  - `data/reports/blog_insights.md`
  - `data/reports/product_fit_and_thesis.md`
  - `data/reports/personal_venture_alignment.md`
  - `data/reports/bwe_voice_style_guide.md`

## Verified Generated Files

After a full successful run, the project generates:

- `data/raw/` HTML snapshots and public source JSON captures
- `data/processed/pages.json`
- `data/processed/ventures.json`
- `data/processed/blogs.json`
- `data/processed/personal_alignment.json`
- `data/chroma_db/` local vector database files
- `data/reports/bwe_overview.md`
- `data/reports/venture_list.md`
- `data/reports/blog_insights.md`
- `data/reports/product_fit_and_thesis.md`
- `data/reports/personal_venture_alignment.md`
- `data/reports/bwe_voice_style_guide.md`

## Limitations

- The crawler only sees public pages reachable from the site and sitemap.
- If content is heavily client-rendered or hidden behind forms, it may be missed. This project mitigates that for BWE by also reading the public data backing the live website.
- Venture and blog extraction are heuristic and only fill fields supported by the scraped text.
- Q&A is limited to the scraped BWE content and intentionally refuses unclear answers.
- Personal venture alignment is a user-profile analysis, not an official BWE ranking.
- BWE voice mode changes presentation style, not the grounding source; it still relies on scraped content and local reports.
- Ollama must be running locally for embeddings and answers.

## Ethical Scraping Note

- The project only targets public pages.
- It checks `robots.txt` and avoids blocked paths such as `/api/`.
- It adds delay between requests.
- It does not attempt login, admin, or private pages.

## Demo Explanation

This project is a local-first AI venture intelligence agent for BWE Studio. It scrapes public BWE content, extracts ventures and insights, builds a local knowledge base with ChromaDB and LlamaIndex, answers grounded questions through Ollama, and generates product-fit and thesis reports in a Streamlit dashboard.

## Demo Flow

Use this flow for HR, mentor, or internship demos:

1. Open the dashboard and start on the hero + metric cards.
2. Show `Overview` as the executive briefing layer.
3. Show `Ventures` and filter by sector or product type.
4. Show `Blog Intelligence` to demonstrate market/theme extraction.
5. Spend most of the demo in `Ask Agent`.
6. Open `My Venture Fit` to show which ventures match your profile and what you could contribute.
7. Finish with `BWE Voice Mode` or `Product Thesis` to show strategy output and voice-aware generation.

Suggested questions:

- `What does Bold World Engineering do?`
- `What ventures are listed?`
- `Which ventures align with me most?`
- `Which venture looks most promising based on available content?`
- `What sectors does BWE focus on?`
- `What should BWE build next?`
- `What product thesis fits BWE best?`
