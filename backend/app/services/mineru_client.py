"""
MinerU PDF extraction client.

Wraps the ``mineru`` CLI tool to extract text, images, and tables from
PDF documents.  Output is organised per task under a configurable base
directory.
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


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
        device: str = "cuda",
    ) -> Optional[Dict[str, Any]]:
        """
        Run MinerU on a PDF and return the parsed result.

        Args:
            pdf_path: Path to the source PDF file.
            task_id: Task identifier (isolates the output directory).
            backend: MinerU backend engine (default ``"pipeline"``).
            device: Compute device (``"cuda"`` or ``"cpu"``).

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

            # 3. Build the CLI command
            cmd = [
                "mineru",
                "-p", pdf_path,
                "-o", str(task_output_dir),
                "-b", backend,
                "-d", device,
            ]

            logger.info(f"Invoking MinerU on: {pdf_path}")
            logger.info(f"Command: {' '.join(cmd)}")

            # 4. Execute
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )

            if proc.returncode != 0:
                logger.error(f"MinerU exited with code {proc.returncode}")
                logger.error(f"stderr: {proc.stderr}")
                return None

            logger.info("MinerU parsing finished")
            logger.debug(f"stdout: {proc.stdout}")

            # 5. Locate the output directory
            #    Layout: <task_output_dir>/<pdf_stem>/<backend_alias>/
            pdf_name = pdf_file.stem
            pdf_output_dir = task_output_dir / pdf_name

            if not pdf_output_dir.exists():
                logger.error(f"Expected output directory missing: {pdf_output_dir}")
                return None

            # MinerU may remap the backend name (e.g. pipeline → auto),
            # so we scan for the actual sub-directory.
            backend_dirs = [d for d in pdf_output_dir.iterdir() if d.is_dir()]
            if not backend_dirs:
                logger.error(f"No backend output directory found under: {pdf_output_dir}")
                return None

            content_dir = backend_dirs[0]  # typically only one
            logger.info(f"MinerU output directory: {content_dir}")

            # 6. Load the content list
            content_list_path = content_dir / f"{pdf_name}_content_list.json"
            if not content_list_path.exists():
                logger.error(f"Content list not found: {content_list_path}")
                return None

            with open(content_list_path, "r", encoding="utf-8") as fh:
                content_list = json.load(fh)

            logger.info(f"Loaded content list with {len(content_list)} items")

            # 7. Build result
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
