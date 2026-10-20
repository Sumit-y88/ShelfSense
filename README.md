# ShelfSense: Supermart Inventory Assistant

ShelfSense is a Streamlit app for asking natural-language questions about a sample supermart inventory. Gemini turns questions into SQL, and the app runs approved queries against a read-only SQLite database.

## Features

- Sample inventory with 100 grocery and household products, 10 categories, 10 suppliers, and 500 sales.
- Retail prices in Indian Rupees (INR), stock counts, and reorder levels.
- Generated SQL shown with each assistant response.
- Read-only query validation limited to approved inventory tables and at most 50 rows.
- A separate private database for product costs, employee records, and profit reports.
- Local JSON Lines audit records in `logs/queries.log`.

## Requirements

- Python
- A Gemini API key for natural-language questions

## Setup on Windows

Run these commands from the project folder in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` and add your Gemini API key. Keep the model name set to a model available to your API key:

```dotenv
GEMINI_API_KEY=your_gemini_api_key
MODEL_NAME=gemini-3.5-flash-lite
```

Create or refresh the local sample databases, then launch the app:

```powershell
.\.venv\Scripts\python.exe .\src\create_db.py
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Streamlit prints a local URL after startup. The database generator uses a fixed sample catalog and updates seeded rows when run again.

## Example questions

- Which grocery products are low on stock?
- Show me the 5 most recent sales.
- List pantry items with their prices.
- Which suppliers are in Mumbai?

## Data and access boundaries

The assistant can read product names and descriptions, categories, supplier names and cities, selling prices, stock levels, and sales quantities and dates. Product prices use INR.

The public inventory database is `data/inventory.db`. The separate `data/private.db` contains cost, employee, and profit data; the assistant's database connection is restricted to the approved tables in `inventory.db`. The sample catalog also includes one prompt-injection description used as a security fixture.

Query audit records may include the question text and generated SQL. They are stored locally in `logs/queries.log` and should not be committed.

## Project files

- `app.py` — Streamlit chat interface.
- `src/llm.py` — Gemini prompts and API calls.
- `src/db_safe.py` — SQL validation and read-only database access.
- `src/pipeline.py` — Question-to-answer flow.
- `src/create_db.py` — Generate or refresh sample databases.
- `src/check_db.py` — Print local database row counts.
- `tests/` — Offline safety and pipeline tests.

Run the test suite with:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## GitHub notes

`.gitignore` excludes `.env`, local SQLite databases, virtual environments, Python caches, test output, and runtime logs. Commit `.env.example` as the configuration template; never commit the actual `.env` file or API key.
