---
name: export
description: Export and validate YOLO dataset from annotations. Use before training runs or when checking dataset integrity.
---

# YOLO Dataset Export & Validation

## YOLO-Pose Export Format

Hierarchical bboxes exported as pose keypoints:
- **Model bbox**: Standard YOLO format (class, x_center, y_center, width, height)
- **Base bbox**: 4 keypoints at corners (TL, TR, BR, BL) with visibility flags
- **Missing base**: Omit keypoints entirely (5 values instead of 17)
- **Keypoint format**: 12 values (4 keypoints x 3: x, y, visibility)
- **Coordinates**: Normalized to 0-1 range

### Annotated Examples

```
# Model with base (17 values)
# class x_center y_center width height TL_x TL_y TL_vis TR_x TR_y TR_vis BR_x BR_y BR_vis BL_x BL_y BL_vis
0 0.5 0.5 0.3 0.2 0.4 0.4 1 0.6 0.4 1 0.6 0.6 1 0.4 0.6 1

# Model without base (5 values)
# class x_center y_center width height
0 0.5 0.5 0.3 0.2
```

## Export Commands

```bash
# Validate before export (recommended)
curl -X POST http://localhost:3001/api/annotate/validate-export

# Export to YOLO
curl -X POST http://localhost:3001/api/annotate/export \
  -H "Content-Type: application/json" \
  -d '{}'

# Validate exported dataset
python3 scripts/validate_yolo_dataset.py backend/yolo_dataset
```

## Export Code Location

Edit `backend/src/services/annotationService.ts` -> `exportToYOLO()` method

## Data Paths

- **Input images**: `backend/training_data/{faction}/{source}/`
- **Annotations**: `backend/training_data_annotations/` (JSON)
- **YOLO output**: `backend/yolo_dataset/`
- **Confidence scores**: `backend/confidence_scores.json`
- **Trained model**: `runs/yolo11_colab_best.pt`

## Validation Checks

- Each image has a corresponding .txt label file
- Label format correct (class_id x_center y_center width height, normalized 0-1)
- No coordinates outside [0,1]
- No empty label files
- No images without labels
- Class distribution report
- 5 values (no base) or 17 values (with base) per line
- Keypoint visibility flags are 0, 1, or 2

## Best Practices

- Always normalize coordinates to 0-1 range
- Include visibility flags: keypoints need (x, y, visibility) not just (x, y)
- Handle missing bases: omit keypoints entirely (5 values, not 17 with zeros)
- Run `validateAllAnnotations()` before YOLO export
