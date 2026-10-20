Created the project folders and Python dependency list for the inventory assistant.
Added an environment-variable template and Git ignore rules to keep API keys, local databases, and runtime files out of version control.
Configured the project to use Google's Gemini API with the official google-genai Python SDK.
The Gemini API key and model name will be loaded from the local .env file instead of being written into source code.
Created separate inventory and private databases with Faker-generated store data; cost, salary, and profit records are kept only in private.db.
Added a row-count checker to verify the sample data and included a poisoned product description for later security testing.
Added a read-only inventory connection with a SQLite authorizer and a SQL validation layer that allow only approved SELECT queries.
Added security tests for write statements, private table names, multiple statements, ATTACH, PRAGMA, UNION, and the 50-row limit.
Added a Gemini text-to-SQL wrapper that reads its API key and model name from .env and uses only the approved inventory schema in its prompt.
Protected financial and HR questions return a refusal marker before a Gemini request is made; response cleanup removes Markdown SQL fences.
Added the question pipeline that validates and runs generated SQL, retries one SQLite execution error, and returns answer, SQL, rows, and status.
Added answer generation in llm.py with explicit handling of untrusted database rows, plus offline and real-database tests for refusal, retries, and errors.
Added JSON-lines audit logging for each question, generated SQL, allowed/blocked/error status, and result count.
Connected the pipeline to the logger so successful, blocked, and failed requests all produce an audit record.
Added a Streamlit chat screen with example inventory questions and an expandable SQL view under each reply.
Added a sidebar explaining the inventory data available to the AI and the financial and HR data it cannot access.
Updated the sample Gemini model after the API rejected the old model for this new key; kept the API key unchanged.
Added safe terminal diagnostics so Gemini and pipeline failures are easier to identify without printing API keys.
