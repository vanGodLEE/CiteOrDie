"""
Async MinerU CLI runner with progress reporting.

Executes the ``mineru`` command as an async subprocess, streams its
stdout/stderr, estimates progress from log output, and reads the
resulting content-list JSON.

.. warning::
   This module is currently **dead code** — no external callers exist.
   It also depends on ``ContentBlock``, ``TOCItem``, ``ParsedDocument``
   and ``PDFParserService`` which are **not defined** in the codebase.
   See the FIXME markers below.
"""

import asyncio
import json
from pathlib import Path
from typing import Callable, Optional

from loguru import logger

# FIXME: ContentBlock, TOCItem, ParsedDocument do not exist in schema.py.
# They were presumably removed in an earlier refactoring.  This import
# will raise ImportError at runtime.
from app.domain.schema import ContentBlock, TOCItem, ParsedDocument  # noqa: F401
from app.domain.settings import settings  # noqa: F401


class AsyncMinerURunner:
    """
    Async wrapper around the ``mineru`` CLI.

    Launches MinerU as a subprocess via :mod:`asyncio`, monitors its
    output to estimate progress, and returns a ``ParsedDocument``.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def parse_pdf_with_progress(
        self,
        pdf_path: str,
        output_dir: Path,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> "ParsedDocument":
        """
        Parse a PDF asynchronously with optional progress reporting.

        Args:
            pdf_path: Path to the source PDF.
            output_dir: Directory for MinerU output artefacts.
            progress_callback: ``callback(progress, message)`` called as
                               parsing progresses.

        Returns:
            A ``ParsedDocument`` instance.

        Raises:
            RuntimeError: If MinerU exits with a non-zero code or times out.
        """
        try:
            command = ["mineru", "-p", pdf_path, "-o", str(output_dir)]
            logger.info(f"Executing: {' '.join(command)}")

            if progress_callback:
                progress_callback(10, "Starting MinerU…")

            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_lines: list[str] = []
            stderr_lines: list[str] = []

            async def _read_stream(
                stream: asyncio.StreamReader,
                lines: list[str],
                *,
                is_stderr: bool = False,
            ) -> None:
                while True:
                    raw = await stream.readline()
                    if not raw:
                        break
                    decoded = raw.decode("utf-8", errors="ignore").strip()
                    lines.append(decoded)

                    if progress_callback and not is_stderr:
                        progress = self._estimate_progress(decoded)
                        if progress > 0:
                            progress_callback(progress, decoded[:100])

                    logger.debug(f"MinerU: {decoded}")

            await asyncio.gather(
                _read_stream(process.stdout, stdout_lines, is_stderr=False),
                _read_stream(process.stderr, stderr_lines, is_stderr=True),
            )

            returncode = await process.wait()

            if returncode != 0:
                tail = "\n".join(stderr_lines[-10:])
                logger.error(f"MinerU exited with code {returncode}")
                logger.error(f"stderr (last 10 lines): {tail}")
                raise RuntimeError(f"MinerU failed: {tail}")

            if progress_callback:
                progress_callback(50, "MinerU finished, reading output…")

            result = await self._read_mineru_output(pdf_path, output_dir)

            if progress_callback:
                progress_callback(60, "Output loaded")

            return result

        except asyncio.TimeoutError:
            logger.error("MinerU timed out")
            raise RuntimeError("PDF parsing timed out (>30 min)")
        except Exception as e:
            logger.error(f"Async PDF parsing failed: {e}")
            raise

    # ------------------------------------------------------------------
    # Progress estimation
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_progress(line: str) -> float:
        """
        Estimate overall progress from a single MinerU log line.

        Mapping (approximate):
        - Layout Predict  → 15–20 %
        - MFD Predict     → 25–30 %
        - MFR Predict     → 35–40 %
        - Table OCR       → 43 %
        - OCR Predict     → 48–50 %
        """
        low = line.lower()

        if "layout predict" in low:
            return 20 if "100%" in line else 15
        if "mfd predict" in low:
            return 30 if "100%" in line else 25
        if "mfr predict" in low:
            return 40 if "100%" in line else 35
        if "table" in low and "ocr" in low:
            return 43
        if "ocr" in low and "predict" in low:
            return 50 if "100%" in line else 48

        return 0

    # ------------------------------------------------------------------
    # Output reader
    # ------------------------------------------------------------------

    async def _read_mineru_output(
        self,
        pdf_path: str,
        output_dir: Path,
    ) -> "ParsedDocument":
        """
        Read MinerU's output artefacts and assemble a ``ParsedDocument``.

        Raises:
            FileNotFoundError: If the expected output files are missing.
        """
        # FIXME: PDFParserService does not exist in the codebase.  This
        # lazy import will raise ImportError at runtime.
        from app.services.pdf_parser import PDFParserService

        pdf_name = Path(pdf_path).stem

        # MinerU output layout: <output_dir>/<pdf_name>/auto/*_content_list.json
        auto_dir = output_dir / pdf_name / "auto"
        logger.info(f"Expected output directory: {auto_dir}")

        if not auto_dir.exists():
            logger.warning("Output directory missing – searching recursively…")
            content_list_files = list(output_dir.rglob("*_content_list.json"))
            if not content_list_files:
                raise FileNotFoundError(
                    f"MinerU output not found.\n"
                    f"Expected path: {auto_dir}\n"
                    f"Verify that MinerU executed successfully."
                )
            content_list_path = content_list_files[0]
            logger.info(f"Found content list: {content_list_path}")
        else:
            content_list_files = list(auto_dir.glob("*_content_list.json"))
            if not content_list_files:
                raise FileNotFoundError(
                    f"No content_list.json in output directory.\n"
                    f"Directory: {auto_dir}\n"
                    f"Contents: {list(auto_dir.glob('*'))}"
                )
            content_list_path = content_list_files[0]
            logger.info(f"Found content list: {content_list_path}")

        with open(content_list_path, "r", encoding="utf-8") as fh:
            content_list_raw = json.load(fh)

        content_blocks = [ContentBlock(**block) for block in content_list_raw]

        # Read companion markdown (if present)
        md_path = content_list_path.parent / f"{pdf_name}.md"
        markdown = ""
        if md_path.exists():
            with open(md_path, "r", encoding="utf-8") as fh:
                markdown = fh.read()

        # Extract table of contents
        parser = PDFParserService()
        toc = parser.extract_toc(content_blocks)

        logger.info(
            f"MinerU output loaded: {len(content_blocks)} blocks, "
            f"{len(toc)} TOC entries"
        )

        return ParsedDocument(
            content_list=content_blocks,
            markdown=markdown,
            toc=toc,
        )


# Backward-compatible alias
AsyncPDFParser = AsyncMinerURunner
