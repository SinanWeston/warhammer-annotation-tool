# Annotation Tool Improvements

**Created**: December 27, 2025
**Last Updated**: December 27, 2025
**Product Mission**: Fast, reliable annotation for YOLO training

---

## Product Direction

This tool has **one job**: create clean, correct training data for YOLOv8-pose models.

**In scope:**
- Features that increase annotation throughput (undo/redo, zoom/pan, keyboard shortcuts)
- Features that prevent bad exports (validation, quality checks, contract enforcement)
- Training pipeline setup (environment, configs, testing)

**Out of scope:**
- Bulk gallery/management (defer until annotation complete)
- Templates (high risk of systematic errors)
- Any feature that doesn't directly serve annotation speed or data correctness

**Previously deferred, now implemented (Feb 2026):**
- ~~Analytics dashboards~~ — Quality Dashboard implemented with box stats, faction sizes, speed, outliers
- Active Learning pipeline — confidence-based annotation prioritization

---

## YOLO-Pose Label Contract

**This must be defined BEFORE implementing any feature.**

### Current Export Format (from annotationService.ts)

The tool exports to **YOLOv8-pose format** where:
- Each miniature = 1 object instance
- Model bbox = standard YOLO bbox (class x_center y_center width height)
- Base bbox corners = 4 keypoints (pose data)

### Critical Questions to Answer

Before writing any code, we must define:

#### 1. Missing Base Bbox Behavior
**Question**: What happens when a model bbox exists but base bbox is missing?

**Options:**
- **A)** Emit keypoints with `visibility=0` (4 keypoints at 0,0 with v=0)
- **B)** Omit keypoints entirely (standard bbox only, no pose data)
- **C)** Reject/flag annotation as incomplete during export

**Recommendation**: **Option B** (omit keypoints)
- Simplest for YOLO (standard detection + optional pose)
- Models without visible bases are valid (flying units, mounted on larger base, etc.)
- No fake data (0,0 coordinates are lies)

**Implementation:**
```python
# In exportToYOLO()
if bbox.baseBbox:
    # Export with keypoints
    keypoints = convert_base_to_keypoints(bbox.baseBbox)
    line = f"{class_id} {bbox_norm} {keypoints}\n"
else:
    # Export as standard detection (no pose data)
    line = f"{class_id} {bbox_norm}\n"
```

#### 2. Keypoint Ordering
**Question**: What order should base bbox corners be in?

**Standard**: **TL → TR → BR → BL** (clockwise from top-left)
- Matches common pose annotation conventions
- Easy to visualize and validate
- Consistent with COCO keypoint ordering patterns

**Implementation:**
```typescript
// Convert base bbox to 4 corner keypoints
function baseBboxToKeypoints(baseBbox: BBox): Keypoint[] {
  return [
    { x: baseBbox.x, y: baseBbox.y, visible: 1 },                           // TL
    { x: baseBbox.x + baseBbox.width, y: baseBbox.y, visible: 1 },          // TR
    { x: baseBbox.x + baseBbox.width, y: baseBbox.y + baseBbox.height, visible: 1 }, // BR
    { x: baseBbox.x, y: baseBbox.y + baseBbox.height, visible: 1 }          // BL
  ];
}
```

#### 3. Class Strategy
**Question**: Single class or multi-class?

**Recommendation**: **Single class ("miniature")** for initial training
- Simpler model (detection + pose, not classification)
- Faction classification can be separate model/pipeline
- 18k images all labeled "miniature" = strong detector
- Can add faction classification later if needed

**data.yaml:**
```yaml
nc: 1  # number of classes
names: ['miniature']
kpt_shape: [4, 3]  # 4 keypoints, 3 values each (x, y, visibility)
```

#### 4. Visibility Flags
**Question**: How to encode keypoint visibility?

**Recommendation**: **Binary (0 or 1)**
- 0 = not visible / not annotated
- 1 = visible and annotated
- Simpler than confidence values (0.0-1.0)
- Matches COCO standard

**For base bboxes**: All corners always visible=1 (if base exists, all corners exist)

#### 5. Coordinate Normalization
**Question**: How do we convert pixel coordinates to normalized YOLO format?

**YOLO Format** (normalized 0-1):
```
class x_center y_center width height [kpt1_x kpt1_y kpt1_v ...]
```

**Conversion from pixels**:
```typescript
function normalizeBbox(bbox: BBox, imageWidth: number, imageHeight: number) {
  const x_center = (bbox.x + bbox.width / 2) / imageWidth;
  const y_center = (bbox.y + bbox.height / 2) / imageHeight;
  const width = bbox.width / imageWidth;
  const height = bbox.height / imageHeight;

  return { x_center, y_center, width, height };
}

function normalizeKeypoint(kpt: {x: number, y: number}, imageWidth: number, imageHeight: number) {
  return {
    x: kpt.x / imageWidth,
    y: kpt.y / imageHeight
  };
}

// Full export example
function exportInstance(modelBbox: BBox, baseBbox: BBox | null, imageWidth: number, imageHeight: number): string {
  const norm = normalizeBbox(modelBbox, imageWidth, imageHeight);
  let line = `0 ${norm.x_center} ${norm.y_center} ${norm.width} ${norm.height}`;

  if (baseBbox) {
    // Convert base corners to keypoints (TL, TR, BR, BL)
    const corners = [
      { x: baseBbox.x, y: baseBbox.y },                                  // TL
      { x: baseBbox.x + baseBbox.width, y: baseBbox.y },                 // TR
      { x: baseBbox.x + baseBbox.width, y: baseBbox.y + baseBbox.height }, // BR
      { x: baseBbox.x, y: baseBbox.y + baseBbox.height }                 // BL
    ];

    for (const corner of corners) {
      const kpt = normalizeKeypoint(corner, imageWidth, imageHeight);
      line += ` ${kpt.x} ${kpt.y} 1`; // visibility=1
    }
  }

  return line + '\n';
}
```

#### 6. Skipped Images
**Question**: How do we handle skipped images (no miniatures)?

**Recommendation**: Export empty .txt file
- YOLO treats empty labels as "no objects in image"
- Valid for negative samples (images without miniatures)
- Prevents training errors from missing label files

**Implementation**:
```typescript
// In exportToYOLO()
if (annotation.annotations.length === 0) {
  // Create empty .txt file (valid for skipped/empty images)
  await fs.writeFile(labelPath, '');
} else {
  // Write annotations
  const lines = annotation.annotations.map(bbox => exportInstance(...));
  await fs.writeFile(labelPath, lines.join(''));
}
```

---

## Implementation Plan (Ordered by Priority)

### Phase 1: Correctness Infrastructure (MUST HAVE)
**Goal**: Prevent bad data from entering training pipeline

#### 1. YOLO-Pose Export Validator
**Effort**: 4-5 hours
**Impact**: Critical - prevents training on garbage

Validates exported dataset before training:

**Checks:**
```typescript
interface ValidationError {
  severity: 'error' | 'warning';
  file: string;
  line?: number;
  message: string;
}

class YoloPoseValidator {

  // 1. Label file structure
  validateLabelFile(path: string): ValidationError[] {
    const errors: ValidationError[] = [];
    const lines = readLines(path);

    for (const [lineNum, line] of lines.entries()) {
      const parts = line.split(' ');

      // Standard bbox: class x y w h (5 values)
      // With pose: class x y w h x1 y1 v1 x2 y2 v2 x3 y3 v3 x4 y4 v4 (17 values)

      if (parts.length !== 5 && parts.length !== 17) {
        errors.push({
          severity: 'error',
          file: path,
          line: lineNum + 1,
          message: `Invalid format: expected 5 (bbox) or 17 (bbox+pose) values, got ${parts.length}`
        });
        continue;
      }

      // Validate class ID
      const classId = parseInt(parts[0]);
      if (classId !== 0) {  // Single class: only 0 allowed
        errors.push({
          severity: 'error',
          file: path,
          line: lineNum + 1,
          message: `Invalid class ID: ${classId} (only 0 allowed for single-class)`
        });
      }

      // Validate bbox (normalized 0-1)
      const [x, y, w, h] = parts.slice(1, 5).map(Number);

      if (x < 0 || x > 1 || y < 0 || y > 1) {
        errors.push({
          severity: 'error',
          file: path,
          line: lineNum + 1,
          message: `Bbox center out of range: x=${x.toFixed(3)}, y=${y.toFixed(3)} (must be 0-1)`
        });
      }

      if (w <= 0 || w > 1 || h <= 0 || h > 1) {
        errors.push({
          severity: 'error',
          file: path,
          line: lineNum + 1,
          message: `Bbox size invalid: w=${w.toFixed(3)}, h=${h.toFixed(3)} (must be 0-1, >0)`
        });
      }

      // Validate keypoints (if present)
      if (parts.length === 17) {
        const keypoints = parts.slice(5);

        for (let i = 0; i < 4; i++) {
          const kx = Number(keypoints[i * 3]);
          const ky = Number(keypoints[i * 3 + 1]);
          const kv = Number(keypoints[i * 3 + 2]);

          // Check coordinates in range
          if (kx < 0 || kx > 1 || ky < 0 || ky > 1) {
            errors.push({
              severity: 'error',
              file: path,
              line: lineNum + 1,
              message: `Keypoint ${i} out of range: (${kx.toFixed(3)}, ${ky.toFixed(3)})`
            });
          }

          // Check visibility flag (must be 0 or 1)
          if (kv !== 0 && kv !== 1) {
            errors.push({
              severity: 'error',
              file: path,
              line: lineNum + 1,
              message: `Keypoint ${i} invalid visibility: ${kv} (must be 0 or 1)`
            });
          }
        }

        // Check keypoint ordering (TL → TR → BR → BL should form valid rectangle)
        // This catches copy-paste errors and ensures clockwise order
        const corners = [
          { x: Number(keypoints[0]), y: Number(keypoints[1]) },  // TL
          { x: Number(keypoints[3]), y: Number(keypoints[4]) },  // TR
          { x: Number(keypoints[6]), y: Number(keypoints[7]) },  // BR
          { x: Number(keypoints[9]), y: Number(keypoints[10]) }  // BL
        ];

        // TL should be top-left (x smallest, y smallest)
        // TR should be top-right (x largest, y smallest)
        // etc.
        if (!isValidRectangleOrder(corners)) {
          errors.push({
            severity: 'warning',
            file: path,
            line: lineNum + 1,
            message: `Keypoint order suspicious (expected TL→TR→BR→BL clockwise)`
          });
        }
      }
    }

    // Check for overlapping instances (clustered miniatures warning)
    const bboxes = lines.map(line => {
      const parts = line.trim().split(' ');
      if (parts.length < 5) return null;
      const [cls, x, y, w, h] = parts.slice(0, 5).map(Number);
      return { x, y, w, h };
    }).filter(b => b !== null);

    for (let i = 0; i < bboxes.length; i++) {
      for (let j = i + 1; j < bboxes.length; j++) {
        const iou = calculateIoU(bboxes[i]!, bboxes[j]!);
        if (iou > 0.5) {  // >50% overlap = warning for clustered minis
          errors.push({
            severity: 'warning',
            file: path,
            line: null,
            message: `High overlap (${(iou * 100).toFixed(0)}%) between instances ${i+1} and ${j+1} - verify not duplicate`
          });
        }
      }
    }

    return errors;
  }

  // Helper: Calculate IoU for normalized bboxes
  private calculateIoU(a: {x: number, y: number, w: number, h: number},
                       b: {x: number, y: number, w: number, h: number}): number {
    // Convert center+size to corners
    const a_x1 = a.x - a.w / 2;
    const a_y1 = a.y - a.h / 2;
    const a_x2 = a.x + a.w / 2;
    const a_y2 = a.y + a.h / 2;

    const b_x1 = b.x - b.w / 2;
    const b_y1 = b.y - b.h / 2;
    const b_x2 = b.x + b.w / 2;
    const b_y2 = b.y + b.h / 2;

    // Calculate intersection
    const x1 = Math.max(a_x1, b_x1);
    const y1 = Math.max(a_y1, b_y1);
    const x2 = Math.min(a_x2, b_x2);
    const y2 = Math.min(a_y2, b_y2);

    if (x2 < x1 || y2 < y1) return 0;  // No overlap

    const intersection = (x2 - x1) * (y2 - y1);
    const areaA = a.w * a.h;
    const areaB = b.w * b.h;
    const union = areaA + areaB - intersection;

    return intersection / union;
  }

  // 2. Image-label pairing
  validatePairing(imagesDir: string, labelsDir: string): ValidationError[] {
    const errors: ValidationError[] = [];

    const imageFiles = getFiles(imagesDir);
    const labelFiles = getFiles(labelsDir);

    const imageStems = new Set(imageFiles.map(f => stem(f)));
    const labelStems = new Set(labelFiles.map(f => stem(f)));

    // Check for missing labels
    for (const imageStem of imageStems) {
      if (!labelStems.has(imageStem)) {
        errors.push({
          severity: 'error',
          file: `${imageStem}.*`,
          message: 'Image has no corresponding label file'
        });
      }
    }

    // Check for orphaned labels
    for (const labelStem of labelStems) {
      if (!imageStems.has(labelStem)) {
        errors.push({
          severity: 'warning',
          file: `${labelStem}.txt`,
          message: 'Label has no corresponding image'
        });
      }
    }

    return errors;
  }

  // 3. data.yaml validation
  validateDataYaml(path: string): ValidationError[] {
    const errors: ValidationError[] = [];
    const data = yaml.parse(readFile(path));

    // Required fields
    const required = ['train', 'val', 'nc', 'names', 'kpt_shape'];
    for (const field of required) {
      if (!(field in data)) {
        errors.push({
          severity: 'error',
          file: 'data.yaml',
          message: `Missing required field: ${field}`
        });
      }
    }

    // Validate kpt_shape for pose
    if (data.kpt_shape) {
      const [nKpts, nValues] = data.kpt_shape;
      if (nKpts !== 4 || nValues !== 3) {
        errors.push({
          severity: 'error',
          file: 'data.yaml',
          message: `Invalid kpt_shape: [${nKpts}, ${nValues}] (expected [4, 3] for base corners)`
        });
      }
    }

    // Validate class count matches names
    if (data.nc !== data.names.length) {
      errors.push({
        severity: 'error',
        file: 'data.yaml',
        message: `Class count mismatch: nc=${data.nc} but ${data.names.length} names provided`
      });
    }

    return errors;
  }
}
```

**Validation script** (`scripts/validate_yolo_dataset.py`):
```python
#!/usr/bin/env python3
"""Validate YOLO-pose dataset before training"""

import sys
from pathlib import Path
import yaml

def validate_dataset(dataset_path):
    dataset_path = Path(dataset_path)
    errors = []
    warnings = []

    # 1. Check structure
    required_dirs = [
        'images/train', 'images/val',
        'labels/train', 'labels/val'
    ]
    for dir_name in required_dirs:
        if not (dataset_path / dir_name).exists():
            errors.append(f"Missing directory: {dir_name}")

    if errors:
        print_report(errors, warnings)
        return False

    # 2. Validate data.yaml
    yaml_path = dataset_path / 'data.yaml'
    if not yaml_path.exists():
        errors.append("Missing data.yaml")
    else:
        with open(yaml_path) as f:
            config = yaml.safe_load(f)

        # Check kpt_shape
        if config.get('kpt_shape') != [4, 3]:
            errors.append(f"Invalid kpt_shape: {config.get('kpt_shape')} (expected [4, 3])")

        # Check single class
        if config.get('nc') != 1:
            warnings.append(f"Multi-class detected: nc={config.get('nc')} (expected 1 for 'miniature')")

    # 3. Validate labels
    for split in ['train', 'val']:
        label_dir = dataset_path / 'labels' / split
        for label_file in label_dir.glob('*.txt'):
            with open(label_file) as f:
                for line_num, line in enumerate(f, 1):
                    parts = line.strip().split()

                    # Check format
                    if len(parts) not in [5, 17]:
                        errors.append(
                            f"{split}/{label_file.name}:{line_num} - "
                            f"Invalid format ({len(parts)} values, expected 5 or 17)"
                        )
                        continue

                    # Check class
                    if int(parts[0]) != 0:
                        errors.append(
                            f"{split}/{label_file.name}:{line_num} - "
                            f"Invalid class {parts[0]} (expected 0)"
                        )

                    # Check bbox bounds
                    bbox = [float(x) for x in parts[1:5]]
                    for i, val in enumerate(bbox):
                        if val < 0 or val > 1:
                            errors.append(
                                f"{split}/{label_file.name}:{line_num} - "
                                f"Bbox value out of range: {val}"
                            )

                    # Check keypoints (if present)
                    if len(parts) == 17:
                        kpts = [float(x) for x in parts[5:]]
                        for i in range(4):
                            kx, ky, kv = kpts[i*3:(i+1)*3]

                            # Check coordinates
                            if kx < 0 or kx > 1 or ky < 0 or ky > 1:
                                errors.append(
                                    f"{split}/{label_file.name}:{line_num} - "
                                    f"Keypoint {i} out of range: ({kx}, {ky})"
                                )

                            # Check visibility
                            if kv not in [0, 1]:
                                errors.append(
                                    f"{split}/{label_file.name}:{line_num} - "
                                    f"Keypoint {i} invalid visibility: {kv}"
                                )

    print_report(errors, warnings)
    return len(errors) == 0

def print_report(errors, warnings):
    print("=" * 60)
    if errors:
        print(f"❌ {len(errors)} ERRORS:")
        for err in errors[:20]:
            print(f"  • {err}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")

    if warnings:
        print(f"\n⚠️  {len(warnings)} WARNINGS:")
        for warn in warnings[:20]:
            print(f"  • {warn}")

    if not errors and not warnings:
        print("✅ Dataset validation passed!")
    elif not errors:
        print("\n✅ No errors (warnings can usually be ignored)")
    else:
        print("\n❌ Fix errors before training")
    print("=" * 60)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python validate_yolo_dataset.py <dataset_path>")
        sys.exit(1)

    success = validate_dataset(sys.argv[1])
    sys.exit(0 if success else 1)
```

---

#### 2. Real-Time Quality Checks
**Effort**: 3-4 hours
**Impact**: High - catches errors during annotation

Add quality validation when saving annotations:

**Backend** (`annotationService.ts`):
```typescript
interface QualityIssue {
  type: 'error' | 'warning';
  code: 'BASE_OUTSIDE_MODEL' | 'BBOX_OUT_OF_BOUNDS' | 'BBOX_TOO_SMALL' | 'DUPLICATE_BOX';
  message: string;
  bboxId?: string;
}

async validateAnnotation(annotation: ImageAnnotation): Promise<QualityIssue[]> {
  const issues: QualityIssue[] = [];

  // Get image dimensions
  const metadata = await sharp(annotation.imagePath).metadata();
  const imgWidth = metadata.width!;
  const imgHeight = metadata.height!;

  for (const bbox of annotation.annotations) {

    // 1. Check bbox is within image bounds
    if (bbox.x < 0 || bbox.y < 0 ||
        bbox.x + bbox.width > imgWidth ||
        bbox.y + bbox.height > imgHeight) {
      issues.push({
        type: 'error',
        code: 'BBOX_OUT_OF_BOUNDS',
        message: `Model bbox extends beyond image (${bbox.x},${bbox.y} ${bbox.width}x${bbox.height})`,
        bboxId: bbox.id
      });
    }

    // 2. Check minimum size (avoid tiny accidental boxes)
    if (bbox.width < 10 || bbox.height < 10) {
      issues.push({
        type: 'warning',
        code: 'BBOX_TOO_SMALL',
        message: `Model bbox very small (${bbox.width}x${bbox.height}px)`,
        bboxId: bbox.id
      });
    }

    // 3. If base bbox exists, check it's inside model bbox
    if (bbox.baseBbox) {
      const base = bbox.baseBbox;
      const modelBounds = {
        x1: bbox.x,
        y1: bbox.y,
        x2: bbox.x + bbox.width,
        y2: bbox.y + bbox.height
      };

      const baseBounds = {
        x1: base.x,
        y1: base.y,
        x2: base.x + base.width,
        y2: base.y + base.height
      };

      // Check all corners of base are inside model
      if (baseBounds.x1 < modelBounds.x1 ||
          baseBounds.y1 < modelBounds.y1 ||
          baseBounds.x2 > modelBounds.x2 ||
          baseBounds.y2 > modelBounds.y2) {
        issues.push({
          type: 'error',
          code: 'BASE_OUTSIDE_MODEL',
          message: 'Base bbox extends outside model bbox',
          bboxId: bbox.id
        });
      }
    }
  }

  // 4. Check for duplicate/overlapping boxes
  for (let i = 0; i < annotation.annotations.length; i++) {
    for (let j = i + 1; j < annotation.annotations.length; j++) {
      const iou = calculateIoU(
        annotation.annotations[i],
        annotation.annotations[j]
      );

      if (iou > 0.9) {  // 90%+ overlap = likely duplicate
        issues.push({
          type: 'warning',
          code: 'DUPLICATE_BOX',
          message: `High overlap (${(iou * 100).toFixed(0)}%) between boxes`,
          bboxId: annotation.annotations[i].id
        });
      }
    }
  }

  return issues;
}

// Modify save endpoint to return quality issues
app.post('/api/annotate/save', async (req, res) => {
  const annotation = req.body;

  // Validate
  const issues = await annotationService.validateAnnotation(annotation);

  // Block on errors, warn on warnings
  const errors = issues.filter(i => i.type === 'error');
  const warnings = issues.filter(i => i.type === 'warning');

  if (errors.length > 0) {
    return res.status(400).json({
      success: false,
      errors,
      warnings,
      message: 'Cannot save: annotation has errors'
    });
  }

  // Save annotation
  await annotationService.saveAnnotation(annotation);

  res.json({
    success: true,
    warnings,  // Return warnings but allow save
    message: 'Annotation saved'
  });
});
```

**Frontend** (`AnnotationInterface.tsx`):
```typescript
const saveAnnotations = async () => {
  setSaving(true);

  try {
    const response = await fetch('/api/annotate/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        imageId: currentImage.imageId,
        imagePath: currentImage.path,
        faction: currentImage.faction,
        source: currentImage.source,
        annotations: annotations
      })
    });

    const data = await response.json();

    if (!response.ok) {
      // Show errors
      setMessage({
        type: 'error',
        text: `Cannot save: ${data.errors.map(e => e.message).join(', ')}`
      });
      return;
    }

    // Show warnings if any
    if (data.warnings && data.warnings.length > 0) {
      setMessage({
        type: 'warning',
        text: `Saved with warnings: ${data.warnings.map(w => w.message).join(', ')}`
      });
    } else {
      setMessage({ type: 'success', text: 'Saved successfully' });
    }

    // Load next image
    await loadNextImage();

  } catch (error) {
    setMessage({ type: 'error', text: 'Failed to save' });
  } finally {
    setSaving(false);
  }
};
```

---

#### 2a. Quality Issues UI Modal
**Effort**: 1-2 hours
**Impact**: High - helps users fix errors quickly

Display quality issues in a modal with actionable "Fix" buttons:

**Frontend** (`QualityIssuesModal.tsx`):
```typescript
interface QualityIssue {
  type: 'error' | 'warning';
  code: string;
  message: string;
  bboxId?: string;
}

const QualityIssuesModal: React.FC<{
  issues: QualityIssue[];
  onClose: () => void;
  onFixBbox: (bboxId: string) => void;
}> = ({ issues, onClose, onFixBbox }) => {
  const errors = issues.filter(i => i.type === 'error');
  const warnings = issues.filter(i => i.type === 'warning');

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <h2>Annotation Quality Issues</h2>

        {errors.length > 0 && (
          <div className="errors-section">
            <h3>❌ Errors (must fix to save)</h3>
            {errors.map((error, idx) => (
              <div key={idx} className="issue-item error">
                <div className="issue-message">{error.message}</div>
                {error.bboxId && (
                  <button
                    className="fix-button"
                    onClick={() => {
                      onFixBbox(error.bboxId!);
                      onClose();
                    }}
                  >
                    Fix
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {warnings.length > 0 && (
          <div className="warnings-section">
            <h3>⚠️ Warnings (can save, but review recommended)</h3>
            {warnings.map((warning, idx) => (
              <div key={idx} className="issue-item warning">
                <div className="issue-message">{warning.message}</div>
                {warning.bboxId && (
                  <button
                    className="fix-button"
                    onClick={() => {
                      onFixBbox(warning.bboxId!);
                      onClose();
                    }}
                  >
                    Review
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="modal-actions">
          {errors.length === 0 && (
            <button className="save-anyway" onClick={onClose}>
              Save Anyway
            </button>
          )}
          <button className="close" onClick={onClose}>
            {errors.length > 0 ? 'Cancel' : 'Close'}
          </button>
        </div>
      </div>
    </div>
  );
};

// In AnnotationInterface.tsx
const [qualityIssues, setQualityIssues] = useState<QualityIssue[]>([]);
const [showIssuesModal, setShowIssuesModal] = useState(false);

const saveAnnotations = async () => {
  // ... save logic

  if (!response.ok) {
    // Show issues in modal instead of text message
    setQualityIssues([...data.errors, ...data.warnings]);
    setShowIssuesModal(true);
    return;
  }

  // ... success logic
};

const handleFixBbox = (bboxId: string) => {
  // Select and highlight the problematic bbox
  setSelectedAnnotation(bboxId);
  // Optionally zoom to it
  const bbox = annotations.find(a => a.id === bboxId);
  if (bbox) {
    zoomToBbox(bbox);
  }
};

return (
  <>
    {/* ... existing UI ... */}

    {showIssuesModal && (
      <QualityIssuesModal
        issues={qualityIssues}
        onClose={() => setShowIssuesModal(false)}
        onFixBbox={handleFixBbox}
      />
    )}
  </>
);
```

---

#### 2b. Pre-Export Validation Endpoint
**Effort**: 1 hour
**Impact**: Medium - prevents wasted export time

Add validation check before running full export:

**Backend** (`index.ts`):
```typescript
app.post('/api/annotate/validate-export', async (req, res) => {
  try {
    const issues: QualityIssue[] = [];

    // Load all annotations
    const annotations = await annotationService.getAllAnnotations();

    // Run quality checks on each
    for (const annotation of annotations) {
      const annotationIssues = await annotationService.validateAnnotation(annotation);
      issues.push(...annotationIssues.map(issue => ({
        ...issue,
        imageId: annotation.imageId
      })));
    }

    // Count errors vs warnings
    const errors = issues.filter(i => i.type === 'error');
    const warnings = issues.filter(i => i.type === 'warning');

    res.json({
      success: errors.length === 0,
      totalAnnotations: annotations.length,
      errors: errors.length,
      warnings: warnings.length,
      issues: issues.slice(0, 100),  // Return first 100 for preview
      message: errors.length === 0
        ? 'Ready to export'
        : `Found ${errors.length} errors - fix before exporting`
    });

  } catch (error) {
    res.status(500).json({ error: 'Validation failed' });
  }
});

// Modify export endpoint to run validation first
app.post('/api/annotate/export', async (req, res) => {
  // Run validation
  const validationResponse = await fetch('/api/annotate/validate-export');
  const validation = await validationResponse.json();

  if (!validation.success) {
    return res.status(400).json({
      error: 'Cannot export: dataset has quality errors',
      errors: validation.errors,
      warnings: validation.warnings
    });
  }

  // Proceed with export
  const { outputDir, trainSplit } = req.body;
  await annotationService.exportToYOLO(outputDir, trainSplit);

  res.json({
    success: true,
    message: 'Export complete',
    warnings: validation.warnings
  });
});
```

**Usage**:
```bash
# Check before exporting
curl -X POST http://localhost:3001/api/annotate/validate-export

# Only export if validation passes
curl -X POST http://localhost:3001/api/annotate/export \
  -H "Content-Type: application/json" \
  -d '{"outputDir": "backend/yolo_dataset", "trainSplit": 0.8}'
```

---

### Phase 2: Throughput Boosters (HIGH PRIORITY)
**Goal**: Make annotation faster and less frustrating

#### 3. Zoom & Pan (Centralized Transforms)
**Effort**: 4-5 hours
**Impact**: Critical for precision

**Key principles:**
- **One source of truth** for coordinate conversion
- **Space+drag** for panning (trackpad-friendly)
- **Clamp viewport** to prevent flinging image into void

**Implementation** (`BboxAnnotator.tsx`):
```typescript
interface Viewport {
  zoom: number;    // 0.5 to 5.0
  offsetX: number;
  offsetY: number;
}

const [viewport, setViewport] = useState<Viewport>({
  zoom: 1.0,
  offsetX: 0,
  offsetY: 0
});

// SINGLE SOURCE OF TRUTH for coordinate conversion
const toImageCoords = (screenX: number, screenY: number) => {
  const rect = canvasRef.current!.getBoundingClientRect();
  const canvasX = screenX - rect.left;
  const canvasY = screenY - rect.top;

  return {
    x: (canvasX - viewport.offsetX) / viewport.zoom,
    y: (canvasY - viewport.offsetY) / viewport.zoom
  };
};

const toScreenCoords = (imageX: number, imageY: number) => {
  return {
    x: imageX * viewport.zoom + viewport.offsetX,
    y: imageY * viewport.zoom + viewport.offsetY
  };
};

// Mouse wheel zoom (toward cursor)
const handleWheel = (e: React.WheelEvent) => {
  e.preventDefault();

  const delta = e.deltaY > 0 ? 0.9 : 1.1;
  const newZoom = Math.max(0.5, Math.min(5.0, viewport.zoom * delta));

  // Zoom toward cursor position
  const rect = canvasRef.current!.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;

  const zoomRatio = newZoom / viewport.zoom;
  const newOffsetX = mouseX - (mouseX - viewport.offsetX) * zoomRatio;
  const newOffsetY = mouseY - (mouseY - viewport.offsetY) * zoomRatio;

  // Clamp offsets to prevent flinging image away
  const canvas = canvasRef.current!;
  const maxOffsetX = canvas.width * 0.5;
  const maxOffsetY = canvas.height * 0.5;
  const minOffsetX = -canvas.width * (newZoom - 0.5);
  const minOffsetY = -canvas.height * (newZoom - 0.5);

  setViewport({
    zoom: newZoom,
    offsetX: Math.max(minOffsetX, Math.min(maxOffsetX, newOffsetX)),
    offsetY: Math.max(minOffsetY, Math.min(maxOffsetY, newOffsetY))
  });
};

// Panning with Space+drag OR middle-click
const [isPanning, setIsPanning] = useState(false);
const [panStart, setPanStart] = useState({ x: 0, y: 0 });
const [spacePressed, setSpacePressed] = useState(false);

useEffect(() => {
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.code === 'Space' && !spacePressed) {
      setSpacePressed(true);
      e.preventDefault();
    }
  };

  const handleKeyUp = (e: KeyboardEvent) => {
    if (e.code === 'Space') {
      setSpacePressed(false);
      setIsPanning(false);
    }
  };

  window.addEventListener('keydown', handleKeyDown);
  window.addEventListener('keyup', handleKeyUp);

  return () => {
    window.removeEventListener('keydown', handleKeyDown);
    window.removeEventListener('keyup', handleKeyUp);
  };
}, [spacePressed]);

const handleMouseDown = (e: React.MouseEvent) => {
  // Pan with middle-click OR Space+left-click
  if (e.button === 1 || (e.button === 0 && spacePressed)) {
    e.preventDefault();
    setIsPanning(true);
    setPanStart({ x: e.clientX, y: e.clientY });
    return;
  }

  // Normal bbox drawing (if not panning)
  if (!isPanning && !spacePressed) {
    const imageCoords = toImageCoords(e.clientX, e.clientY);
    // ... bbox drawing logic using imageCoords
  }
};

const handleMouseMove = (e: React.MouseEvent) => {
  if (isPanning) {
    const dx = e.clientX - panStart.x;
    const dy = e.clientY - panStart.y;

    setViewport(prev => ({
      ...prev,
      offsetX: prev.offsetX + dx,
      offsetY: prev.offsetY + dy
    }));

    setPanStart({ x: e.clientX, y: e.clientY });
    redrawCanvas();
    return;
  }

  // Normal bbox drawing
  if (isDrawing) {
    const imageCoords = toImageCoords(e.clientX, e.clientY);
    // ... bbox drawing logic using imageCoords
  }
};

// Drawing with viewport transform
const redrawCanvas = () => {
  const canvas = canvasRef.current!;
  const ctx = canvas.getContext('2d')!;

  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Apply viewport transform
  ctx.save();
  ctx.translate(viewport.offsetX, viewport.offsetY);
  ctx.scale(viewport.zoom, viewport.zoom);

  // Draw image
  if (imageElement) {
    ctx.drawImage(imageElement, 0, 0, imageWidth, imageHeight);
  }

  // Draw bboxes (all coordinates already in image space)
  for (const bbox of annotations) {
    drawBbox(ctx, bbox);
  }

  ctx.restore();
};

// Reset zoom/pan (R key)
useEffect(() => {
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.code === 'KeyR') {
      setViewport({ zoom: 1.0, offsetX: 0, offsetY: 0 });
      redrawCanvas();
    }
  };

  window.addEventListener('keydown', handleKeyDown);
  return () => window.removeEventListener('keydown', handleKeyDown);
}, []);
```

**UI indicators:**
- Zoom percentage in corner: `100%` / `200%` / etc.
- Panning cursor when Space held
- "R to reset zoom" hint

---

#### 4. Undo/Redo (Command Pattern)
**Effort**: 3-4 hours
**Impact**: High - reduces frustration

**Key principles:**
- Save history only on **committed actions** (not mousemove)
- Use **command pattern** (not full state snapshots if annotations grow large)
- **Reset history** on image change

**Implementation** (`BboxAnnotator.tsx`):
```typescript
// Command interface
interface Command {
  type: 'ADD_BBOX' | 'DELETE_BBOX' | 'UPDATE_LABEL' | 'ADD_BASE' | 'DELETE_BASE';
  execute: () => void;
  undo: () => void;
}

// Command implementations
class AddBboxCommand implements Command {
  type = 'ADD_BBOX' as const;

  constructor(
    private bbox: BboxAnnotation,
    private addFn: (bbox: BboxAnnotation) => void,
    private removeFn: (id: string) => void
  ) {}

  execute() { this.addFn(this.bbox); }
  undo() { this.removeFn(this.bbox.id); }
}

class DeleteBboxCommand implements Command {
  type = 'DELETE_BBOX' as const;

  constructor(
    private bbox: BboxAnnotation,
    private addFn: (bbox: BboxAnnotation) => void,
    private removeFn: (id: string) => void
  ) {}

  execute() { this.removeFn(this.bbox.id); }
  undo() { this.addFn(this.bbox); }
}

// History manager
const [commandHistory, setCommandHistory] = useState<Command[]>([]);
const [historyIndex, setHistoryIndex] = useState(-1);

const executeCommand = (command: Command) => {
  command.execute();

  // Trim future history if we're not at the end
  const newHistory = commandHistory.slice(0, historyIndex + 1);
  newHistory.push(command);

  // Limit to 50 commands
  if (newHistory.length > 50) {
    newHistory.shift();
  }

  setCommandHistory(newHistory);
  setHistoryIndex(newHistory.length - 1);
};

const undo = () => {
  if (historyIndex >= 0) {
    const command = commandHistory[historyIndex];
    command.undo();
    setHistoryIndex(historyIndex - 1);
    redrawCanvas();
  }
};

const redo = () => {
  if (historyIndex < commandHistory.length - 1) {
    const command = commandHistory[historyIndex + 1];
    command.execute();
    setHistoryIndex(historyIndex + 1);
    redrawCanvas();
  }
};

// Keyboard shortcuts
useEffect(() => {
  const handleKeyDown = (e: KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'z') {
      e.preventDefault();
      if (e.shiftKey) {
        redo();
      } else {
        undo();
      }
    }
  };

  window.addEventListener('keydown', handleKeyDown);
  return () => window.removeEventListener('keydown', handleKeyDown);
}, [historyIndex, commandHistory]);

// Reset history on image change
useEffect(() => {
  setCommandHistory([]);
  setHistoryIndex(-1);
}, [currentImage?.imageId]);

// Modify bbox creation to use commands
const handleMouseUp = (e: React.MouseEvent) => {
  if (!isDrawing) return;

  setIsDrawing(false);

  const imageCoords = toImageCoords(e.clientX, e.clientY);
  const width = Math.abs(imageCoords.x - drawStart.x);
  const height = Math.abs(imageCoords.y - drawStart.y);

  // Minimum size check
  if (width < 10 || height < 10) {
    setMessage({ type: 'warning', text: 'Box too small (min 10px)' });
    return;
  }

  const newBbox: BboxAnnotation = {
    id: crypto.randomUUID(),
    x: Math.min(drawStart.x, imageCoords.x),
    y: Math.min(drawStart.y, imageCoords.y),
    width,
    height,
    classLabel: 'miniature'
  };

  // Execute command (adds to history automatically)
  executeCommand(new AddBboxCommand(
    newBbox,
    (bbox) => setAnnotations(prev => [...prev, bbox]),
    (id) => setAnnotations(prev => prev.filter(a => a.id !== id))
  ));
};

// Modify delete to use commands
const handleDelete = () => {
  if (!selectedAnnotation) return;

  const bbox = annotations.find(a => a.id === selectedAnnotation);
  if (!bbox) return;

  executeCommand(new DeleteBboxCommand(
    bbox,
    (bbox) => setAnnotations(prev => [...prev, bbox]),
    (id) => setAnnotations(prev => prev.filter(a => a.id !== id))
  ));

  setSelectedAnnotation(null);
};
```

---

#### 4a. Auto-Constrain Base Bbox
**Effort**: 1 hour
**Impact**: High - prevents base-outside-model errors

Automatically constrain base bbox drawing to stay within parent model bbox:

**Implementation** (`BboxAnnotator.tsx`):
```typescript
// In Base mode, constrain drawing to selected model bbox
const handleMouseMove = (e: React.MouseEvent) => {
  if (isPanning) {
    // ... panning logic
    return;
  }

  if (isDrawing) {
    const imageCoords = toImageCoords(e.clientX, e.clientY);

    // If in Base mode, constrain to parent model bbox
    if (mode === 'base' && selectedAnnotation) {
      const parentBbox = annotations.find(a => a.id === selectedAnnotation);
      if (parentBbox) {
        // Clamp coordinates to model bbox bounds
        imageCoords.x = Math.max(
          parentBbox.x,
          Math.min(parentBbox.x + parentBbox.width, imageCoords.x)
        );
        imageCoords.y = Math.max(
          parentBbox.y,
          Math.min(parentBbox.y + parentBbox.height, imageCoords.y)
        );
      }
    }

    // Update current drawing box
    setCurrentDraw({
      x: Math.min(drawStart.x, imageCoords.x),
      y: Math.min(drawStart.y, imageCoords.y),
      width: Math.abs(imageCoords.x - drawStart.x),
      height: Math.abs(imageCoords.y - drawStart.y)
    });

    redrawCanvas();
  }
};

// Also constrain on mouse up
const handleMouseUp = (e: React.MouseEvent) => {
  if (!isDrawing) return;

  setIsDrawing(false);
  const imageCoords = toImageCoords(e.clientX, e.clientY);

  // Constrain if in Base mode
  if (mode === 'base' && selectedAnnotation) {
    const parentBbox = annotations.find(a => a.id === selectedAnnotation);
    if (parentBbox) {
      imageCoords.x = Math.max(
        parentBbox.x,
        Math.min(parentBbox.x + parentBbox.width, imageCoords.x)
      );
      imageCoords.y = Math.max(
        parentBbox.y,
        Math.min(parentBbox.y + parentBbox.height, imageCoords.y)
      );
    }
  }

  // Create bbox
  const width = Math.abs(imageCoords.x - drawStart.x);
  const height = Math.abs(imageCoords.y - drawStart.y);

  if (width < 10 || height < 10) {
    setMessage({ type: 'warning', text: 'Box too small (min 10px)' });
    return;
  }

  // ... rest of bbox creation logic
};
```

**Visual feedback**:
- Show model bbox outline in brighter color when in Base mode
- Display "Drawing constrained to model bounds" message
- Cursor changes to "not-allowed" at model bbox edges

**Benefits**:
- Prevents BASE_OUTSIDE_MODEL quality errors entirely
- Makes annotation faster (no need to carefully stay inside)
- Intuitive UX (can't accidentally draw outside)

---

### Phase 3: Training Pipeline (BEFORE ANNOTATION COMPLETE)
**Goal**: Be ready to train the moment annotations are done

#### 5. Training Environment Setup
**Effort**: 2-3 hours
**Impact**: High - removes friction

**Setup script** (`scripts/setup_yolo_training.sh`):
```bash
#!/bin/bash

echo "Setting up YOLO training environment..."

# Create structure
mkdir -p yolo_training/{models,runs,configs}

# Create virtual environment
python3 -m venv yolo_training/venv
source yolo_training/venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install ultralytics opencv-python matplotlib tensorboard

# Download pre-trained models
cd yolo_training/models
python -c "
from ultralytics import YOLO
for size in ['n', 's', 'm']:
    print(f'Downloading yolov8{size}-pose.pt...')
    YOLO(f'yolov8{size}-pose.pt')
"
cd ../..

echo "✅ Training environment ready!"
echo ""
echo "Next steps:"
echo "1. Export annotations: curl -X POST http://localhost:3001/api/annotate/export"
echo "2. Validate dataset: python scripts/validate_yolo_dataset.py backend/yolo_dataset"
echo "3. Train: source yolo_training/venv/bin/activate && yolo pose train data=backend/yolo_dataset/data.yaml model=yolov8m-pose.pt"
```

**Training config** (`yolo_training/configs/production.yaml`):
```yaml
# Production training config
task: pose
mode: train

data: ../../backend/yolo_dataset/data.yaml
model: yolov8m-pose.pt

epochs: 150
batch: 16
imgsz: 640

# Optimizer
optimizer: AdamW
lr0: 0.001
lrf: 0.01

# Augmentation (conservative for miniatures)
hsv_h: 0.015
hsv_s: 0.7
hsv_v: 0.4
degrees: 0.0      # Don't rotate (miniatures should be upright)
translate: 0.1
scale: 0.5
flipud: 0.0       # Don't flip upside-down
fliplr: 0.5       # Can flip left-right

# Early stopping
patience: 30

# Output
project: runs/production
name: warhammer_v1
save: true
save_period: 10
```

**Quick test config** (`yolo_training/configs/quick_test.yaml`):
```yaml
# 5-minute test to verify everything works
task: pose
mode: train

data: ../../backend/yolo_dataset/data.yaml
model: yolov8n-pose.pt  # Fastest

epochs: 5
batch: 4
imgsz: 416

patience: 3

project: runs/test
name: quick_test
```

---

#### 6. Model Testing Harness
**Effort**: 2-3 hours
**Impact**: Medium - useful for evaluation

**Test script** (`scripts/test_model.py`):
```python
#!/usr/bin/env python3
"""Test trained YOLO model on images"""

import argparse
from pathlib import Path
from ultralytics import YOLO
import cv2

def test_model(model_path, test_images, output_dir, conf=0.25):
    model = YOLO(model_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for img_path in test_images:
        img_path = Path(img_path)
        print(f"Testing {img_path.name}...")

        results = model.predict(
            source=str(img_path),
            conf=conf,
            save=False
        )

        result = results[0]
        annotated = result.plot()

        output_path = output_dir / f"result_{img_path.name}"
        cv2.imwrite(str(output_path), annotated)

        print(f"  Detections: {len(result.boxes)}")
        print(f"  Saved to: {output_path}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('model', help='Path to .pt model')
    parser.add_argument('images', nargs='+', help='Test images')
    parser.add_argument('--output', default='test_results')
    parser.add_argument('--conf', type=float, default=0.25)
    args = parser.parse_args()

    test_model(args.model, args.images, args.output, args.conf)
```

---

## Testing & Quality Assurance

### Unit Tests for Validators
**Effort**: 2-3 hours
**Critical for correctness**

Create test suite for validation logic:

**Test file** (`backend/src/services/__tests__/annotationService.test.ts`):
```typescript
import { describe, test, expect } from '@jest/globals';
import { AnnotationService } from '../annotationService';

describe('AnnotationService - Quality Validation', () => {
  const service = new AnnotationService();

  test('should reject base bbox outside model bbox', async () => {
    const annotation = {
      imageId: 'test',
      imagePath: '/test/image.jpg',
      faction: 'tyranids',
      source: 'reddit',
      annotations: [{
        id: '1',
        x: 100,
        y: 100,
        width: 100,
        height: 100,
        classLabel: 'miniature',
        baseBbox: {
          x: 150,  // Inside
          y: 150,  // Inside
          width: 100,  // Extends past x=200 (outside!)
          height: 50
        }
      }]
    };

    const issues = await service.validateAnnotation(annotation);
    const baseErrors = issues.filter(i => i.code === 'BASE_OUTSIDE_MODEL');

    expect(baseErrors.length).toBe(1);
    expect(baseErrors[0].type).toBe('error');
  });

  test('should accept valid base bbox inside model', async () => {
    const annotation = {
      imageId: 'test',
      imagePath: '/test/image.jpg',
      faction: 'tyranids',
      source: 'reddit',
      annotations: [{
        id: '1',
        x: 100,
        y: 100,
        width: 100,
        height: 100,
        classLabel: 'miniature',
        baseBbox: {
          x: 120,
          y: 120,
          width: 50,
          height: 50
        }
      }]
    };

    const issues = await service.validateAnnotation(annotation);
    const baseErrors = issues.filter(i => i.code === 'BASE_OUTSIDE_MODEL');

    expect(baseErrors.length).toBe(0);
  });

  test('should detect duplicate boxes (>90% IoU)', async () => {
    const annotation = {
      imageId: 'test',
      imagePath: '/test/image.jpg',
      faction: 'tyranids',
      source: 'reddit',
      annotations: [
        { id: '1', x: 100, y: 100, width: 100, height: 100, classLabel: 'miniature' },
        { id: '2', x: 101, y: 101, width: 100, height: 100, classLabel: 'miniature' }  // Near duplicate
      ]
    };

    const issues = await service.validateAnnotation(annotation);
    const duplicates = issues.filter(i => i.code === 'DUPLICATE_BOX');

    expect(duplicates.length).toBeGreaterThan(0);
  });

  test('should reject bbox out of image bounds', async () => {
    // Mock image dimensions: 500x500
    const annotation = {
      imageId: 'test',
      imagePath: '/test/image_500x500.jpg',
      faction: 'tyranids',
      source: 'reddit',
      annotations: [{
        id: '1',
        x: 450,
        y: 450,
        width: 100,  // Extends to x=550 (out of bounds)
        height: 100
        classLabel: 'miniature'
      }]
    };

    const issues = await service.validateAnnotation(annotation);
    const boundsErrors = issues.filter(i => i.code === 'BBOX_OUT_OF_BOUNDS');

    expect(boundsErrors.length).toBe(1);
  });
});

describe('YOLO Export Validation', () => {
  test('should validate normalized coordinates (0-1 range)', () => {
    const badLabel = '0 1.5 0.5 0.2 0.3';  // x_center > 1.0
    // ... validator should catch this
  });

  test('should validate keypoint count (must be 4 for base corners)', () => {
    const badLabel = '0 0.5 0.5 0.2 0.3 0.1 0.1 1 0.2 0.1 1';  // Only 2 keypoints
    // ... validator should reject
  });

  test('should validate visibility flags (must be 0 or 1)', () => {
    const badLabel = '0 0.5 0.5 0.2 0.3 0.1 0.1 2';  // visibility=2 (invalid)
    // ... validator should reject
  });
});
```

**Run tests**:
```bash
npm test -- annotationService.test.ts
```

---

### End-to-End Test Flow
**Effort**: 1-2 hours
**Validates entire pipeline**

Test the complete annotation → export → validate → train flow:

**E2E test script** (`scripts/test_e2e.sh`):
```bash
#!/bin/bash

set -e  # Exit on error

echo "🧪 Running E2E annotation pipeline test..."

# 1. Start services
echo "1️⃣ Starting backend..."
npm run dev:backend &
BACKEND_PID=$!
sleep 3

# 2. Create test annotation
echo "2️⃣ Creating test annotation..."
curl -X POST http://localhost:3001/api/annotate/save \
  -H "Content-Type: application/json" \
  -d '{
    "imageId": "test_001",
    "imagePath": "test-images/test.jpg",
    "faction": "tyranids",
    "source": "test",
    "annotations": [{
      "id": "1",
      "x": 100,
      "y": 100,
      "width": 200,
      "height": 200,
      "classLabel": "miniature",
      "baseBbox": {
        "x": 150,
        "y": 150,
        "width": 100,
        "height": 100
      }
    }]
  }'

# 3. Export to YOLO
echo "3️⃣ Exporting to YOLO format..."
curl -X POST http://localhost:3001/api/annotate/export \
  -H "Content-Type: application/json" \
  -d '{"outputDir": "test_yolo_dataset", "trainSplit": 0.8}'

# 4. Validate exported dataset
echo "4️⃣ Validating YOLO dataset..."
python scripts/validate_yolo_dataset.py test_yolo_dataset

if [ $? -eq 0 ]; then
  echo "✅ Validation passed!"
else
  echo "❌ Validation failed!"
  kill $BACKEND_PID
  exit 1
fi

# 5. Quick YOLO training test (5 epochs)
echo "5️⃣ Running quick YOLO training test..."
source yolo_training/venv/bin/activate
yolo pose train \
  data=test_yolo_dataset/data.yaml \
  model=yolov8n-pose.pt \
  epochs=5 \
  imgsz=416 \
  batch=2 \
  project=test_runs \
  name=e2e_test

if [ $? -eq 0 ]; then
  echo "✅ Training test passed!"
else
  echo "❌ Training test failed!"
  kill $BACKEND_PID
  exit 1
fi

# Cleanup
echo "6️⃣ Cleaning up..."
kill $BACKEND_PID
rm -rf test_yolo_dataset test_runs

echo ""
echo "🎉 E2E test complete! Pipeline is working."
```

**Run E2E test**:
```bash
chmod +x scripts/test_e2e.sh
./scripts/test_e2e.sh
```

---

### Timeline Buffer & Risk Mitigation

**Original estimate**: 19-20 hours

**Revised estimate with buffer**: 22-25 hours
- Validator debugging: +1-2h
- Zoom/pan coordinate edge cases: +1h
- Integration issues: +1-2h

**Risk Mitigation**:
1. **Start with validators** - Catch issues early before building on bad foundation
2. **Test incrementally** - Run unit tests after each feature
3. **Manual testing** - Annotate 10-20 images after each phase
4. **Early export test** - Export and validate after Phase 1, before building Phase 2

**Blockers to watch for**:
- Sharp image metadata failures (check for corrupted images in dataset)
- Coordinate rounding bugs (test with various zoom levels)
- IoU calculation edge cases (overlapping boxes at image boundaries)

---

## Implementation Checklist

Execute in this order:

### Week 1: Correctness Infrastructure
- [ ] Define YOLO-pose label contract (30 min discussion)
  - [ ] Decide: missing base bbox behavior (recommend: omit keypoints)
  - [ ] Confirm: keypoint order (TL→TR→BR→BL)
  - [ ] Confirm: single class ("miniature")
  - [ ] Confirm: visibility encoding (0/1 binary)
- [ ] Write export validator script (4h)
  - [ ] Label format validation
  - [ ] Keypoint validation
  - [ ] Image-label pairing check
  - [ ] data.yaml validation
- [ ] Add real-time quality checks (3h)
  - [ ] Base-in-model check
  - [ ] Out-of-bounds check
  - [ ] Duplicate detection
  - [ ] Frontend error display

### Week 2: Throughput Boosters
- [ ] Implement Zoom/Pan (5h)
  - [ ] Centralized coordinate conversion
  - [ ] Mouse wheel zoom toward cursor
  - [ ] Space+drag panning
  - [ ] Viewport clamping
  - [ ] Reset zoom (R key)
- [ ] Implement Undo/Redo (3h)
  - [ ] Command pattern
  - [ ] Ctrl+Z / Ctrl+Shift+Z
  - [ ] History reset on image change
  - [ ] UI indicators (enabled/disabled buttons)

### Week 3: Training Pipeline
- [ ] Setup training environment (2h)
  - [ ] Run setup script
  - [ ] Download pre-trained models
  - [ ] Create configs (quick test + production)
- [ ] Create model testing harness (2h)
  - [ ] Test script for inference
  - [ ] Visualization of predictions
- [ ] Export first test dataset (even with few annotations)
  - [ ] Run validator
  - [ ] Fix any issues
  - [ ] Quick test training (5 epochs, verify it works)

---

## Out of Scope (For Now)

These are **not** being implemented in this phase:

### Deferred Features
- **Bulk gallery mode** - High complexity, defer until annotation complete
- **Templates** - Risk of systematic errors
- **Model comparison dashboard** - Compare mAP across training iterations
- **Export confidence-weighted sampling** - Oversample low-confidence factions in training split

### Previously Deferred, Now Implemented
- ~~**Analytics dashboards**~~ - **Implemented Feb 15, 2026** as Quality Dashboard
- ~~**Faction difficulty analysis**~~ - **Implemented** via box sizes by faction + outlier detection
- ~~**Timing analytics**~~ - **Implemented** as annotation speed (per day) chart
- ~~**Active learning / prioritization**~~ - **Implemented** via batch YOLO inference + confidence scoring

### Why Some Remain Deferred
These features either:
- Have high implementation cost relative to benefit
- Risk introducing subtle bugs that poison the dataset
- Can be added later without affecting core workflow

---

## Success Criteria

You'll know this is working when:

1. **Validation catches real errors**
   - Run validator on export → finds actual issues
   - Fix issues → validator passes
   - Train model → converges properly

2. **Annotation is faster**
   - Zoom/pan feels natural
   - Undo/redo prevents rage-quits
   - No coordinate bugs

3. **Training just works**
   - Export → validate → train (no surprises)
   - Model converges to reasonable mAP50 (>0.7)
   - Predictions make sense on test images

---

## Total Effort Estimate

### Breakdown by Phase

**Week 1 - Correctness Infrastructure**:
- YOLO-pose validator: 4-5h
- Real-time quality checks: 3-4h
- Quality issues UI modal: 1-2h
- Pre-export validation endpoint: 1h
- **Subtotal: 9-12h**

**Week 2 - Throughput Boosters**:
- Zoom & Pan (centralized transforms): 4-5h
- Undo/Redo (command pattern): 3-4h
- Auto-constrain base bbox: 1h
- **Subtotal: 8-10h**

**Week 3 - Training Pipeline**:
- Training environment setup: 2-3h
- Model testing harness: 2-3h
- **Subtotal: 4-6h**

**Testing & QA**:
- Unit tests for validators: 2-3h
- E2E test flow: 1-2h
- **Subtotal: 3-5h**

**Buffer** (debugging, integration, edge cases): 3-5h

### Total Estimate

**Base estimate**: 24-33 hours
**With buffer**: **27-38 hours**

### Comparison to Original Plan

**Original (before expert reviews)**: 19-20 hours
**Revised (with expert feedback)**: 27-38 hours
**Additional time**: +8-18 hours

**What changed**:
- Added overlap detection to validator (+0.5h)
- Added pixel-to-normalized conversion docs (+0h, just docs)
- Added quality issues UI modal (+1-2h)
- Added pre-export validation (+1h)
- Added auto-constrain base bbox (+1h)
- Added comprehensive testing (+3-5h)
- Added realistic buffer (+3-5h)

**Why the increase is worth it**:
- Prevents training on bad data (saves GPU time and frustration)
- Catches errors during annotation (not after 1000 images)
- Auto-constrain prevents most common error type
- Tests ensure pipeline works before committing time

---

**Ready to start? Recommend beginning with the 30-minute YOLO-pose contract discussion, then implementing the validator.**
