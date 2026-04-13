# YOLO Custom Training Guide

## Overview
Train a custom YOLOv8 model specifically for Warhammer 40K miniature detection with generous bounding boxes.

## Why Custom Training?

**Current Issues:**
- Roboflow model trained on only 97 images
- Bboxes sometimes too tight, cutting off:
  - Extended limbs/weapons
  - Tails (Tyranids)
  - Antennae
  - Dynamic poses

**Benefits of Custom Training:**
- Full control over bbox labeling standards
- Can enforce "generous bbox" policy
- Train on your specific miniature collection
- Free (runs locally)
- Can achieve 90%+ bbox accuracy with 300+ images

## Prerequisites

```bash
# Install dependencies
pip install ultralytics opencv-python pillow

# Verify installation
yolo version
```

## Step 1: Prepare Training Data

### A. Collect Images

Use your existing debug overlays as a starting point:

```bash
# Your debug overlays already show YOLO detections
ls backend/debug_overlays/

# Save images where YOLO fails:
# - Cuts off tails
# - Misses extended arms
# - Too tight around miniatures
```

**Target:** 200-500 images minimum
- 70% training set
- 20% validation set
- 10% test set

### B. Label Images with LabelImg

Install LabelImg (free bbox annotation tool):

```bash
pip install labelImg
labelImg
```

**Labeling Standards (CRITICAL):**

✅ **GOOD Bboxes:**
- Include ALL parts of miniature
- 10-15% padding around edges
- Include base/stand
- Capture dynamic poses fully
- Box extends to tips of:
  - Weapons
  - Tails
  - Antennae
  - Wings
  - Claws

❌ **BAD Bboxes:**
- Tight to body
- Cuts off extended limbs
- Excludes base
- Misses weapon tips

**Class Labels:**
- `miniature` (single class for detection)
- Or faction-specific: `tyranid`, `space_marine`, etc.

### C. Organize Dataset

```
yolo_training_data/
├── images/
│   ├── train/
│   │   ├── image1.jpg
│   │   ├── image2.jpg
│   │   └── ...
│   ├── val/
│   │   ├── image50.jpg
│   │   └── ...
│   └── test/
│       ├── image60.jpg
│       └── ...
└── labels/
    ├── train/
    │   ├── image1.txt  # YOLO format bbox annotations
    │   ├── image2.txt
    │   └── ...
    ├── val/
    │   └── ...
    └── test/
        └── ...
```

**YOLO Label Format (image1.txt):**
```
0 0.5 0.5 0.3 0.4
# class_id center_x center_y width height (normalized 0-1)
```

## Step 2: Create Dataset Config

Create `warhammer_dataset.yaml`:

```yaml
# Train/val/test sets
path: /home/sinan/photoanalyzer/yolo_training_data
train: images/train
val: images/val
test: images/test

# Number of classes
nc: 1

# Class names
names:
  0: miniature
```

## Step 3: Train the Model

### Basic Training (YOLOv8n - Nano)

```bash
yolo train \
  model=yolov8n.pt \
  data=warhammer_dataset.yaml \
  epochs=100 \
  imgsz=640 \
  batch=16 \
  patience=20 \
  device=0  # Use GPU (or 'cpu' if no GPU)
```

**Training Parameters:**
- `epochs=100` - Number of training iterations
- `imgsz=640` - Image size (640x640 is standard)
- `batch=16` - Batch size (adjust based on GPU memory)
- `patience=20` - Early stopping if no improvement for 20 epochs

**Expected Time:**
- 200 images, 100 epochs: ~30 minutes (GPU) / 3-4 hours (CPU)

### Advanced: Data Augmentation

YOLOv8 includes augmentation by default, but you can customize:

```yaml
# In warhammer_dataset.yaml, add:
augment: true
hsv_h: 0.015      # Hue variation
hsv_s: 0.7        # Saturation
hsv_v: 0.4        # Value
degrees: 10       # Rotation
translate: 0.1    # Translation
scale: 0.5        # Scale
flipud: 0.5       # Vertical flip
fliplr: 0.5       # Horizontal flip
mosaic: 1.0       # Mosaic augmentation
```

## Step 4: Evaluate Results

After training completes:

```bash
# Check results
ls runs/detect/train/

# View metrics
cat runs/detect/train/results.csv

# Key metrics:
# - mAP@0.5: Should be >0.85 for good detection
# - precision: % of detections that are correct
# - recall: % of miniatures detected
```

**Visualize Results:**
```bash
# View predictions on test set
yolo val model=runs/detect/train/weights/best.pt data=warhammer_dataset.yaml
```

## Step 5: Export for Production

### Option A: Export to ONNX (for Node.js)

```bash
yolo export model=runs/detect/train/weights/best.pt format=onnx
```

This creates `best.onnx` file you can use with `onnxruntime-node`.

### Option B: Keep PyTorch Format

If you prefer Python inference, keep the `.pt` file.

## Step 6: Integrate into Project

### Create Python Inference Service

Create `backend/yolo_service.py`:

```python
from ultralytics import YOLO
from flask import Flask, request, jsonify
import cv2
import numpy as np

app = Flask(__name__)

# Load your custom model
model = YOLO('runs/detect/train/weights/best.pt')

@app.route('/detect', methods=['POST'])
def detect():
    # Get image from request
    file = request.files['image']
    img_bytes = file.read()
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Run inference
    results = model(img, conf=0.4)  # 40% confidence threshold

    # Extract bboxes
    detections = []
    for r in results:
        boxes = r.boxes
        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            detections.append({
                'bbox': [x1, y1, x2, y2],
                'confidence': conf,
                'class': 'miniature'
            })

    return jsonify({'detections': detections})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

### Start Service

```bash
python backend/yolo_service.py
```

### Update Node.js to Use Local YOLO

Modify `backend/src/services/yoloDetector.ts`:

```typescript
// Change from Roboflow API to local service
const YOLO_SERVICE_URL = process.env.YOLO_SERVICE_URL || 'http://localhost:5000'

export async function detectWithYOLO(imageBuffer: Buffer) {
  const formData = new FormData()
  formData.append('image', imageBuffer, 'image.jpg')

  const response = await axios.post(`${YOLO_SERVICE_URL}/detect`, formData)

  // Parse response (same format as before)
  return parseDetections(response.data.detections)
}
```

## Step 7: Continuous Improvement

### Active Learning Loop

1. **Deploy model** → Detect miniatures
2. **Save hard cases** → Images where confidence < 0.6
3. **Review & relabel** → Fix incorrect bboxes
4. **Retrain** → Add new images to dataset
5. **Repeat** → Model gets better over time

**Script to Auto-Save Hard Cases:**

```typescript
// In bboxDetector.ts
if (SAVE_HARD_CASES && confidence < 0.6) {
  const hardCasePath = `backend/hard_cases/${timestamp}_${cropId}.jpg`
  await fs.writeFile(hardCasePath, cropBuffer)
  logger.info(`Saved hard case: ${hardCasePath}`)
}
```

## Expected Results

| Metric | Before Training | After 200 Images | After 500 Images |
|--------|----------------|------------------|------------------|
| mAP@0.5 | 0.65 (Roboflow) | 0.80 | 0.90+ |
| Bbox Quality | 60% good | 85% good | 95% good |
| Tail Detection | Often cut off | Usually captured | Always captured |
| Extended Limbs | 50% captured | 85% captured | 95% captured |

## Quick Start Script

Save as `train_yolo.sh`:

```bash
#!/bin/bash

# Setup
mkdir -p yolo_training_data/{images,labels}/{train,val,test}

# Download pre-trained weights
yolo download model=yolov8n.pt

# Train
yolo train \
  model=yolov8n.pt \
  data=warhammer_dataset.yaml \
  epochs=100 \
  imgsz=640 \
  batch=16 \
  patience=20 \
  device=0

# Evaluate
yolo val model=runs/detect/train/weights/best.pt data=warhammer_dataset.yaml

# Export
yolo export model=runs/detect/train/weights/best.pt format=onnx

echo "Training complete! Model saved to runs/detect/train/weights/best.pt"
```

## Troubleshooting

### Issue: Bboxes Still Too Tight

**Solution:** Review your labeling standards. Make bboxes 15-20% larger.

### Issue: Low mAP (<0.7)

**Solutions:**
- Add more training images (aim for 300+)
- Increase epochs (150-200)
- Use larger model: `yolov8s.pt` or `yolov8m.pt`
- Check label quality (are bboxes accurate?)

### Issue: Overfitting

**Symptoms:** High training accuracy, low validation accuracy

**Solutions:**
- Add more training data
- Enable more augmentation
- Reduce epochs
- Use early stopping (`patience=20`)

## Resources

- [Ultralytics YOLOv8 Docs](https://docs.ultralytics.com/)
- [LabelImg Tool](https://github.com/tzutalin/labelImg)
- [YOLO Dataset Format](https://docs.ultralytics.com/datasets/detect/)

## Next Steps

After training your model:
1. Compare with Roboflow model
2. A/B test on real images
3. Deploy the better performer
4. Set up continuous learning pipeline
