"""
MinerU PDF extraction client.

Wraps the ``mineru`` CLI tool to extract text, images, and tables from
PDF documents.  Output is organised per task under a configurable base
directory.

Uses ``subprocess.Popen`` for streaming stderr in real-time so that
MinerU's progress (batch info, model loading) can be reported to the
task tracker during long-running parses.
"""

import json
import re
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


def _detect_device() -> str:
    """Auto-detect the best compute device for MinerU.

    Returns ``"cuda"`` when a CUDA-capable PyTorch is installed **and**
    at least one GPU is visible; otherwise ``"cpu"``.
    """
    try:
        import torch
        if torch.cuda.is_available():
            logger.info("CUDA available – MinerU will use GPU")
            return "cuda"
    except Exception:
        pass
    logger.info("CUDA not available – MinerU will use CPU")
    return "cpu"


# ---------------------------------------------------------------------------
# Stderr streaming helper
# ---------------------------------------------------------------------------

_BATCH_RE = re.compile(r"Batch\s+(\d+)/(\d+):\s+(\d+)\s+pages/(\d+)\s+pages")
_PROGRESS_RE = re.compile(r"(\d+)%\|")


def _stream_stderr(
    pipe,
    collected: list,
    on_progress: Optional[Callable[[str], None]] = None,
) -> None:
    """Read *pipe* line-by-line, collecting output and emitting progress.

    Runs in a daemon thread so that the main thread can wait on
    ``proc.wait()`` without deadlock.
    """
    try:
        for raw_line in pipe:
            line = raw_line.rstrip("\n\r")
            collected.append(line)

            # Relay meaningful lines to the progress callback
            if on_progress and line.strip():
                # Detect MinerU batch info: "Batch 1/1: 21 pages/21 pages"
                m = _BATCH_RE.search(line)
                if m:
                    on_progress(f"MinerU processing batch {m.group(1)}/{m.group(2)} ({m.group(3)} pages)")
                    continue

                # Detect model loading
                if "DocAnalysis init" in line:
                    on_progress("MinerU loading analysis model...")
                    continue

                # Detect progress bar percentage
                m = _PROGRESS_RE.search(line)
                if m:
                    on_progress(f"MinerU progress: {m.group(1)}%")
                    continue
    except Exception:
        pass  # pipe closed


class MinerUClient:
    """Client that invokes the MinerU CLI and collects its output."""

    def __init__(self, output_base_dir: str = "mineru_output") -> None:
        """
        Args:
            output_base_dir: Root directory for MinerU output artefacts.
        """
        self.output_base_dir = Path(output_base_dir)
        self.output_base_dir.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Core parsing
    # ------------------------------------------------------------------

    def parse_pdf(
        self,
        pdf_path: str,
        task_id: str,
        backend: str = "pipeline",
        device: str = "auto",
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Run MinerU on a PDF and return the parsed result.

        Args:
            pdf_path: Path to the source PDF file.
            task_id: Task identifier (isolates the output directory).
            backend: MinerU backend engine (default ``"pipeline"``).
            device: Compute device. ``"auto"`` (default) detects CUDA
                availability; also accepts ``"cuda"`` or ``"cpu"``.
            on_progress: Optional callback ``(message: str) -> None``
                invoked with human-readable progress strings as MinerU
                runs (e.g. batch info, model loading).

        Returns:
            A dict containing ``content_list``, ``output_dir``,
            ``images_dir``, ``md_path``, ``pdf_name``, ``total_items``,
            and ``type_counts``; or ``None`` on failure.
        """
        try:
            # 1. Validate input
            pdf_file = Path(pdf_path)
            if not pdf_file.exists():
                logger.error(f"PDF file not found: {pdf_path}")
                return None

            # 2. Prepare task-specific output directory
            task_output_dir = self.output_base_dir / task_id
            task_output_dir.mkdir(exist_ok=True)

            # 3. Resolve device
            if device == "auto":
                device = _detect_device()

            # 4. Build the CLI command
            cmd = [
                "mineru",
                "-p", pdf_path,
                "-o", str(task_output_dir),
                "-b", backend,
                "-d", device,
            ]

            logger.info(f"Invoking MinerU on: {pdf_path}")
            logger.info(f"Command: {' '.join(cmd)}")
            if on_progress:
                on_progress("MinerU subprocess starting...")

            # 5. Execute with streaming stderr
            stderr_lines: list = []
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )

            # Stream stderr in a background thread to avoid deadlock and
            # to relay real-time progress to the task tracker.
            stderr_thread = threading.Thread(
                target=_stream_stderr,
                args=(proc.stderr, stderr_lines, on_progress),
                daemon=True,
            )
            stderr_thread.start()

            # Read stdout (usually empty for MinerU)
            stdout_data = proc.stdout.read() if proc.stdout else ""

            # Wait for process to finish
            returncode = proc.wait()
            stderr_thread.join(timeout=5)

            stderr_text = "\n".join(stderr_lines)

            # Always log stderr tail
            if stderr_text:
                logger.debug(f"MinerU stderr (tail): {stderr_text[-2000:]}")

            if returncode != 0:
                logger.error(f"MinerU exited with code {returncode}")
                return None

            # Check for known fatal errors in stderr even when rc == 0
            if stderr_text and ("Error" in stderr_text or "AssertionError" in stderr_text):
                logger.error(
                    f"MinerU reported errors despite exit code 0: "
                    f"{stderr_text[-500:]}"
                )
                return None

            logger.info("MinerU parsing finished")
            if stdout_data:
                logger.debug(f"stdout: {stdout_data}")

            # 6. Locate the output directory
            pdf_name = pdf_file.stem
            pdf_output_dir = task_output_dir / pdf_name

            if not pdf_output_dir.exists():
                logger.warning(
                    f"Expected output dir not found: {pdf_output_dir}. "
                    "Scanning for alternatives..."
                )
                candidate_dirs = [
                    d for d in task_output_dir.iterdir() if d.is_dir()
                ]
                if len(candidate_dirs) == 1:
                    pdf_output_dir = candidate_dirs[0]
                    logger.info(f"Using alternative output dir: {pdf_output_dir}")
                elif len(candidate_dirs) > 1:
                    from difflib import SequenceMatcher
                    pdf_output_dir = max(
                        candidate_dirs,
                        key=lambda d: SequenceMatcher(
                            None, d.name, pdf_name
                        ).ratio(),
                    )
                    logger.info(f"Best match output dir: {pdf_output_dir}")
                else:
                    logger.error(
                        f"No output directories found under: {task_output_dir}"
                    )
                    return None

            # MinerU may remap backend name; scan for the actual sub-dir.
            backend_dirs = [d for d in pdf_output_dir.iterdir() if d.is_dir()]
            if not backend_dirs:
                logger.error(f"No backend output directory found under: {pdf_output_dir}")
                return None

            content_dir = backend_dirs[0]
            logger.info(f"MinerU output directory: {content_dir}")

            # 7. Load the content list
            content_list_path = content_dir / f"{pdf_name}_content_list.json"
            if not content_list_path.exists():
                candidates = list(content_dir.glob("*_content_list.json"))
                if candidates:
                    content_list_path = candidates[0]
                    logger.info(f"Content list found via glob: {content_list_path}")
                else:
                    logger.error(f"Content list not found: {content_list_path}")
                    return None

            with open(content_list_path, "r", encoding="utf-8") as fh:
                content_list = json.load(fh)

            logger.info(f"Loaded content list with {len(content_list)} items")

            # 8. Build result
            type_counts = self._count_content_types(content_list)
            logger.info(f"Content type counts: {type_counts}")

            return {
                "content_list": content_list,
                "output_dir": str(content_dir),
                "images_dir": str(content_dir / "images"),
                "md_path": str(content_dir / f"{pdf_name}.md"),
                "pdf_name": pdf_name,
                "total_items": len(content_list),
                "type_counts": type_counts,
            }

        except Exception as e:
            logger.error(f"MinerU parsing failed: {e}")
            logger.exception(e)
            return None

    # ------------------------------------------------------------------
    # Content helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _count_content_types(content_list: List[Dict]) -> Dict[str, int]:
        """Count items in *content_list* grouped by ``type``."""
        counts: Dict[str, int] = {
            "text": 0,
            "list": 0,
            "image": 0,
            "table": 0,
            "other": 0,
        }
        for item in content_list:
            item_type = item.get("type", "other")
            if item_type in counts:
                counts[item_type] += 1
            else:
                counts["other"] += 1
        return counts

    @staticmethod
    def get_content_by_page(
        content_list: List[Dict],
        page_idx: int,
    ) -> List[Dict]:
        """
        Return all content items on *page_idx* (0-based).

        Args:
            content_list: MinerU content list.
            page_idx: Zero-based page index.
        """
        return [item for item in content_list if item.get("page_idx") == page_idx]

    @staticmethod
    def get_content_range(
        content_list: List[Dict],
        start_page: int,
        end_page: int,
    ) -> List[Dict]:
        """
        Return content items within a page range (inclusive, 0-based).

        Args:
            content_list: MinerU content list.
            start_page: First page index.
            end_page: Last page index (inclusive).
        """
        return [
            item
            for item in content_list
            if start_page <= item.get("page_idx", -1) <= end_page
        ]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_mineru_client_instance: Optional[MinerUClient] = None


def get_mineru_client() -> MinerUClient:
    """Return the module-level ``MinerUClient`` singleton."""
    global _mineru_client_instance
    if _mineru_client_instance is None:
        _mineru_client_instance = MinerUClient()
    return _mineru_client_instance


# Backward-compatible aliases
MinerUService = MinerUClient
get_mineru_service = get_mineru_client
