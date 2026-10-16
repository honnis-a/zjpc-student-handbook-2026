#!/usr/bin/env python3
"""Run local Vision OCR on the prepared page manifest, preserving raw results."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import time

from vision_ocr import recognize


def write_json(path, result):
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def process(page, output_dir, overwrite):
    destination = output_dir / f"scan_{page['scan_id']:03d}.json"
    if destination.is_file() and not overwrite:
        existing = json.loads(destination.read_text(encoding="utf-8"))
        if existing.get("status") == "ok":
            return {"scan_id": page["scan_id"], "status": "ok", "cached": True, "line_count": len(existing["lines"])}
    start = time.monotonic()
    record = {
        "scan_id": page["scan_id"],
        "image_index": page["image_index"],
        "book_page": page.get("book_page"),
        "toc_page": page.get("toc_page"),
        "source": page["image_path"],
        "original_filename": page["filename"],
        "engine": "macOS Vision VNRecognizeTextRequest",
        "recognitionLevel": "accurate",
        "usesLanguageCorrection": False,
        "usesCPUOnly": True,
        "recognitionLanguages": ["zh-Hans", "en-US"],
        "coordinateSystem": "normalized; origin bottom-left; prepared page crop",
    }
    try:
        record["lines"] = recognize(page["image_path"], candidates=5)
        record["status"] = "ok"
    except Exception as error:
        record["status"] = "failed"
        record["error"] = f"{type(error).__name__}: {error}"
        record["lines"] = []
    record["elapsed_seconds"] = round(time.monotonic() - start, 3)
    write_json(destination, record)
    return {"scan_id": page["scan_id"], "status": record["status"], "cached": False, "line_count": len(record["lines"]), **({"error": record["error"]} if "error" in record else {})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("tmp/pages_manifest.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/ocr"))
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    pages = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    completed = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = [pool.submit(process, page, args.output_dir, args.overwrite) for page in pages]
        for future in as_completed(pending):
            result = future.result()
            completed.append(result)
            if result["status"] != "ok":
                print(json.dumps({"failure": result}, ensure_ascii=False), flush=True)
            if len(completed) % 10 == 0 or len(completed) == len(pages):
                print(json.dumps({"completed": len(completed), "total": len(pages), "failed": sum(x["status"] != "ok" for x in completed), "elapsed_seconds": round(time.monotonic() - started, 1)}, ensure_ascii=False), flush=True)
    summary = {
        "total": len(pages),
        "succeeded": sum(x["status"] == "ok" for x in completed),
        "failed": sum(x["status"] != "ok" for x in completed),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "pages": sorted(completed, key=lambda x: x["scan_id"]),
    }
    write_json(args.output_dir / "batch_summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "pages"}, ensure_ascii=False), flush=True)
    if summary["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
