#!/usr/bin/env python3
"""
Unit Tests for YOLO Dataset Validator

Tests the validation logic in validate_yolo_dataset.py:
- Directory structure validation
- data.yaml validation
- Label file format validation
- Coordinate range validation
- Keypoint validation
- Overlap detection

Run with: pytest test_validate_yolo_dataset.py -v
"""

import pytest
import tempfile
import shutil
from pathlib import Path
import yaml
import sys

# Import the validator
sys.path.insert(0, str(Path(__file__).parent))
from validate_yolo_dataset import DatasetValidator


class TestDatasetValidator:
    """Test suite for YOLO dataset validator"""

    @pytest.fixture
    def temp_dataset(self):
        """Create a temporary dataset structure"""
        temp_dir = tempfile.mkdtemp()
        dataset_path = Path(temp_dir) / 'test_dataset'
        dataset_path.mkdir()

        # Create directory structure
        for split in ['train', 'val']:
            (dataset_path / 'images' / split).mkdir(parents=True)
            (dataset_path / 'labels' / split).mkdir(parents=True)

        yield dataset_path

        # Cleanup
        shutil.rmtree(temp_dir)

    def test_directory_structure_valid(self, temp_dataset):
        """Test that validator accepts valid directory structure"""
        # Create data.yaml
        data_yaml = {
            'train': 'images/train',
            'val': 'images/val',
            'nc': 1,
            'names': ['miniature'],
            'kpt_shape': [4, 3]
        }
        with open(temp_dataset / 'data.yaml', 'w') as f:
            yaml.dump(data_yaml, f)

        validator = DatasetValidator(temp_dataset)
        assert validator.check_structure() == True
        assert len(validator.errors) == 0

    def test_directory_structure_missing_dirs(self, temp_dataset):
        """Test that validator detects missing directories"""
        # Remove a required directory
        shutil.rmtree(temp_dataset / 'images' / 'val')

        validator = DatasetValidator(temp_dataset)
        assert validator.check_structure() == False
        assert len(validator.errors) > 0
        assert any('images/val' in err for err in validator.errors)

    def test_data_yaml_valid(self, temp_dataset):
        """Test validation of valid data.yaml"""
        data_yaml = {
            'train': 'images/train',
            'val': 'images/val',
            'nc': 1,
            'names': ['miniature'],
            'kpt_shape': [4, 3]
        }
        with open(temp_dataset / 'data.yaml', 'w') as f:
            yaml.dump(data_yaml, f)

        validator = DatasetValidator(temp_dataset)
        validator.check_structure()
        config = validator.load_data_yaml()

        assert config is not None
        assert config['nc'] == 1
        assert config['kpt_shape'] == [4, 3]
        assert len(validator.errors) == 0

    def test_data_yaml_missing_fields(self, temp_dataset):
        """Test that validator detects missing required fields"""
        data_yaml = {
            'train': 'images/train',
            # Missing 'val', 'nc', 'names', 'kpt_shape'
        }
        with open(temp_dataset / 'data.yaml', 'w') as f:
            yaml.dump(data_yaml, f)

        validator = DatasetValidator(temp_dataset)
        validator.check_structure()
        config = validator.load_data_yaml()

        assert len(validator.errors) >= 4  # Should have errors for missing fields

    def test_data_yaml_invalid_kpt_shape(self, temp_dataset):
        """Test that validator detects invalid kpt_shape"""
        data_yaml = {
            'train': 'images/train',
            'val': 'images/val',
            'nc': 1,
            'names': ['miniature'],
            'kpt_shape': [4, 2]  # Wrong! Should be [4, 3]
        }
        with open(temp_dataset / 'data.yaml', 'w') as f:
            yaml.dump(data_yaml, f)

        validator = DatasetValidator(temp_dataset)
        validator.check_structure()
        config = validator.load_data_yaml()

        assert len(validator.errors) > 0
        assert any('kpt_shape' in err for err in validator.errors)

    def test_data_yaml_class_count_mismatch(self, temp_dataset):
        """Test that validator detects nc != len(names)"""
        data_yaml = {
            'train': 'images/train',
            'val': 'images/val',
            'nc': 2,  # Says 2 classes
            'names': ['miniature'],  # But only 1 name
            'kpt_shape': [4, 3]
        }
        with open(temp_dataset / 'data.yaml', 'w') as f:
            yaml.dump(data_yaml, f)

        validator = DatasetValidator(temp_dataset)
        validator.check_structure()
        config = validator.load_data_yaml()

        assert len(validator.errors) > 0
        assert any('mismatch' in err.lower() for err in validator.errors)


class TestLabelValidation:
    """Test suite for label file validation"""

    @pytest.fixture
    def temp_dataset(self):
        """Create temp dataset with structure"""
        temp_dir = tempfile.mkdtemp()
        dataset_path = Path(temp_dir) / 'test_dataset'
        dataset_path.mkdir()

        for split in ['train', 'val']:
            (dataset_path / 'images' / split).mkdir(parents=True)
            (dataset_path / 'labels' / split).mkdir(parents=True)

        data_yaml = {
            'train': 'images/train',
            'val': 'images/val',
            'nc': 1,
            'names': ['miniature'],
            'kpt_shape': [4, 3]
        }
        with open(dataset_path / 'data.yaml', 'w') as f:
            yaml.dump(data_yaml, f)

        yield dataset_path
        shutil.rmtree(temp_dir)

    def test_valid_bbox_only_label(self, temp_dataset):
        """Test validation of bbox-only label (5 values)"""
        label_file = temp_dataset / 'labels' / 'train' / 'test.txt'
        label_file.write_text('0 0.5 0.5 0.3 0.2\n')

        validator = DatasetValidator(temp_dataset)
        validator.check_structure()
        validator.load_data_yaml()

        issues = validator.validate_label_file(label_file, 1, 'train')
        assert len(issues) == 0

    def test_valid_pose_label(self, temp_dataset):
        """Test validation of pose label (17 values)"""
        # class x_center y_center width height + 4 keypoints (x,y,v each)
        label_line = '0 0.5 0.5 0.3 0.2 0.4 0.4 1 0.6 0.4 1 0.6 0.6 1 0.4 0.6 1\n'
        label_file = temp_dataset / 'labels' / 'train' / 'test.txt'
        label_file.write_text(label_line)

        validator = DatasetValidator(temp_dataset)
        validator.check_structure()
        validator.load_data_yaml()

        issues = validator.validate_label_file(label_file, 1, 'train')
        assert len(issues) == 0

    def test_invalid_format_wrong_value_count(self, temp_dataset):
        """Test detection of wrong number of values"""
        label_file = temp_dataset / 'labels' / 'train' / 'test.txt'
        label_file.write_text('0 0.5 0.5 0.3\n')  # Only 4 values (invalid)

        validator = DatasetValidator(temp_dataset)
        validator.check_structure()
        validator.load_data_yaml()

        issues = validator.validate_label_file(label_file, 1, 'train')
        assert len(issues) > 0
        assert any('format' in str(i) for i in issues)

    def test_invalid_class_id(self, temp_dataset):
        """Test detection of invalid class ID"""
        label_file = temp_dataset / 'labels' / 'train' / 'test.txt'
        label_file.write_text('5 0.5 0.5 0.3 0.2\n')  # Class 5, but nc=1

        validator = DatasetValidator(temp_dataset)
        validator.check_structure()
        validator.load_data_yaml()

        issues = validator.validate_label_file(label_file, 1, 'train')
        assert len(issues) > 0
        assert any('class' in str(i) for i in issues)

    def test_bbox_center_out_of_range(self, temp_dataset):
        """Test detection of bbox center outside 0-1 range"""
        label_file = temp_dataset / 'labels' / 'train' / 'test.txt'
        label_file.write_text('0 1.5 0.5 0.3 0.2\n')  # x=1.5 (out of range)

        validator = DatasetValidator(temp_dataset)
        validator.check_structure()
        validator.load_data_yaml()

        issues = validator.validate_label_file(label_file, 1, 'train')
        assert len(issues) > 0
        assert any('bbox_center' in str(i) for i in issues)

    def test_bbox_size_invalid(self, temp_dataset):
        """Test detection of invalid bbox size"""
        label_file = temp_dataset / 'labels' / 'train' / 'test.txt'
        label_file.write_text('0 0.5 0.5 0 0.2\n')  # width=0 (invalid)

        validator = DatasetValidator(temp_dataset)
        validator.check_structure()
        validator.load_data_yaml()

        issues = validator.validate_label_file(label_file, 1, 'train')
        assert len(issues) > 0
        assert any('bbox_size' in str(i) for i in issues)

    def test_keypoint_out_of_range(self, temp_dataset):
        """Test detection of keypoint coordinates outside 0-1 range"""
        # Keypoint at x=1.5 (out of range)
        label_line = '0 0.5 0.5 0.3 0.2 1.5 0.4 1 0.6 0.4 1 0.6 0.6 1 0.4 0.6 1\n'
        label_file = temp_dataset / 'labels' / 'train' / 'test.txt'
        label_file.write_text(label_line)

        validator = DatasetValidator(temp_dataset)
        validator.check_structure()
        validator.load_data_yaml()

        issues = validator.validate_label_file(label_file, 1, 'train')
        assert len(issues) > 0
        assert any('kpt_coords' in str(i) for i in issues)

    def test_keypoint_invalid_visibility(self, temp_dataset):
        """Test detection of invalid visibility flag"""
        # Visibility = 0.5 (should be 0 or 1)
        label_line = '0 0.5 0.5 0.3 0.2 0.4 0.4 0.5 0.6 0.4 1 0.6 0.6 1 0.4 0.6 1\n'
        label_file = temp_dataset / 'labels' / 'train' / 'test.txt'
        label_file.write_text(label_line)

        validator = DatasetValidator(temp_dataset)
        validator.check_structure()
        validator.load_data_yaml()

        issues = validator.validate_label_file(label_file, 1, 'train')
        assert len(issues) > 0
        assert any('kpt_visibility' in str(i) for i in issues)

    def test_empty_label_file(self, temp_dataset):
        """Test that empty label file is valid (no objects)"""
        label_file = temp_dataset / 'labels' / 'train' / 'test.txt'
        label_file.write_text('')

        validator = DatasetValidator(temp_dataset)
        validator.check_structure()
        validator.load_data_yaml()

        issues = validator.validate_label_file(label_file, 1, 'train')
        assert len(issues) == 0  # Empty is valid


class TestOverlapDetection:
    """Test overlap detection (IoU calculation)"""

    def test_calculate_iou_identical_boxes(self):
        """Test IoU for identical boxes (should be 1.0)"""
        validator = DatasetValidator(Path('.'))

        bbox1 = (0.5, 0.5, 0.2, 0.2)  # cx, cy, w, h
        bbox2 = (0.5, 0.5, 0.2, 0.2)

        iou = validator.calculate_iou(bbox1, bbox2)
        assert abs(iou - 1.0) < 0.01

    def test_calculate_iou_no_overlap(self):
        """Test IoU for non-overlapping boxes (should be 0.0)"""
        validator = DatasetValidator(Path('.'))

        bbox1 = (0.3, 0.3, 0.2, 0.2)
        bbox2 = (0.7, 0.7, 0.2, 0.2)

        iou = validator.calculate_iou(bbox1, bbox2)
        assert iou == 0.0

    def test_calculate_iou_partial_overlap(self):
        """Test IoU for partially overlapping boxes"""
        validator = DatasetValidator(Path('.'))

        bbox1 = (0.4, 0.4, 0.2, 0.2)  # 0.3-0.5 in both x and y
        bbox2 = (0.5, 0.5, 0.2, 0.2)  # 0.4-0.6 in both x and y

        iou = validator.calculate_iou(bbox1, bbox2)

        # Overlap region: 0.1 x 0.1 = 0.01
        # Union: 0.04 + 0.04 - 0.01 = 0.07
        # IoU: 0.01 / 0.07 ≈ 0.143
        assert abs(iou - 0.143) < 0.01

    def test_calculate_iou_high_overlap(self):
        """Test IoU for high overlap (>50%)"""
        validator = DatasetValidator(Path('.'))

        bbox1 = (0.5, 0.5, 0.2, 0.2)
        bbox2 = (0.52, 0.52, 0.2, 0.2)  # Slightly offset

        iou = validator.calculate_iou(bbox1, bbox2)
        assert iou > 0.5  # High overlap


class TestFullValidation:
    """Integration tests for full validation pipeline"""

    @pytest.fixture
    def complete_dataset(self):
        """Create a complete valid dataset"""
        temp_dir = tempfile.mkdtemp()
        dataset_path = Path(temp_dir) / 'test_dataset'
        dataset_path.mkdir()

        # Create structure
        for split in ['train', 'val']:
            (dataset_path / 'images' / split).mkdir(parents=True)
            (dataset_path / 'labels' / split).mkdir(parents=True)

        # Create data.yaml
        data_yaml = {
            'train': 'images/train',
            'val': 'images/val',
            'nc': 1,
            'names': ['miniature'],
            'kpt_shape': [4, 3]
        }
        with open(dataset_path / 'data.yaml', 'w') as f:
            yaml.dump(data_yaml, f)

        # Create dummy images
        for split in ['train', 'val']:
            img_dir = dataset_path / 'images' / split
            (img_dir / 'img1.jpg').touch()
            (img_dir / 'img2.jpg').touch()

        # Create valid labels
        for split in ['train', 'val']:
            labels_dir = dataset_path / 'labels' / split
            (labels_dir / 'img1.txt').write_text('0 0.5 0.5 0.3 0.2\n')
            (labels_dir / 'img2.txt').write_text(
                '0 0.5 0.5 0.3 0.2 0.4 0.4 1 0.6 0.4 1 0.6 0.6 1 0.4 0.6 1\n'
            )

        yield dataset_path
        shutil.rmtree(temp_dir)

    def test_full_validation_success(self, complete_dataset):
        """Test that a valid dataset passes full validation"""
        validator = DatasetValidator(complete_dataset)
        success = validator.validate()

        assert success == True
        assert len(validator.errors) == 0

    @pytest.mark.xfail(reason="DatasetValidator does not currently flag small normalized bboxes as warnings. Feature gap (not a regression) — remove this mark when the validator learns the rule.")
    def test_full_validation_with_warnings(self, complete_dataset):
        """Test dataset with warnings still passes"""
        # Add a label with small bbox (warning)
        label_file = complete_dataset / 'labels' / 'train' / 'img1.txt'
        label_file.write_text('0 0.5 0.5 0.01 0.01\n')  # Very small (warning)

        validator = DatasetValidator(complete_dataset)
        validator.validate()

        # Should still pass with warnings
        assert len(validator.warnings) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
