"""
summarize.py — Generate structured notes from transcript using Claude or a local OpenAI-compatible API.

Usage:
    python summarize.py <session-output-dir>

Reads transcript.txt and metadata.json; writes notes.md.

Backend selection (checked in order):
  1. LOCAL_OPENAI_API is set → use that OpenAI-compatible endpoint (LOCAL_OPENAI_MODEL)
  2. Otherwise → use Anthropic Claude (ANTHROPIC_API_KEY required)
"""

import argparse
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ANTHROPIC_MODEL = "claude-opus-4-6"

SYSTEM_PROMPT = """You are an expert ML researcher creating structured notes from NeurIPS conference sessions.
Your notes should be precise, technical, and useful for a researcher who wants to understand the key contributions
without watching the full session. Use LaTeX notation for math where appropriate."""

NOTES_PROMPT_TEMPLATE = """Please create structured notes for the following NeurIPS session.

**Session Title:** {title}
**Session URL:** {url}
**Slide Count:** {slide_count}

**Transcript:**
{transcript}

---

Generate comprehensive notes in Markdown with the following sections:

## Abstract
(2-3 sentence summary of what the paper/talk is about)

## Problem Statement
(What problem does this work address? Why is it hard/important?)

## Key Contributions
(Bulleted list of the main technical contributions)

## Method / Approach
(Detailed description of the proposed method, with any key equations or algorithms)

## Experimental Results
(What datasets, baselines, and metrics? What are the main results?)

## Limitations & Future Work
(Acknowledged limitations and open questions)

## Questions Raised
(Interesting questions or critiques that arise from this work)

## Key Terms
(Brief glossary of important technical terms introduced or used)
"""


def generate_notes(output_dir: Path) -> str:
    """Generate structured notes from transcript and metadata using Claude."""
    transcript_path = output_dir / "transcript.txt"
    notes_path = output_dir / "notes.md"
    metadata_path = output_dir / "metadata.json"

    if notes_path.exists():
        print(f"  notes.md already exists, skipping.")
        return notes_path.read_text()

    if not transcript_path.exists():
        raise FileNotFoundError(f"No transcript.txt found in {output_dir}")

    transcript = transcript_path.read_text()

    # Load metadata if available
    title = output_dir.name
    url = ""
    slide_count = "unknown"
    if metadata_path.exists():
        import json
        metadata = json.loads(metadata_path.read_text())
        title = metadata.get("title", title)
        url = metadata.get("url", "")
        slide_count = str(metadata.get("slide_count", "unknown"))

    prompt = NOTES_PROMPT_TEMPLATE.format(
        title=title,
        url=url,
        slide_count=slide_count,
        transcript=transcript,
    )

    local_api = os.environ.get("LOCAL_OPENAI_API")
    notes_text = ""

    if local_api:
        from openai import OpenAI

        local_model = os.environ.get("LOCAL_OPENAI_MODEL", "openai/gpt-oss-20b")
        client = OpenAI(base_url=local_api, api_key="local")

        print(f"Generating notes with {local_model} via {local_api} (streaming)...")
        stream = client.chat.completions.create(
            model=local_model,
            max_tokens=8192,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            stream=True,
        )
        for chunk in stream:
            text = chunk.choices[0].delta.content or ""
            print(text, end="", flush=True)
            notes_text += text
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "Set ANTHROPIC_API_KEY for Claude, or LOCAL_OPENAI_API for a local model."
            )

        client = anthropic.Anthropic(api_key=api_key)

        print(f"Generating notes with {ANTHROPIC_MODEL} (streaming)...")
        with client.messages.stream(
            model=ANTHROPIC_MODEL,
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                notes_text += text

    print()  # newline after streaming output
    if not notes_text.strip():
        raise RuntimeError("Generation returned empty output — notes.md not written.")
    notes_path.write_text(notes_text)
    print(f"  Notes saved to notes.md ({len(notes_text)} characters).")
    return notes_text


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Generate session notes with Claude.")
    parser.add_argument("output_dir", help="Session output directory")
    args = parser.parse_args()

    generate_notes(Path(args.output_dir))


if __name__ == "__main__":
    main()
