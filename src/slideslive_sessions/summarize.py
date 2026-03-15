"""
summarize.py — Generate structured notes from transcript using any litellm-supported LLM.

Usage:
    slideslive-summarize <session-output-dir> [--force]

Reads transcript.txt and metadata.json; writes notes.md.

Model selection via env vars:
  NOTES_MODEL    — litellm model string (default: anthropic/claude-opus-4-6)
  NOTES_API_BASE — optional custom API base URL (e.g. for Ollama or local endpoints)
"""

import argparse
import os
from pathlib import Path

import litellm
from dotenv import load_dotenv

DEFAULT_NOTES_MODEL = "anthropic/claude-opus-4-6"

SYSTEM_PROMPT = """You are an expert ML researcher creating structured notes from NeurIPS conference sessions.

Your notes should be precise, technical, and useful for a researcher who wants to understand the key contributions, mechanisms, assumptions, and limitations without watching the full session.

Your job is to reconstruct the talk the way a careful reader would understand it from the slides, not to produce a chronological recap of the raw speech.

Guidelines:
1. Identify the speaker's central thesis, question, or research program.
2. Recover the major conceptual sections of the talk in the order the ideas are developed.
3. For each section, capture:
   - the main claim,
   - the mechanism, model, derivation, or argument used to support it,
   - the significance of the result,
   - and any important assumptions, simplifying conditions, or caveats.
4. Preserve the progression from simpler ideas or surrogate models to more complex ones when that progression is part of the talk's logic.
5. Distinguish clearly between:
   - core results or claims,
   - illustrative examples or intuitions,
   - assumptions or approximations,
   - and open questions, limitations, or future directions.
6. Ignore greetings, applause, housekeeping, repeated filler, and audience Q&A unless a question reveals a major limitation, clarification, or future direction.
7. Do not invent content that is not supported by the transcript.
8. Prefer precise technical language over generic prose.
9. Use LaTeX notation for math where appropriate.
10. Be comprehensive about important concepts; do not omit substantive ideas merely to keep the notes short.

When the talk introduces a sequence of models, abstractions, or theoretical reductions, preserve that structure explicitly in the notes."""

NOTES_PROMPT_TEMPLATE = """Please create structured notes for the following NeurIPS session.

Session metadata:
- Session Title: {title}
- Session URL: {url}
- Slide Count: {slide_count}

Transcript:
{transcript}

Instructions for this session:
- Use the transcript to recover the conceptual organization of the talk as it would be understood from the slides.
- Focus on the technical ideas, theoretical framing, mechanisms, and conclusions.
- Preserve the order in which the key ideas are developed.
- Capture the important concepts completely, even if the notes become long.
- Do not produce a raw chronological recap of the spoken transcript.

Output format:
1. Title
2. Executive Summary
   - 1 to 3 paragraphs summarizing the overall thesis and contribution of the talk
3. Main Argument
   - a concise statement of the central question, thesis, or research agenda
4. Structured Notes by Section
   - organize the talk into major conceptual sections
   - for each section include:
     - Section Heading
     - Main Claim
     - Technical Content
     - Why It Matters
     - Assumptions / Caveats (if any)
5. Key Technical Insights
   - bullet list of the most important results, mechanisms, reductions, or interpretations
6. Assumptions, Limitations, and Open Questions
7. One-Sentence Essence

Important:
- Ground everything in the transcript.
- Ignore filler and logistics.
- Include mathematical notation when it clarifies the content.
- Prefer faithful technical reconstruction over brevity.
"""


def generate_notes(output_dir: Path, force: bool = False) -> str:
    """Generate structured notes from transcript and metadata using litellm."""
    transcript_path = output_dir / "transcript.txt"
    notes_path = output_dir / "notes.md"
    metadata_path = output_dir / "metadata.json"

    if notes_path.exists():
        if not force:
            print(f"  notes.md already exists, skipping.")
            return notes_path.read_text()
        notes_path.unlink()

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

    notes_model = os.environ.get("NOTES_MODEL", DEFAULT_NOTES_MODEL)
    notes_api_base = os.environ.get("NOTES_API_BASE")
    notes_text = ""

    kwargs = {
        "model": notes_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "max_tokens": 8192,
    }
    if notes_api_base:
        kwargs["api_base"] = notes_api_base

    print(f"Generating notes with {notes_model} (streaming)...")
    for chunk in litellm.completion(**kwargs):
        text = chunk.choices[0].delta.content or ""
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

    parser = argparse.ArgumentParser(description="Generate session notes using any litellm-supported model.")
    parser.add_argument("output_dir", help="Session output directory")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate notes even if notes.md already exists",
    )
    args = parser.parse_args()

    generate_notes(Path(args.output_dir), force=args.force)


if __name__ == "__main__":
    main()
