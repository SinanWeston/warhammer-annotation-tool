# Train Custom YOLO Model - Complete Guide

## Overview

After annotating 200+ images, you can train a custom YOLO model that produces better bboxes than the current Roboflow model.

## Prerequisites

### 1. Annotated Dataset
- ✅ 200+ images in `backend/yolo_dataset/images/`
- ✅ Matching labels in `backend/yolo_dataset/labels/`
- ✅ YOLO format (class x_center y_center width height)

### 2. Python Environment
```bash
pip install ultralytics
```

## Step-by-Step Training

### Step 1: Split Dataset (70/20/10)

Run the automatic splitter:
```bash
cd /home/sinan/photoanalyzer
python3 scripts/split_dataset.py
```

**What this does:**
- Shuffles your images randomly
- Splits: 70% train, 20% val, 10% test
- Copies image/label pairs to split directories
- Creates `dataset.yaml` config file

**Output:**
```
backend/yolo_dataset/
├── train/
│   ├── images/  (140 images)
│   └── labels/  (140 labels)
├── val/
│   ├── images/  (40 images)
│   └── labels/  (40 labels)
├── test/
│   ├── images/  (20 images)
│   └── labels/  (20 labels)
└── dataset.yaml
```

### Step 2: Verify Dataset

Check the generated `dataset.yaml`:
```yaml
path: /home/sinan/photoanalyzer/backend/yolo_dataset
train: train/images
val: val/images
test: test/images

names:
  0: miniature
```

### Step 3: Train YOLO

**Basic Training** (recommended for first run):
```bash
cd /home/sinan/photoanalyzer/backend/yolo_dataset

yolo train \
  data=dataset.yaml \
  model=yolov8n.pt \
  epochs=100 \
  imgsz=640 \
  batch=16 \
  device=0
```

**Parameters Explained:**
- `model=yolov8n.pt` - Nano model (fastest, smallest)
- `epochs=100` - Training iterations
- `imgsz=640` - Image size (640x640)
- `batch=16` - Images per batch (adjust based on GPU memory)
- `device=0` - Use GPU 0 (or `cpu` for CPU training)

**Advanced Training** (if first run is good):
```bash
yolo train \
  data=dataset.yaml \
  model=yolov8s.pt \
  epochs=200 \
  imgsz=640 \
  batch=16 \
  patience=50 \
  save_period=10 \
  device=0
```

**Model Sizes:**
- `yolov8n.pt` - Nano (fastest, 3.2M params)
- `yolov8s.pt` - Small (11.2M params)
- `yolov8m.pt` - Medium (25.9M params)
- `yolov8l.pt` - Large (43.7M params)
- `yolov8x.pt` - Extra Large (68.2M params)

**Recommendation**: Start with `yolov8n.pt` or `yolov8s.pt`

### Step 4: Monitor Training

YOLO creates a training run directory:
```
runs/detect/train/
├── weights/
│   ├── best.pt       ← Best model (use this!)
│   └── last.pt       ← Last epoch
├── results.png       ← Training graphs
├── confusion_matrix.png
└── val_batch0_pred.jpg  ← Predictions on val set
```

**During training, watch for:**
- `mAP@0.5` increasing (target: >0.85)
- Loss decreasing (box_loss, cls_loss)
- No overfitting (train and val metrics similar)

### Step 5: Evaluate Results

**Check metrics:**
```bash
cat runs/detect/train/results.txt
```

**Look for:**
- `mAP@0.5` > 0.85 (85% bbox accuracy)
- `mAP@0.5:0.95` > 0.60 (good across IoU thresholds)
- `Precision` > 0.80
- `Recall` > 0.80

**View predictions:**
```bash
# Open in image viewer
eog runs/detect/train/val_batch0_pred.jpg
```

**Check if bboxes are generous:**
- ✅ Include all limbs, weapons, tails
- ✅ Capture full base
- ✅ No cut-off parts

### Step 6: Test on New Images

```bash
yolo predict \
  model=runs/detect/train/weights/best.pt \
  source=../test-images/ \
  save=True \
  conf=0.25
```

**Check predictions:**
```bash
ls runs/detect/predict/
# Look at predicted images
```

## Deployment Options

### Option A: Local YOLO Service (Recommended)

Create a local inference service:

**1. Create service script:**
```python
# backend/yolo_service.py
from ultralytics import YOLO
from fastapi import FastAPI, File, UploadFile
from PIL import Image
import io

app = FastAPI()
model = YOLO('runs/detect/train/weights/best.pt')

@app.post("/detect")
async def detect(image: UploadFile = File(...)):
    img = Image.open(io.BytesIO(await image.read()))
    results = model(img)

    detections = []
    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = box.conf[0].item()
            cls = int(box.cls[0].item())

            detections.append({
                "bbox": [x1, y1, x2, y2],
                "confidence": conf,
                "class": cls
            })

    return {"detections": detections}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8001)
```

**2. Install dependencies:**
```bash
cd backend
pip install fastapi uvicorn pillow
```

**3. Start service:**
```bash
python3 yolo_service.py
```

**4. Update backend to use local service:**
```typescript
// backend/src/services/localYoloDetector.ts
const YOLO_SERVICE_URL = 'http://localhost:8001/detect'

export async function detectWithLocalYolo(imageBuffer: Buffer) {
  const formData = new FormData()
  formData.append('image', new Blob([imageBuffer]))

  const response = await fetch(YOLO_SERVICE_URL, {
    method: 'POST',
    body: formData
  })

  const data = await response.json()
  return data.detections
}
```

**5. Update .env:**
```bash
USE_LOCAL_YOLO=true
LOCAL_YOLO_URL=http://localhost:8001/detect
```

### Option B: Upload to Roboflow

**1. Export to Roboflow format:**
```bash
# Roboflow expects same structure we already have
# Just zip the dataset
cd backend/yolo_dataset
zip -r warhammer_dataset.zip train/ val/ test/ dataset.yaml
```

**2. Upload to Roboflow:**
- Go to roboflow.com
- Create new project
- Upload `warhammer_dataset.zip`
- Deploy model
- Get new API endpoint

**3. Update .env:**
```bash
ROBOFLOW_MODEL_ENDPOINT=https://detect.roboflow.com/your-new-model/1
```

### Option C: ONNX Export (Fastest)

Convert to ONNX for faster inference:

```bash
yolo export model=runs/detect/train/weights/best.pt format=onnx
```

This creates `best.onnx` for use with ONNX Runtime.

## Expected Results

### Before (Roboflow 97 images)
- ❌ Tight bboxes
- ❌ Cuts off extended limbs
- ❌ Misses tails/antennae
- ⚠️  ~70-80% bbox quality

### After (Your custom model)
- ✅ Generous bboxes
- ✅ Includes all parts
- ✅ Captures dynamic poses
- ✅ 90%+ bbox quality

### Downstream Benefits
- **Better crops** → More context for classifier
- **Higher classification accuracy** → AI can see more features
- **Fewer errors** → Less manual correction needed

## Troubleshooting

### Training fails with CUDA error
**Solution**: Use CPU or reduce batch size
```bash
yolo train data=dataset.yaml model=yolov8n.pt device=cpu batch=8
```

### mAP is low (<0.70)
**Possible causes:**
- Not enough data (need 300+ images)
- Inconsistent annotations
- Images too varied (different lighting/angles)

**Solutions:**
- Annotate more images
- Review annotations for consistency
- Add data augmentation

### Overfitting (train good, val bad)
**Solution**: Add regularization
```bash
yolo train data=dataset.yaml model=yolov8n.pt epochs=100 dropout=0.2
```

### Predictions too tight
**Check your annotations:**
- Are your boxes generous enough?
- Do they include padding?
- Re-annotate with more padding

## Hyperparameter Tuning

### If you have time, optimize:

```bash
# Grid search
yolo train data=dataset.yaml model=yolov8n.pt \
  lr0=0.001,0.01 \
  lrf=0.01,0.1 \
  momentum=0.8,0.9 \
  weight_decay=0.0005,0.001
```

### Recommended settings for small datasets:

```bash
yolo train \
  data=dataset.yaml \
  model=yolov8n.pt \
  epochs=150 \
  patience=30 \
  lr0=0.001 \
  lrf=0.01 \
  momentum=0.937 \
  weight_decay=0.0005 \
  warmup_epochs=3 \
  box=7.5 \
  cls=0.5
```

## Performance Benchmarks

### Speed (640x640 image)
- YOLOv8n: ~10ms (CPU), ~2ms (GPU)
- YOLOv8s: ~20ms (CPU), ~3ms (GPU)
- YOLOv8m: ~40ms (CPU), ~5ms (GPU)

### Accuracy (typical)
- 200 images: mAP@0.5 ~0.75-0.85
- 500 images: mAP@0.5 ~0.85-0.92
- 1000 images: mAP@0.5 ~0.90-0.95

### File Sizes
- YOLOv8n: ~6MB
- YOLOv8s: ~22MB
- YOLOv8m: ~52MB

## Next Steps After Training

### 1. Integrate with App
- Deploy using Option A, B, or C above
- Update backend to use new model
- Test with real images

### 2. Continuous Improvement
- Collect failure cases
- Re-annotate with better standards
- Retrain with more data
- Iterate until >90% accuracy

### 3. Monitor Performance
- Track bbox quality in production
- Log cases where bboxes are bad
- Use debug overlays to verify
- Re-train periodically

## Summary

✅ **Annotate** 200+ images with generous bboxes
✅ **Split** dataset with `split_dataset.py`
✅ **Train** with `yolo train`
✅ **Deploy** locally or to Roboflow
✅ **Enjoy** 90%+ bbox accuracy!

**Time Investment:**
- Annotation: 10-50 hours (200-500 images)
- Training: 1-4 hours (depends on GPU)
- Deployment: 30 minutes
- **Total: 12-55 hours**

**Return on Investment:**
- Better bbox quality → Better crops → Better classification
- Reduce misclassification rate by 20-30%
- Build proprietary dataset for your miniature collection

---

**Ready to train? Let's go! 🚀**
