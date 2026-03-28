"""
Core AWS Textract client wrapper.
"""

from __future__ import annotations

import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from textractprettyprinter.t_pretty_print import (
    get_string,
    Pretty_Print_Table_Format,
    Textract_Pretty_Print,
)


class TextractClient:
    def __init__(self, region: str = "us-east-1", **kwargs):
        self._client = boto3.client("textract", region_name=region, **kwargs)

    def detect_text(self, *, file_path: str | None = None, s3_bucket: str | None = None, s3_key: str | None = None) -> list[dict]:
        doc = self._build_document(file_path=file_path, s3_bucket=s3_bucket, s3_key=s3_key)
        response = self._client.detect_document_text(Document=doc)
        return [b for b in response["Blocks"] if b["BlockType"] in ("LINE", "WORD")]

    def extract_text(self, *, file_path: str | None = None, s3_bucket: str | None = None, s3_key: str | None = None) -> str:
        blocks = self.detect_text(file_path=file_path, s3_bucket=s3_bucket, s3_key=s3_key)
        lines = [b["Text"] for b in blocks if b["BlockType"] == "LINE"]
        return "\n".join(lines)

    def export_markdown(self, *, file_path: str | None = None, s3_bucket: str | None = None, s3_key: str | None = None, feature_types: list[str] | None = None) -> str:
        """Extract text, tables, and key-value forms from a document and return clean Markdown.

        Uses Textract AnalyzeDocument for rich structural extraction (tables + forms).
        Content is interleaved in document reading order (top-to-bottom).
        Falls back to plain text detection if analysis fails.
        """
        if feature_types is None:
            feature_types = ["TABLES", "FORMS"]
        doc = self._build_document(file_path=file_path, s3_bucket=s3_bucket, s3_key=s3_key)
        try:
            response = self._client.analyze_document(Document=doc, FeatureTypes=feature_types)
        except (ClientError, Exception):
            # Fallback: plain text extraction for unsupported formats
            return self.extract_text(file_path=file_path, s3_bucket=s3_bucket, s3_key=s3_key)
        return _blocks_to_markdown(response["Blocks"])

    def analyze_document(self, *, file_path: str | None = None, s3_bucket: str | None = None, s3_key: str | None = None, feature_types: list[str] | None = None) -> dict:
        if feature_types is None:
            feature_types = ["TABLES", "FORMS"]
        doc = self._build_document(file_path=file_path, s3_bucket=s3_bucket, s3_key=s3_key)
        response = self._client.analyze_document(Document=doc, FeatureTypes=feature_types)
        blocks = response["Blocks"]
        result: dict = {"blocks": blocks, "tables": [], "forms": []}
        if "TABLES" in feature_types:
            result["tables"] = _extract_tables(blocks)
        if "FORMS" in feature_types:
            result["forms"] = _extract_forms(blocks)
        return result

    def start_text_detection(self, s3_bucket: str, s3_key: str, *, sns_topic_arn: str | None = None, sns_role_arn: str | None = None) -> str:
        params: dict = {"DocumentLocation": {"S3Object": {"Bucket": s3_bucket, "Name": s3_key}}}
        if sns_topic_arn and sns_role_arn:
            params["NotificationChannel"] = {"SNSTopicArn": sns_topic_arn, "RoleArn": sns_role_arn}
        response = self._client.start_document_text_detection(**params)
        return response["JobId"]

    def get_text_detection_results(self, job_id: str, *, poll_interval: float = 5.0, timeout: float = 300.0) -> list[dict]:
        deadline = time.monotonic() + timeout
        while True:
            response = self._client.get_document_text_detection(JobId=job_id)
            status = response["JobStatus"]
            if status == "SUCCEEDED":
                return self._paginate_async_results("get_document_text_detection", job_id, response)
            if status == "FAILED":
                raise RuntimeError(f"Textract job {job_id} failed: {response.get('StatusMessage', 'unknown error')}")
            if time.monotonic() > deadline:
                raise TimeoutError(f"Textract job {job_id} did not complete within {timeout}s")
            time.sleep(poll_interval)

    def start_document_analysis(self, s3_bucket: str, s3_key: str, *, feature_types: list[str] | None = None, sns_topic_arn: str | None = None, sns_role_arn: str | None = None) -> str:
        if feature_types is None:
            feature_types = ["TABLES", "FORMS"]
        params: dict = {"DocumentLocation": {"S3Object": {"Bucket": s3_bucket, "Name": s3_key}}, "FeatureTypes": feature_types}
        if sns_topic_arn and sns_role_arn:
            params["NotificationChannel"] = {"SNSTopicArn": sns_topic_arn, "RoleArn": sns_role_arn}
        response = self._client.start_document_analysis(**params)
        return response["JobId"]

    def get_document_analysis_results(self, job_id: str, *, poll_interval: float = 5.0, timeout: float = 300.0) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            response = self._client.get_document_analysis(JobId=job_id)
            status = response["JobStatus"]
            if status == "SUCCEEDED":
                blocks = self._paginate_async_results("get_document_analysis", job_id, response)
                return {"blocks": blocks, "tables": _extract_tables(blocks), "forms": _extract_forms(blocks)}
            if status == "FAILED":
                raise RuntimeError(f"Textract job {job_id} failed: {response.get('StatusMessage', 'unknown error')}")
            if time.monotonic() > deadline:
                raise TimeoutError(f"Textract job {job_id} did not complete within {timeout}s")
            time.sleep(poll_interval)

    @staticmethod
    def _build_document(*, file_path: str | None, s3_bucket: str | None, s3_key: str | None) -> dict:
        if file_path:
            data = Path(file_path).read_bytes()
            return {"Bytes": data}
        if s3_bucket and s3_key:
            return {"S3Object": {"Bucket": s3_bucket, "Name": s3_key}}
        raise ValueError("Provide either file_path or both s3_bucket and s3_key")

    def _paginate_async_results(self, method_name: str, job_id: str, first_response: dict) -> list[dict]:
        api = getattr(self._client, method_name)
        blocks: list[dict] = list(first_response.get("Blocks", []))
        next_token = first_response.get("NextToken")
        while next_token:
            response = api(JobId=job_id, NextToken=next_token)
            blocks.extend(response.get("Blocks", []))
            next_token = response.get("NextToken")
        return blocks


def _block_map(blocks: list[dict]) -> dict[str, dict]:
    return {b["Id"]: b for b in blocks}


def _extract_tables(blocks: list[dict]) -> list[list[list[str]]]:
    bmap = _block_map(blocks)
    tables = []
    for block in blocks:
        if block["BlockType"] != "TABLE":
            continue
        cells: dict[tuple[int, int], str] = {}
        for rel in block.get("Relationships", []):
            if rel["Type"] != "CHILD":
                continue
            for cell_id in rel["Ids"]:
                cell = bmap.get(cell_id, {})
                if cell.get("BlockType") != "CELL":
                    continue
                row = cell["RowIndex"]
                col = cell["ColumnIndex"]
                text_parts = []
                for word_rel in cell.get("Relationships", []):
                    if word_rel["Type"] != "CHILD":
                        continue
                    for word_id in word_rel["Ids"]:
                        word = bmap.get(word_id, {})
                        if word.get("BlockType") in ("WORD", "SELECTION_ELEMENT"):
                            text_parts.append(word.get("Text", word.get("SelectionStatus", "")))
                cells[(row, col)] = " ".join(text_parts)

        if not cells:
            continue
        max_row = max(r for r, _ in cells)
        max_col = max(c for _, c in cells)
        table = [[cells.get((r, c), "") for c in range(1, max_col + 1)] for r in range(1, max_row + 1)]
        tables.append(table)
    return tables


def _extract_forms(blocks: list[dict]) -> list[dict[str, str]]:
    bmap = _block_map(blocks)
    pairs = []
    for block in blocks:
        if block["BlockType"] != "KEY_VALUE_SET" or "KEY" not in block.get("EntityTypes", []):
            continue
        key_text = _collect_text(block, bmap, "CHILD")
        value_text = ""
        for rel in block.get("Relationships", []):
            if rel["Type"] == "VALUE":
                for val_id in rel["Ids"]:
                    value_block = bmap.get(val_id, {})
                    value_text = _collect_text(value_block, bmap, "CHILD")
        pairs.append({"key": key_text, "value": value_text})
    return pairs


def _collect_text(block: dict, bmap: dict[str, dict], rel_type: str) -> str:
    parts = []
    for rel in block.get("Relationships", []):
        if rel["Type"] != rel_type:
            continue
        for child_id in rel["Ids"]:
            child = bmap.get(child_id, {})
            bt = child.get("BlockType")
            if bt == "WORD":
                parts.append(child.get("Text", ""))
            elif bt == "SELECTION_ELEMENT":
                parts.append(child.get("SelectionStatus", ""))
    return " ".join(parts)


# ── Markdown rendering helpers ──────────────────────────────────────────────


def _y_pos(block: dict) -> float:
    """Return the top Y coordinate of a block for vertical ordering."""
    return block.get("Geometry", {}).get("BoundingBox", {}).get("Top", 0.0)


def _consume_descendants(block: dict, bmap: dict[str, dict], consumed: set[str]) -> None:
    """Recursively mark a block and all CHILD descendants as consumed."""
    consumed.add(block["Id"])
    for rel in block.get("Relationships", []):
        if rel["Type"] == "CHILD":
            for cid in rel["Ids"]:
                consumed.add(cid)
                child = bmap.get(cid)
                if child:
                    _consume_descendants(child, bmap, consumed)


def _table_block_to_rows(table_block: dict, bmap: dict[str, dict], consumed: set[str]) -> list[list[str]]:
    """Extract a TABLE block into a list of rows (each row a list of cell strings).

    Marks every descendant block (cells, words) as consumed so they are not
    duplicated in the line-text pass.
    """
    cells: dict[tuple[int, int], str] = {}
    for rel in table_block.get("Relationships", []):
        if rel["Type"] != "CHILD":
            continue
        for cell_id in rel["Ids"]:
            cell = bmap.get(cell_id, {})
            if cell.get("BlockType") != "CELL":
                continue
            row_idx = cell["RowIndex"]
            col_idx = cell["ColumnIndex"]
            parts: list[str] = []
            for wrel in cell.get("Relationships", []):
                if wrel["Type"] != "CHILD":
                    continue
                for wid in wrel["Ids"]:
                    w = bmap.get(wid, {})
                    if w.get("BlockType") in ("WORD", "SELECTION_ELEMENT"):
                        parts.append(w.get("Text", w.get("SelectionStatus", "")))
            cells[(row_idx, col_idx)] = " ".join(parts)
    _consume_descendants(table_block, bmap, consumed)
    if not cells:
        return []
    max_r = max(r for r, _ in cells)
    max_c = max(c for _, c in cells)
    return [[cells.get((r, c), "") for c in range(1, max_c + 1)] for r in range(1, max_r + 1)]


def _rows_to_gfm(rows: list[list[str]]) -> str:
    """Render rows as a GitHub-Flavored Markdown table (first row = header)."""
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    rows = [r + [""] * (ncols - len(r)) for r in rows]
    widths = [max((len(rows[ri][ci]) for ri in range(len(rows))), default=3) for ci in range(ncols)]
    widths = [max(w, 3) for w in widths]

    def _fmt(row: list[str]) -> str:
        return "| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) + " |"

    lines = [_fmt(rows[0])]
    lines.append("| " + " | ".join("-" * w for w in widths) + " |")
    for row in rows[1:]:
        lines.append(_fmt(row))
    return "\n".join(lines)


def _blocks_to_markdown(blocks: list[dict]) -> str:
    """Convert Textract AnalyzeDocument blocks into clean Markdown.

    Renders:
    - Tables   → GFM markdown tables (first row treated as header)
    - Forms    → **Key:** Value pairs
    - Leftover → plain text lines

    All content is interleaved by vertical position so the output mirrors the
    original document reading order.
    """
    bmap = _block_map(blocks)
    consumed: set[str] = set()
    elements: list[tuple[float, str]] = []  # (y_position, markdown)

    # ── Tables ──
    for b in blocks:
        if b["BlockType"] != "TABLE":
            continue
        rows = _table_block_to_rows(b, bmap, consumed)
        if rows:
            elements.append((_y_pos(b), _rows_to_gfm(rows)))

    # ── Forms (key-value pairs) ──
    for b in blocks:
        if b["BlockType"] != "KEY_VALUE_SET" or "KEY" not in b.get("EntityTypes", []):
            continue
        key = _collect_text(b, bmap, "CHILD").strip()
        _consume_descendants(b, bmap, consumed)
        value = ""
        for rel in b.get("Relationships", []):
            if rel["Type"] == "VALUE":
                for vid in rel["Ids"]:
                    vb = bmap.get(vid, {})
                    value = _collect_text(vb, bmap, "CHILD").strip()
                    _consume_descendants(vb, bmap, consumed)
        if key:
            elements.append((_y_pos(b), f"**{key}** {value}"))

    # ── Remaining text lines (not consumed by tables or forms) ──
    for b in blocks:
        if b["BlockType"] != "LINE":
            continue
        # A LINE is consumed if all its child WORDs are already accounted for
        child_ids: list[str] = []
        for rel in b.get("Relationships", []):
            if rel["Type"] == "CHILD":
                child_ids.extend(rel["Ids"])
        if child_ids and all(cid in consumed for cid in child_ids):
            continue
        text = b.get("Text", "").strip()
        if text:
            elements.append((_y_pos(b), text))

    # Sort by vertical position (reading order: top → bottom)
    elements.sort(key=lambda e: e[0])
    return "\n\n".join(e[1] for e in elements)
