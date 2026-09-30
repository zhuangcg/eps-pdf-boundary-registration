"""Isolated OCR process: avoids native-library conflicts with GIS runtimes."""
from __future__ import annotations

import argparse
import json
import sys

import fitz
import numpy as np
from rapidocr_onnxruntime import RapidOCR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("dpi", type=int)
    ap.add_argument("page_index", type=int, nargs="?", default=0)
    args = ap.parse_args()
    with fitz.open(args.pdf) as doc:
        pix = doc[args.page_index].get_pixmap(dpi=args.dpi, alpha=False)
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        found, _ = RapidOCR()(image)
    zoom = args.dpi / 72.0
    labels = []
    for box, text, confidence in found or []:
        xs = [float(p[0]) / zoom for p in box]
        ys = [float(p[1]) / zoom for p in box]
        labels.append({"raw_text": text, "confidence": float(confidence), "source": "ocr",
                       "page_box": [min(xs), min(ys), max(xs), max(ys)],
                       "page_x_pt": float(np.mean(xs)), "page_y_pt": float(np.mean(ys))})
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(labels, ensure_ascii=False))


if __name__ == "__main__":
    main()
