---
name: example-file-inspector
description: "EXAMPLE skill: inspect a text file's basic stats (line count, size, extension) using only standard shell tools. Use when you want to see a skill that performs a small, self-contained, side-effect-free task."
---

# Example: File Inspector

Another **dummy/example skill** — no personal information, no secrets, no
private infrastructure. Demonstrates a skill that actually does a small
task using ordinary shell tools, rather than just being static prose.

## Procedure

Given a file path from the user:

1. Confirm the file exists (`test -f "$PATH"`); if not, say so and stop.
2. Report:
   - Line count: `wc -l "$PATH"`
   - Byte size: `wc -c "$PATH"`
   - Extension (if any): everything after the last `.` in the filename
   - File type guess: `file "$PATH"` if available, otherwise infer from
     extension
3. Present the four facts as a short list. Do not speculate about file
   contents beyond what these commands report.

## Why this is a good "second skill" to read

It shows the two things every real skill needs beyond
`example-hello-world`: a numbered **procedure** the agent can follow
mechanically, and an explicit **boundary** ("do not speculate beyond what
these commands report") that keeps the skill's output trustworthy.
