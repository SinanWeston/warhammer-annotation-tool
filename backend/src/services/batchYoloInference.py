"""
Batch YOLO Inference for Active Learning

Loads the YOLO model once, reads image paths from a file,
runs inference on each, and outputs JSON lines to stdout.
Each line: {"imagePath": "...", "maxConfidence": 0.8, "avgConfidence": 0.6, "numPredictions": 5}
"""

import sys
import json

def main():
    if len(sys.argv) < 3:
        print("Usage: batchYoloInference.py <model_path> <image_list_file>", file=sys.stderr)
        sys.exit(1)

    model_path = sys.argv[1]
    image_list_file = sys.argv[2]

    from ultralytics import YOLO
    model = YOLO(model_path)

    with open(image_list_file, 'r') as f:
        image_paths = [line.strip() for line in f if line.strip()]

    for img_path in image_paths:
        try:
            results = model.predict(img_path, conf=0.10, verbose=False)
            confs = []
            for r in results:
                for box in r.boxes:
                    confs.append(float(box.conf[0]))

            result = {
                "imagePath": img_path,
                "maxConfidence": max(confs) if confs else 0.0,
                "avgConfidence": sum(confs) / len(confs) if confs else 0.0,
                "numPredictions": len(confs)
            }
        except Exception as e:
            result = {
                "imagePath": img_path,
                "maxConfidence": 0.0,
                "avgConfidence": 0.0,
                "numPredictions": 0,
                "error": str(e)
            }

        print(json.dumps(result), flush=True)

if __name__ == "__main__":
    main()
