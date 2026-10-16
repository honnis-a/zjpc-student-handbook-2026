#!/usr/bin/env python3
"""Local macOS Vision OCR without PyObjC or an Xcode compiler.

Uses accurate recognition and disables language correction. Emits raw line
candidates and normalized Vision coordinates (origin at the bottom left).
"""

import argparse
import ctypes as C
import json
from pathlib import Path
import sys
import tempfile


class CGPoint(C.Structure):
    _fields_ = [("x", C.c_double), ("y", C.c_double)]


class CGSize(C.Structure):
    _fields_ = [("width", C.c_double), ("height", C.c_double)]


class CGRect(C.Structure):
    _fields_ = [("origin", CGPoint), ("size", CGSize)]


def recognize(image_path, candidates=5):
    if sys.platform != "darwin":
        raise RuntimeError("This script requires macOS Vision.framework")
    objc = C.CDLL("/usr/lib/libobjc.A.dylib")
    C.CDLL("/System/Library/Frameworks/Foundation.framework/Foundation")
    C.CDLL("/System/Library/Frameworks/Vision.framework/Vision")
    objc.objc_getClass.argtypes = [C.c_char_p]
    objc.objc_getClass.restype = C.c_void_p
    objc.sel_registerName.argtypes = [C.c_char_p]
    objc.sel_registerName.restype = C.c_void_p
    send_address = C.cast(objc.objc_msgSend, C.c_void_p).value
    selectors = {}
    methods = {}

    def send(receiver, selector, restype=C.c_void_p, argtypes=(), args=()):
        key = (restype, argtypes)
        if key not in methods:
            methods[key] = C.CFUNCTYPE(restype, C.c_void_p, C.c_void_p, *argtypes)(send_address)
        if selector not in selectors:
            selectors[selector] = objc.sel_registerName(selector.encode())
        return methods[key](receiver, selectors[selector], *args)

    def klass(name):
        value = objc.objc_getClass(name.encode())
        if not value:
            raise RuntimeError(f"Objective-C class unavailable: {name}")
        return value

    def nsstring(value):
        return send(klass("NSString"), "stringWithUTF8String:", argtypes=(C.c_char_p,), args=(value.encode(),))

    def string(value):
        if not value:
            return None
        raw = send(value, "UTF8String", restype=C.c_char_p)
        return raw.decode("utf-8") if raw else ""

    def array(values):
        data = (C.c_void_p * len(values))(*values)
        return send(klass("NSArray"), "arrayWithObjects:count:", argtypes=(C.POINTER(C.c_void_p), C.c_ulong), args=(data, len(values)))

    pool = send(klass("NSAutoreleasePool"), "new")
    handler = request = None
    try:
        url = send(klass("NSURL"), "fileURLWithPath:", argtypes=(C.c_void_p,), args=(nsstring(str(Path(image_path).resolve())),))
        options = send(klass("NSDictionary"), "dictionary")
        handler = send(klass("VNImageRequestHandler"), "alloc")
        handler = send(handler, "initWithURL:options:", argtypes=(C.c_void_p, C.c_void_p), args=(url, options))
        request = send(klass("VNRecognizeTextRequest"), "new")
        send(request, "setUsesCPUOnly:", restype=None, argtypes=(C.c_bool,), args=(True,))
        send(request, "setRecognitionLevel:", restype=None, argtypes=(C.c_long,), args=(0,))
        send(request, "setUsesLanguageCorrection:", restype=None, argtypes=(C.c_bool,), args=(False,))
        send(request, "setRecognitionLanguages:", restype=None, argtypes=(C.c_void_p,), args=(array([nsstring("zh-Hans"), nsstring("en-US")]),))
        # Avoid language auto-detection silently overriding the requested language list.
        responds = send(request, "respondsToSelector:", restype=C.c_bool, argtypes=(C.c_void_p,), args=(objc.sel_registerName(b"setAutomaticallyDetectsLanguage:"),))
        if responds:
            send(request, "setAutomaticallyDetectsLanguage:", restype=None, argtypes=(C.c_bool,), args=(False,))
        error = C.c_void_p()
        succeeded = send(handler, "performRequests:error:", restype=C.c_bool, argtypes=(C.c_void_p, C.POINTER(C.c_void_p)), args=(array([request]), C.byref(error)))
        if not succeeded:
            description = string(send(error, "localizedDescription")) if error.value else "Vision returned failure without NSError (this can occur inside a restricted sandbox)"
            raise RuntimeError(description)
        results = send(request, "results")
        count = send(results, "count", restype=C.c_ulong)
        lines = []
        for index in range(count):
            observation = send(results, "objectAtIndex:", argtypes=(C.c_ulong,), args=(index,))
            box = send(observation, "boundingBox", restype=CGRect)
            alternatives = send(observation, "topCandidates:", argtypes=(C.c_ulong,), args=(candidates,))
            number = send(alternatives, "count", restype=C.c_ulong)
            choices = []
            for alternative_index in range(number):
                choice = send(alternatives, "objectAtIndex:", argtypes=(C.c_ulong,), args=(alternative_index,))
                choices.append({"text": string(send(choice, "string")), "confidence": float(send(choice, "confidence", restype=C.c_float))})
            lines.append({
                "index": index,
                "text": choices[0]["text"] if choices else "",
                "confidence": choices[0]["confidence"] if choices else None,
                "boundingBox": {"x": box.origin.x, "y": box.origin.y, "width": box.size.width, "height": box.size.height},
                "candidates": choices,
            })
        return lines
    finally:
        if request:
            send(request, "release", restype=None)
        if handler:
            send(handler, "release", restype=None)
        send(pool, "drain", restype=None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--rotate", type=int, choices=(0, 90, 180, 270), default=0, help="Counterclockwise degrees, using a temporary copy")
    parser.add_argument("--candidates", type=int, default=5)
    parser.add_argument("--output", type=Path, help="Write JSON here; otherwise use stdout")
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error(f"Image does not exist: {args.image}")
    if args.candidates < 1:
        parser.error("--candidates must be positive")
    from PIL import Image, ImageOps
    with tempfile.TemporaryDirectory(prefix="vision-ocr-") as temp_dir:
        with Image.open(args.image) as original:
            original_size = original.size
            # Resolve EXIF orientation consistently before rotation and OCR.
            processed = ImageOps.exif_transpose(original)
            has_exif_orientation = original.getexif().get(274, 1) != 1
            if args.rotate:
                processed = processed.rotate(args.rotate, expand=True)
            processed_size = processed.size
            image_path = args.image
            if args.rotate or has_exif_orientation:
                image_path = Path(temp_dir) / "prepared.png"
                processed.save(image_path)
            lines = recognize(image_path, args.candidates)
        result = {
            "source": str(args.image.resolve()),
            "engine": "macOS Vision VNRecognizeTextRequest",
            "recognitionLevel": "accurate",
            "usesCPUOnly": True,
            "usesLanguageCorrection": False,
            "recognitionLanguages": ["zh-Hans", "en-US"],
            "rotationCounterclockwise": args.rotate,
            "originalSize": list(original_size),
            "processedSize": list(processed_size),
            "coordinateSystem": "normalized; origin bottom-left; processed image",
            "lines": lines,
        }
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()
