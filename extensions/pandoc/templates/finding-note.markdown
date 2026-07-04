---
id: "$id$"
kind: finding
topic: "$topic$"
status: "$status$"
verification_status: "$verification_status$"
source_status: "$source_status$"
source_topic_file: "$source_topic_file$"
source_heading: "$source_heading$"
source_index: $source_index$
input_sha256: "$input_sha256$"
last_pipeline_run: "$last_pipeline_run$"
updated: "$updated$"
tags:
$for(tags)$
  - "$tags$"
$endfor$
---

# $title$

## Original note

$body$

## Pipeline drafts

<!-- Append generated drafts here. Do not overwrite Original note. -->

## Accepted version

<!-- Human-owned final/current version for topic transclusion. -->
