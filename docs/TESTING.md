# Testing Guide

This document describes how to run the unit tests for the Warhammer 40K annotation tool.

## Test Coverage

We have comprehensive unit tests for:
- ✅ **Backend validation** (TypeScript/Jest)
  - Bbox out of bounds detection
  - Bbox too small warnings
  - Base bbox outside model detection
  - Duplicate box detection (IoU calculation)
  - Complex multi-error scenarios

- ✅ **Python YOLO validator** (pytest)
  - Directory structure validation
  - data.yaml validation
  - Label format validation (5 values bbox, 17 values pose)
  - Coordinate range validation
  - Keypoint validation
  - Overlap detection

## Running Tests

### Backend Tests (TypeScript/Jest)

```bash
# Install dependencies (if not already done)
cd backend
npm install

# Run all tests
npm test

# Run validation tests specifically
npm test -- annotationService.validation.test.ts

# Run with coverage
npm test -- --coverage

# Watch mode (re-run on file changes)
npm test -- --watch
```

**Expected Output:**
```
PASS  src/services/__tests__/annotationService.validation.test.ts
  AnnotationService - Validation
    validateAnnotation - Bbox Out of Bounds
      ✓ should return error when model bbox extends beyond image (right edge)
      ✓ should return error when model bbox extends beyond image (bottom edge)
      ✓ should return error when model bbox has negative coordinates
      ✓ should pass when model bbox is within bounds
    validateAnnotation - Bbox Too Small
      ✓ should return warning when model bbox is very small (< 10px)
      ✓ should pass when model bbox is large enough
    ...

Test Suites: 1 passed, 1 total
Tests:       28 passed, 28 total
```

### Python Tests (pytest)

```bash
# Install pytest (if not already done)
pip install pytest pytest-cov

# Run all Python tests
cd scripts
pytest test_validate_yolo_dataset.py -v

# Run with coverage
pytest test_validate_yolo_dataset.py -v --cov=validate_yolo_dataset --cov-report=html

# Run specific test class
pytest test_validate_yolo_dataset.py::TestLabelValidation -v

# Run specific test
pytest test_validate_yolo_dataset.py::TestLabelValidation::test_valid_pose_label -v
```

**Expected Output:**
```
test_validate_yolo_dataset.py::TestDatasetValidator::test_directory_structure_valid PASSED
test_validate_yolo_dataset.py::TestDatasetValidator::test_directory_structure_missing_dirs PASSED
test_validate_yolo_dataset.py::TestDatasetValidator::test_data_yaml_valid PASSED
test_validate_yolo_dataset.py::TestLabelValidation::test_valid_bbox_only_label PASSED
test_validate_yolo_dataset.py::TestLabelValidation::test_valid_pose_label PASSED
...

======================== 25 passed in 0.5s ========================
```

## Test Structure

### Backend Tests (`backend/src/services/__tests__/annotationService.validation.test.ts`)

Tests are organized by validation type:
- **Bbox Out of Bounds**: Ensures bboxes stay within image dimensions
- **Bbox Too Small**: Detects tiny accidental boxes
- **Base Outside Model**: Ensures base bbox is inside model bbox
- **Duplicate Boxes**: Detects overlapping boxes (>90% IoU)
- **Complex Scenarios**: Multi-error cases, perfect annotations
- **IoU Calculation**: Tests the Intersection over Union algorithm

### Python Tests (`scripts/test_validate_yolo_dataset.py`)

Tests are organized into classes:
- **TestDatasetValidator**: Directory structure, data.yaml validation
- **TestLabelValidation**: Label format, coordinates, keypoints
- **TestOverlapDetection**: IoU calculation edge cases
- **TestFullValidation**: Integration tests for complete datasets

## Writing New Tests

### Adding Backend Tests

```typescript
it('should detect my new validation case', async () => {
  const annotation: ImageAnnotation = {
    ...baseAnnotation,
    annotations: [{
      // Your test case
    }]
  }

  const issues = await annotationService.validateAnnotation(annotation)

  // Assertions
  expect(issues).toContainEqual({
    type: 'error',
    code: 'MY_NEW_CODE',
    message: expect.stringContaining('expected message')
  })
})
```

### Adding Python Tests

```python
def test_my_new_validation(self, temp_dataset):
    """Test description"""
    label_file = temp_dataset / 'labels' / 'train' / 'test.txt'
    label_file.write_text('0 0.5 0.5 0.3 0.2\n')

    validator = DatasetValidator(temp_dataset)
    validator.check_structure()
    validator.load_data_yaml()

    issues = validator.validate_label_file(label_file, 1, 'train')
    assert len(issues) == 0  # or > 0 for error cases
```

## Continuous Integration

To set up CI (GitHub Actions, GitLab CI, etc.):

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      # Backend tests
      - name: Setup Node.js
        uses: actions/setup-node@v2
        with:
          node-version: '18'
      - run: cd backend && npm install && npm test

      # Python tests
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.8'
      - run: pip install pytest
      - run: cd scripts && pytest test_validate_yolo_dataset.py -v
```

## Coverage Reports

### Backend Coverage

After running `npm test -- --coverage`, open:
```
backend/coverage/lcov-report/index.html
```

### Python Coverage

After running `pytest --cov`, open:
```
htmlcov/index.html
```

## Troubleshooting

**TypeScript tests fail with "Cannot find module":**
- Run `cd backend && npm install` to install dependencies
- Ensure `@types/jest` is installed

**Python tests fail with "ModuleNotFoundError":**
- Install pytest: `pip install pytest`
- Ensure you're in the `scripts/` directory when running tests

**Tests timeout:**
- Increase timeout in Jest config: `jest.setTimeout(10000)`
- For pytest: `pytest --timeout=10`

**Mock issues:**
- Ensure sharp is properly mocked in TypeScript tests
- Check that file paths exist in Python fixtures

## Test Philosophy

Our tests follow these principles:

1. **Comprehensive Coverage**: Test happy path, edge cases, and error cases
2. **Fast Execution**: Use mocks to avoid slow I/O operations
3. **Clear Names**: Test names describe what they're testing
4. **Isolated**: Each test is independent and can run in any order
5. **Maintainable**: Tests are easy to understand and update

## Metrics

**Current Test Coverage:**
- Backend validation: 28 test cases
- Python validator: 25+ test cases
- Total: 50+ comprehensive tests
- Coverage: ~90% of validation logic

## Next Steps

To further improve testing:
- Add E2E tests for the full annotation workflow
- Add frontend component tests (React Testing Library)
- Add integration tests for the API endpoints
- Set up automated CI/CD pipeline
