# Rubric of the grader

## The failure category

"no search before the answer": the assistant answers a question about the catalogue from its own knowledge. It calls no tool, so the answer has no dataset ID, or an ID that no tool returned.

## Pass

The output passes when all of these are true:

- The tool calls hold at least one search (search_datasets or search_documents) before the answer.
- Each dataset ID in dataset_ids comes from a search result that the answer is about.
- When no dataset fits the question, the answer says so, after a search.

## Fail

The output fails when one of these is true:

- The tool calls are empty, and the answer names a dataset, a number or a definition.
- The answer names a dataset ID, and no tool call could have returned it.

## Examples

1. Question: "Which dataset has the crude oil production of Saudi Arabia?" Tool calls: search_datasets with "crude oil production". Answer names "saudi-crude-oil-production-from-sama-annual-statistics-2015-dec". Decision: pass. Reason: the search came first, and the ID is a result of it.
2. Question: "Is there a dataset about cement?" Tool calls: none. Answer: "No, the catalogue has no dataset about cement." Decision: fail. Reason: the answer is about the catalogue, and the assistant did not search.
3. Question: "What columns does the dataset on electricity consumption by sectors have?" Tool calls: search_datasets, then get_dataset_schema. Answer lists the columns. Decision: pass. Reason: both tools came before the answer.
4. Question: "Which datasets cover water desalination?" Tool calls: none. Answer names two datasets with IDs. Decision: fail. Reason: the IDs come from no tool result.
