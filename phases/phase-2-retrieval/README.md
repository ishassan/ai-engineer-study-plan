# Phase 2 lab: retrieval over English and Arabic documents

Weeks 4 to 7 of the [study plan](../../README.md#phase-2-retrieval-weeks-4-to-7). At the end, the assistant of Phase 1 has a fourth tool that searches 100 public documents in English and Arabic. Each answer cites the document title, the page and the chunk ID of its sources, and you know the recall of your search for each language.

The lab gives you the documents list, the download script, the database tables, the two model services and their client. You write the parts that the phase teaches:

| Week | You write | File |
| --- | --- | --- |
| 4 | Parse a PDF, normalise the Arabic text, chunk and store | `assistant/ingest.py` |
| 5 | The vector column and its HNSW index | a new file in `db/migrations/` |
| 5 | Embed the chunks, and the vector search | `assistant/ingest.py`, `assistant/retrieval.py` |
| 5 | 50 retrieval questions | `evals/retrieval_questions.jsonl` |
| 5 | The recall measurement | `evals/recall.py` |
| 6 | The text-search column and its index | a new file in `db/migrations/` |
| 6 | Keyword search, rank fusion, re-ranking, one entry point | `assistant/retrieval.py` |
| 7 | The tool `search_documents` | `assistant/tools.py` |
| 7 | Citations in the typed answer | `assistant/schemas.py` |
| 7 | The rule that rejects a wrong citation | `assistant/agent.py` |

**Cost:** the embedding model and the re-ranking model run in Docker on your machine, so weeks 4 to 6 cost nothing. The offline checks are free. The only live check of the phase is in week 7, and it costs about $0.01 (an estimate, see week 7, step 4). You draft the 50 retrieval questions with Claude Code, which uses your subscription and no API credit.

## Before you start

- **Phase 1 is complete.** `make check PHASE=1` passes. Week 7 changes three files that you wrote in Phase 1.
- **Disk space: about 6 GB.** The two models are about 2.3 GB each, in two Docker volumes. The documents take 58 MB. The image of the model server for Apple Silicon is a download of 117 MB.
- **Memory: about 6 GB for Docker.** Measured on the build machine of this lab: the embedding service used 2.5 GiB, the re-ranking service 3.0 GiB and Postgres 0.3 GiB. Make sure that the memory limit in the Docker Desktop settings is higher than the sum.
- **Time.** The first `make up` downloads both models (2 x 2.3 GB). The time depends on your network and was not measured. After that, a service starts in 31 s to 99 s from its volume, with no network access.

The times in this guide were measured on a Linux machine with 4 x86 CPU cores, 15 GiB of memory and no GPU, not on a Mac. On that machine, `make embed` took 44 minutes, and the re-ranking took about 20 s for each question. Times on Apple Silicon were not measured. Use the numbers to plan your week, and write your own numbers in [RESULTS.md](RESULTS.md).

## Setup

Run these commands from the repository root.

```bash
make start PHASE=2
```

This command copies the new files of the phase: `assistant/embeddings.py`, `assistant/ingest.py`, `assistant/retrieval.py`, `evals/recall.py` and `evals/retrieval_questions.jsonl` (two example questions). It also turns on the Python packages of the phase (PyMuPDF and httpx) and the Docker services of the phase. It does not change a file that exists.

Your `.env` is from Phase 1. Copy the Phase 2 lines of `.env.example` into it. On an Apple Silicon Mac the defaults are correct. On an Intel or AMD machine, also add this line, because the default image of the model server is for Apple Silicon only:

```bash
TEI_TAG=cpu-1.9.4
```

```bash
make up
```

`make up` now also starts two copies of [Text Embeddings Inference](https://huggingface.co/docs/text-embeddings-inference/index) (TEI): `embeddings` with `BAAI/bge-m3` on port 8081, and `reranker` with `BAAI/bge-reranker-v2-m3` on port 8082. It waits until both models are loaded. Follow the first download with:

```bash
docker compose --profile phase2 logs -f embeddings reranker
```

Then download the documents and run the checks of week 4:

```bash
make documents
```

```bash
make check WEEK=4
```

The 12 checks fail. Some of them show as errors, because the tables are still empty. Each failing check names a step of week 4.

## How the lab works

- **Steps.** Each week below has the same steps as the plan, in the same order.
- **Checks need your local services.** The checks of week 4 need Postgres and the documents. The checks of weeks 5, 6 and 7 also need both model services and the vectors of the chunks (`make embed`). They call no paid service. Week 7 uses the stand-in for the Claude API of Phase 1. On the build machine the checks took: week 4 2 s, week 5 6 s, week 6 53 s, week 7 about 2 minutes. Most of the time of weeks 6 and 7 is the re-ranking model.
- **Live check.** `make check-live WEEK=7` is the only one in this phase. It calls the real Claude API with your key.
- **Migrations.** `make up` applies each new file in `db/migrations/` one time, in the order of the names. A file that ran does not run again when you edit it. To change a migration that ran, add a new file, or run `make reset` (it deletes the database, see [Commands](#commands)).
- **Your design.** The checks look at the database, the results of your functions, the result file and the event stream of `/ask`. Inside the files you can add functions and change the structure. Keep only the names in the table below.

| Name | Where | Used by |
| --- | --- | --- |
| `parse_pdf(path) -> list[str]` | `assistant/ingest.py` | Week 4 checks. One string for each page, also for an empty page |
| `normalise_arabic(text) -> str` | `assistant/ingest.py` | Week 4 checks |
| `chunk_text(text, size, overlap) -> list[str]` | `assistant/ingest.py` | Week 4 checks. Defaults: `CHUNK_WORDS = 150`, `OVERLAP_WORDS = 30` |
| `ingest_document(document, path) -> int` | `assistant/ingest.py` | Week 4 checks |
| `embed_chunks() -> int` | `assistant/ingest.py` | `make embed` |
| `vector_search(query_text, k=5)`, `keyword_search(query_text, k=5)` | `assistant/retrieval.py` | Checks of weeks 5 and 6 |
| `reciprocal_rank_fusion(rankings, k=60)` | `assistant/retrieval.py` | Week 6 checks. Returns `(id, score)` pairs, best first |
| `retrieve(query_text, mode="rerank", k=5)`, `CANDIDATES = 20` | `assistant/retrieval.py` | Week 6 checks, `evals/recall.py`, the notebook |
| `measure(questions, modes, k=5)`, `python -m evals.recall` | `evals/recall.py` | Checks of weeks 5 and 6 |
| `evals/results/recall.json` | written by `make recall` | Checks of weeks 5 and 6 |
| `evals/retrieval_questions.jsonl` | your questions | Checks of weeks 5 and 7 |
| `search_documents` in `TOOLS`, `run_tool()` | `assistant/tools.py` | Week 7 checks |
| `Answer.citations` | `assistant/schemas.py` | Week 7 checks |

These contracts are also fixed:

- **A search result** is a dict with the keys `chunk_id`, `document_id`, `title`, `language`, `page`, `text` and `score`. The best result comes first, and a better result has a higher score.
- **A chunk ID** is `<document_id>:p<page>:c<n>`, for example `gastat-land-transport-en:p7:c2`. Page and `n` start at 1, and `n` counts the chunks of one page.
- **The tables** `documents` and `chunks` are in `db/migrations/0002_documents.sql`. You add a column of the type `vector(1024)` with an HNSW index, and a column of the type `tsvector` with a GIN index. The names of the columns and indexes are free: the checks find them by type and by `USING hnsw` and `USING gin`.
- **The document ID `lab-check-document`** belongs to the week 4 checks. They store it and delete it after the test.

### Changes to files from Phase 1

`make start PHASE=2` does not touch `assistant/tools.py`, `assistant/schemas.py` and `assistant/agent.py`. In week 7 you change them yourself: a fourth tool, a new field of `Answer`, and the rule that rejects a wrong citation. The week 2 checks of Phase 1 now accept more tools than the three of Phase 1, so `make check PHASE=1` stays green when you add the fourth one.

## Week 4: Parse and chunk the documents

### Step 1. Read

Huyen, chapter 6: RAG, RAG Architecture and Retrieval Algorithms (pages 253 to 268).

### Step 2. The documents

The lab gives this step. `data/documents.csv` lists 100 public PDF files of the General Authority for Statistics (stats.gov.sa): 50 in English and 50 in Arabic, 2342 pages in all. Most of them are the methodology and quality report of one statistical product, in both languages. These reports describe the subjects of the datasets in your catalogue. The columns are `id`, `title`, `language`, `publisher`, `url`, `sha256` and `pages`.

`make documents` downloaded each file to `data/documents/<id>.pdf` and compared its SHA-256 hash with the list. Git ignores this folder. You can run the command again at any time: it keeps each complete file and downloads only the files that are missing or wrong. A publisher can remove or replace a file. Then the script reports the file, and the lab works with the files that you have. The checks need at least 90% of the files.

### Step 3. Parse with PyMuPDF

A PDF does not store text in reading order. It stores glyphs (the shapes of letters) at positions on the page. A parser must find the order again. Arabic makes this hard: the text runs from right to left, and the fonts join some letter pairs into one glyph (a ligature, for example lam + alef in لا). If the order of the words or of the letters is wrong, the chunk has words that no query matches, and the embedding of the chunk is noise.

1. Write `parse_pdf()` in `assistant/ingest.py` with [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/). It returns one string for each page.
2. Print the text of some pages of 5 Arabic PDFs. Open the same pages in a PDF viewer and compare them word by word.
3. If the words or the letters are out of order, try [Docling](https://docling-project.github.io/docling/) on the same files. Try it in a separate environment, for example `uv run --with docling python`, so that it does not become a package of the project. Keep the better parser. The checks test the text, not the parser.

```bash
uv run --group phase2 python -c "from pathlib import Path; from assistant.ingest import parse_pdf; print(parse_pdf(Path('data/documents/gastat-national-accounts-ar.pdf'))[6])"
```

This prints page 7 of `gastat-national-accounts-ar.pdf`, which the checks use.

<details>
<summary>Hint: what to look for</summary>

On page 7 of `gastat-national-accounts-ar.pdf`, look for the word الاستثمار. `page.get_text()` gives االستثمار: the two letters of the lam + alef glyph come out in the wrong order. `page.get_text(sort=True)` puts the words of each line in reverse order. Page 10 of `gastat-census-2022-ar.pdf` has more ligatures than lam + alef. On the build machine, Docling (version 2.150.0, without OCR and table structure) took 22.2 s for the 29 pages of `gastat-national-accounts-ar.pdf`, and it split one word on page 7 ("أ و" for "أو").
</details>

<details>
<summary>Hint: the characters and their positions</summary>

`page.get_text("rawdict")` gives each line as spans, and each span as a list of characters. Each character has its text (`c`) and its box (`bbox`). Look at the boxes of the characters of one ligature, and find what is different about them.

> From the documentation: the structure of `rawdict` is described in the PyMuPDF [Appendix 1](https://pymupdf.readthedocs.io/en/latest/app1.html).
</details>

### Step 4. Normalise, chunk and store

**Normalise.** Arabic writers can add diacritics (short vowel marks) or leave them out, and a tatweel (ـ) only makes a word longer on the page. So the same word can have several forms. Store one form, and use the same function on each query, so that a query and a chunk have the same form. `normalise_arabic()` removes the marks from U+064B to U+0652, U+0670 and the tatweel U+0640, and keeps all other text.

**Chunk.** A chunk is the unit that the search returns and the model reads. A fixed size keeps each chunk small enough for the model services, which cut each text at 2048 tokens. The overlap keeps a sentence at the border between two chunks complete in one of them. `chunk_text()` counts words from `str.split()`. Each chunk starts with the last `overlap` words of the chunk before it, and the last chunk holds at least one new word.

**Store.** Chunk each page separately, so that each chunk has one page number for its citation. Build the chunk ID from the document, the page and the position. Then the same file gives the same IDs each time, and your questions of week 5 stay valid when you ingest again. A second call of `ingest_document()` for the same document must leave the same rows.

1. Write `normalise_arabic()`, `chunk_text()` and `ingest_document()`.
2. Run the ingest of all documents:

```bash
make ingest
```

On the build machine, the ingest of the 100 files took less than 30 s and gave some thousands of chunks.

<details>
<summary>Hint: run it again safely</summary>

The table `chunks` has `ON DELETE CASCADE` on `document_id`. Think about what happens to the chunks of a document when you delete the document row, or when you insert it again with `ON CONFLICT`. Do all writes of one document in one transaction.
</details>

If you change `CHUNK_WORDS` or `OVERLAP_WORDS` later, the chunk IDs change. Then run `make ingest` and `make embed` again, and correct the expected IDs of your questions.

### Step 5. Check

```bash
make check WEEK=4
```

All 12 checks pass. Three of them read pages that were checked by eye in the PDF: page 7 of `gastat-national-accounts-ar.pdf`, page 10 of `gastat-census-2022-ar.pdf` and page 7 of `gastat-land-transport-en.pdf`. The plan check is that the parsed Arabic text reads in the correct order. So also read some pages of your own choice, with the command of step 3. Write the parser that you chose and the faults that you found in [RESULTS.md](RESULTS.md).

## Week 5: Embeddings and vector search

### Step 1. Read

The [pgvector README](https://github.com/pgvector/pgvector): Getting Started, Storing, Querying, HNSW and Filtering. The [BGE-M3](https://huggingface.co/BAAI/bge-m3) model card.

### Step 2. Embed the chunks and search by vector

An embedding model changes a text into a list of numbers, a vector. Texts with a similar meaning get vectors that are near each other. BGE-M3 is multilingual, so an Arabic question can find an English chunk. The vector search embeds the query and returns the chunks with the nearest vectors. The service returns vectors with a length of 1, so cosine distance is the measure to use.

An HNSW index finds the nearest vectors without a comparison to each row. It is approximate: it can miss a near vector. The index helps only a query that orders by the distance operator of the index, with a `LIMIT`.

> From the documentation: BGE-M3 gives vectors of 1024 numbers and reads inputs of up to 8192 tokens ([model card](https://huggingface.co/BAAI/bge-m3)). In pgvector 0.8.7, `<=>` is the cosine distance, an index for it is `USING hnsw (embedding vector_cosine_ops)`, HNSW can index a `vector` of up to 2,000 dimensions, and the default `hnsw.ef_search` is 40 ([README of v0.8.7](https://github.com/pgvector/pgvector/blob/v0.8.7/README.md)).

1. Write a migration file, for example `db/migrations/0003_chunk_embeddings.sql`. It creates the extension `vector`, adds a column of the type `vector(1024)` to `chunks`, and adds an HNSW index on it. Run `make up` to apply it.
2. Write `embed_chunks()`. It reads the chunks that have no vector, calls `embed()` from `assistant/embeddings.py` with some hundred chunks or less at a time, stores the vectors, and commits after each call. `embed()` is complete: it sends batches of 32 texts to the service.
3. Run it:

```bash
make embed
```

On the build machine, 4683 chunks took 44 minutes. You can stop the command and start it again. It continues with the chunks that have no vector.

4. Write `vector_search()` in `assistant/retrieval.py`. Normalise the query with `normalise_arabic()`, embed it, and return the `k` nearest chunks in the form of a search result. A higher score is a better result, so do not return the distance as the score.

<details>
<summary>Hint: send a vector to Postgres</summary>

The project has no pgvector package for Python. The README shows a vector as text, for example `'[1,2,3]'`. Send the vector as one text parameter, and cast it to `vector` in the SQL.
</details>

<details>
<summary>Hint: the score and the index</summary>

Order by the distance itself, for example `ORDER BY embedding <=> %s::vector LIMIT %s`. An `ORDER BY` on an expression of the distance, for example `1 - (embedding <=> v) DESC`, gives the same order, but the index cannot help it. Compute the score in the `SELECT` list.
</details>

Look at the plan of your query. On a table of some thousands of rows, Postgres can find a full read of the table cheaper than the index. On the build machine it chose a full read and a sort for the 4683 chunks, also with the HNSW index in place. To see if the query can use the index, turn the full read off in your session first:

```bash
docker compose exec db psql -U assistant
```

```sql
SET enable_seqscan = off;
EXPLAIN SELECT id FROM chunks ORDER BY embedding <=> (SELECT embedding FROM chunks LIMIT 1) LIMIT 5;
```

Use the name of your own vector column. The plan must show an index scan on your HNSW index. So at this table size, your recall numbers come from an exact search, not from the approximate index. With millions of chunks, the planner uses the index, and the recall can be a little lower.

### Step 3. The 50 retrieval questions

Write 50 questions in `evals/retrieval_questions.jsonl`, 25 in Arabic and 25 in English. Each line has `id`, `language` (`"ar"` or `"en"`), `question` and `expected_chunk_ids`: the IDs of the chunks that hold the answer. The file has two examples.

1. Ask Claude Code for a first draft. It uses your subscription and no API credit. Let it read chunks from the database with `docker compose exec db psql -U assistant`, and ask for questions in the words of a user, not in the words of the chunk.
2. Read each chunk and each question, and correct them by hand. A wrong expected ID makes a correct search fail. If the answer is in two chunks (for example in the overlap), list both IDs.
3. Use the real spread of the documents: many reports have the same structure, so a question such as "What is the base year?" fits many chunks. Name the subject in the question, as a user would.

A question is found when at least one of its expected IDs is in the top five results. The text of an Arabic question must have Arabic letters.

### Step 4. Check

Write `measure()` and `main()` in `evals/recall.py`. The docstring has the arguments and the form of the result file. The result file has `k`, `questions`, `recall[mode]["ar" | "en" | "all"]`, and `rows` with one item for each question and each mode. The checks compute the recall again from the rows.

```bash
make recall ARGS="--modes vector"
```

```bash
make check WEEK=5
```

All 12 checks pass, and the last one prints your recall in the top five for each language. Then open the notebook, which shows the table and the questions that the search misses:

```bash
make notebook
```

The notebook runs the 50 questions through the vector search, which takes less than a minute. For each miss, find the cause: the expected ID is wrong, the question uses other words than the document, or many chunks look the same. Write the recall and the causes in [RESULTS.md](RESULTS.md).

## Week 6: Hybrid search and re-ranking

### Step 1. Read

Huyen, chapter 6: Retrieval Optimization (pages 268 to 273). The [pgvector README](https://github.com/pgvector/pgvector): Hybrid Search.

### Step 2. Full-text search on the chunks

A vector search finds text with a similar meaning. It can miss an exact term, a code or a name. A keyword search finds the chunks that hold the words of the query. Postgres full-text search changes a text into lexemes (the base forms of the words) with a text search configuration. The configuration decides the word forms and the stop words, and it is different for each language.

1. List the configurations of your Postgres, and test the one for Arabic:

```bash
docker compose exec db psql -U assistant -c "\dF"
```

```bash
docker compose exec db psql -U assistant -c "SELECT plainto_tsquery('arabic', 'مُحَمَّدٌ الجـــدول إِحْصَاءَات')"
```

Read the result. What did the configuration change in each word? Try some sentences of your chunks with `to_tsvector('arabic', ...)` and `to_tsvector('english', ...)`.

2. Write a migration file, for example `db/migrations/0004_chunk_text_search.sql`. It adds a `tsvector` column to `chunks`, with the configuration of the language of each row, and a GIN index on it. Run `make up`.
3. Write `keyword_search()`. Use the same configuration for the query as for the column of that language. Order by a rank of the match.

> From the documentation: `plainto_tsquery` puts `&` (AND) between the words, and for `ts_rank_cd` the normalization flag 32 divides the rank by itself + 1 ([Controlling Text Search](https://www.postgresql.org/docs/17/textsearch-controls.html)).

A full question has words that no chunk holds. With AND between the words it finds nothing. The checks need a match on some of the words, as the search of Phase 1 did.

<details>
<summary>Hint: a column that keeps itself up to date</summary>

A generated column computes its value from other columns of the row, also for the rows that exist when you add it. A `CASE` on `language` can choose the configuration.
</details>

<details>
<summary>Hint: stop words in Arabic</summary>

In the Postgres 17 of the image, the `english` configuration removes English stop words. The `arabic` configuration has no stop-word file. So a word such as "في", which is in 1747 of the 2249 Arabic chunks of the build machine, stays in each Arabic query. Find out if this matters for your recall before you fix it.
</details>

### Step 3. Rank fusion and re-ranking

**Reciprocal rank fusion** (RRF) merges two ranked lists without a comparison of their scores. The scores of a vector search and a keyword search have different scales, but a rank is a rank. The score of a chunk is the sum of `1 / (k + rank)` over the lists that hold it, and the first rank is 1. The [paper of Cormack, Clarke and Buettcher (SIGIR 2009)](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) uses k = 60 and says that this value was fixed during a pilot investigation.

**Re-ranking.** The embedding model reads the query and each chunk separately. A cross-encoder such as [bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) reads the query and one chunk together, so it can judge if the chunk answers the query. This is better, but it is slow, because the model runs one time for each pair. So give it only the best candidates. On the build machine, the re-ranking of 20 chunks took about 20 s for each question. The vector search took 0.15 s and the hybrid search 0.19 s.

1. Write `reciprocal_rank_fusion()`.
2. Write `retrieve(query_text, mode, k)`, the one entry point for all callers:
   - `vector`: the vector search alone.
   - `hybrid`: the top 20 (`CANDIDATES`) of the vector search and the top 20 of the keyword search, merged with rank fusion. The score is the fused score.
   - `rerank`: the top 20 of the hybrid search, in the order of the scores of `rerank()` from `assistant/embeddings.py`. The score is the score of the model.
   - Any other mode raises a `ValueError`.

### Step 4. Check

```bash
make recall
```

This runs the 50 questions in the three modes, writes `evals/results/recall.json` and prints the table. On the build machine it took about 17 minutes, nearly all of it for the re-ranking.

```bash
make check WEEK=6
```

All 15 checks pass, and the last one prints your table. Then read the week 6 part of the notebook (`make notebook`). It shows the questions where the modes do not agree. Write the table in [RESULTS.md](RESULTS.md).

**Read your table before you change code.** The plan does not set a target, and your numbers depend on your parser, your chunks and your questions. Find the cause of each difference between the modes in the rows of the result file. For example, in the reference build of this lab, hybrid search had a lower recall than the vector search alone, mainly in Arabic. This was not a bug. Do not use it as the expected answer: measure your own numbers and explain them.

These questions help you find the cause when your hybrid search loses questions that the vector search finds:

- What is the recall of the keyword search alone, in the top 5 and in the top 20, for each language? Call `keyword_search()` in the notebook.
- For a lost question, at which rank does each list hold the expected chunk? Is it in the 20 keyword candidates at all?
- How many chunks are in both lists? Compare the lowest fused score of a chunk in both lists with the highest score of a chunk in one list.
- Which chunks took the places of the expected chunk? Are they other pages of the correct document?

<details>
<summary>Hint: what the reference build found</summary>

With k = 60 and 20 candidates in each list, a chunk in both lists has a score of at least 1/80 + 1/80 = 0.025. A chunk in one list has a score of at most 1/61 = 0.0164. So each chunk that both lists found comes before each chunk that only one list found. When the keyword search is weak, the chunks that it shares with the vector search are often other pages of the correct document: the subject words match, but the page with the answer is a different one. These chunks fill the top 5, and the expected chunk at vector rank 1 to 4 falls out. The keyword search alone was much weaker than the vector search, most of all in Arabic. A short list of Arabic stop words raised the recall of the keyword search, but the hybrid recall did not change, so the missing stop words were not the cause. The re-ranking model reads the 20 fused candidates, which still held the expected chunk, and put it back in the top 5.
</details>

## Week 7: Retrieval as a tool, with citations

### Step 1. Read

Huyen, chapter 6: RAG Beyond Texts (pages 273 to 275), for retrieval over tables.

### Step 2. The tool and the citations

The model now has two search tools: `search_datasets` finds a dataset in the catalogue, and `search_documents` finds a passage in the documents. The model chooses from the descriptions only. A citation lets the user check the answer: the title, the page and the chunk ID point to the passage that supports it.

1. In `assistant/tools.py`, add `search_documents` to `TOOLS`. Its input has a required `query` with a description. The tool description has at least 150 characters, and it says when to use this tool and not `search_datasets`, and what it returns.
2. In `run_tool()`, call `retrieve()` and return a JSON list of 1 to 10 objects with `chunk_id`, `title`, `page` and `text`. Keep the list short: each token of a tool result goes into the prompt of each later turn. Use the mode with the best recall in your table. With `rerank`, each call waits about 20 s on a CPU like the one of the build machine.
3. In `assistant/schemas.py`, add a field `citations` to `Answer`: a list of objects with `document_title`, `page` and `chunk_id`, each with a description. A citation without `chunk_id` is not valid. Give the field the default `[]`, so that an answer of Phase 1 without citations stays valid.
4. The new schema goes in `output_config.format.schema` of each request, as in Phase 1. Tell the model in the system prompt when to search the documents, and to cite each passage that it uses.

The tool definitions are in the cached part of each request. The new tool changes that part, so the first request after the change writes a new cache entry.

### Step 3. Reject a citation that the tool did not return

A model can write a chunk ID that looks correct but that no search returned. Then the citation points to a passage that the model did not read. Your loop knows each chunk ID that a tool returned in this conversation, so it can check each citation before the user sees the answer. This is why Phase 1 sent one `answer` event at the end: you cannot take back an answer that you already sent.

1. In `assistant/agent.py`, collect the chunk IDs of each tool result of `search_documents` in this conversation. Skip the results with `is_error`.
2. After you validate the final answer, compare its citations with these IDs. Compare with the tool results, not with the table `chunks`: a chunk that exists but that no search returned is also wrong.
3. If a citation is wrong, do not send the answer. Keep the rejected answer in the messages as an assistant turn, add a user message that names the wrong chunk IDs, and ask the model again.
4. Ask again one time only. If the second answer also has a wrong citation, yield an `error` event and no `answer` event. The stream still ends with `done`, and its `requests` counts the extra request.

<details>
<summary>Hint: where the IDs come from</summary>

You already build each tool result in the loop, from the output of `run_tool()`. Read the chunk IDs from that output at the same place, and keep them in a set for the whole conversation.
</details>

### Step 4. Check: the exit test

```bash
make check WEEK=7
```

All 11 checks pass. They take about 2 minutes on the build machine, because the tool does a real search with your services. Then run all checks of the phase, and the checks of Phase 1 again:

```bash
make check PHASE=2
```

```bash
make check PHASE=1
```

The 50 checks of Phase 2 and the 37 checks of Phase 1 pass.

The exit test of the plan is the recall of the 50 retrieval questions, in the top five, before and after hybrid search and re-ranking, for Arabic and English separately. Run `make recall` again with your final code, and write the table in [RESULTS.md](RESULTS.md) with the date.

Then run the live check. It sends the first two English and the first two Arabic questions of your file through the real loop, and checks that the answers cite chunks that a search returned:

```bash
make check-live WEEK=7
```

**Cost estimate:** about 12 requests to Claude Haiku 5.5 (4 questions, about 3 requests each). Assume about 5,000 input tokens for each request (the tools, the system prompt and up to 10 chunks of tool results) and about 1,000 output tokens (thinking included). Input: 12 x 5,000 = 60,000 tokens x $0.10 per million = $0.006. Output: 12 x 1,000 = 12,000 tokens x $0.50 per million = $0.006. Total: about $0.01. Cache reads make the input part smaller. This number is an estimate, not a measurement. The check also takes some minutes: each search with re-ranking takes about 20 s on the build machine, and the check runs each search of the model again to compare the citations.

Write the numbers that it prints in [RESULTS.md](RESULTS.md). When an answer cites other chunks than the expected ones, find the cause in the `tool` events: did the search return the expected chunk, and did the model use it?

## Commands

| Command | What it does |
| --- | --- |
| `make up` | Start Postgres, the API and the two model services, apply the migrations, load the catalogue |
| `make down` | Stop the services and keep the data |
| `make reset` | Stop the services and delete the database volume. The two model volumes stay, so the next `make up` does not download the models again |
| `make documents` | Download the documents of `data/documents.csv` and check each SHA-256 hash |
| `make ingest` | Parse, chunk and store the documents |
| `make embed` | Embed the chunks that have no vector |
| `make recall` | Measure the recall of the three modes. `ARGS="--modes vector"` for one mode. Other arguments: `--k`, `--questions`, `--out` |
| `make notebook` | Open `phases/phase-2-retrieval/notebooks/recall.ipynb` in JupyterLab |
| `make check WEEK=5` | Offline checks of one week |
| `make check PHASE=2` | Offline checks of the phase |
| `make check-live WEEK=7` | The live check of the phase |

To delete the models too (4.6 GB), run `make down`, then `docker volume rm assistant_embeddings-model assistant_reranker-model`.

| Setting in `.env` | Default | Meaning |
| --- | --- | --- |
| `TEI_TAG` | `cpu-arm64-1.9.4` | The image of the model server. Set `cpu-1.9.4` on an Intel or AMD machine |
| `EMBEDDINGS_PORT` | `8081` | Change it, and the port in `EMBEDDINGS_URL`, if 8081 is in use |
| `RERANKER_PORT` | `8082` | Change it, and the port in `RERANKER_URL`, if 8082 is in use |
| `EMBEDDINGS_URL` | `http://localhost:8081` | Where your code and the checks find the embedding service |
| `RERANKER_URL` | `http://localhost:8082` | Where your code and the checks find the re-ranking service |

The API container finds the two services by their names in Docker Compose, so these URLs are only for the code that runs on your machine. The services are reachable only from your machine (127.0.0.1).

> From the documentation: the TEI API has `POST /embed` (`inputs`, `normalize`, `truncate`), `POST /rerank` (`query`, `texts`, `truncate`) and `GET /health` ([openapi.json of TEI](https://huggingface.github.io/text-embeddings-inference/openapi.json)). The server accepts at most 32 texts in one request by default (`--max-client-batch-size`), and `--max-batch-tokens` limits the tokens of one batch ([TEI CLI arguments](https://huggingface.co/docs/text-embeddings-inference/cli_arguments)).
