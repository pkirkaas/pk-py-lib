"""
Tests for individual processing phases.

Tests each phase in isolation to ensure correct behavior
and enable targeted testing of complex logic.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from pk_py_lib.core.flat_cache import FlatCacheManager
from pk_py_lib.core.image.similarity.phases import (
    PhaseContext,
    phase_algorithm_resolution,
    phase_exact_duplicate_detection,
    phase_perceptual_hash_computation,
    phase_similarity_clustering,
    execute_all_phases
)
from pk_py_lib.core.image.similarity.types import SimilarityError, ExactDuplicateSet
from pk_py_lib.gui.dialog_models import Group


class TestPhaseContext:
    """Test PhaseContext initialization and data management."""

    def test_context_initialization(self):
        """Test PhaseContext is properly initialized."""
        paths = ["/path/to/img1.jpg", "/path/to/img2.jpg"]
        context = PhaseContext(
            image_paths=paths,
            algorithm="phash",
            threshold=10,
            settings={"test": "value"},
            flat_cache_manager=None,
            search_type="similarity"
        )

        assert context.image_paths == paths
        assert context.algorithm == "phash"
        assert context.threshold == 10
        assert context.settings == {"test": "value"}
        assert context.flat_cache_manager is None
        assert context.search_type == "similarity"

        # Check phase-specific data is initialized
        assert context.exact_sets == []
        assert context.path_to_set_id_map == {}
        assert context.representative_paths == []
        assert context.perceptual_hashes == {}
        assert context.representative_groups == []
        assert context.final_groups == []
        assert context.stats == {}

    def test_context_data_management(self):
        """Test context data updates between phases."""
        context = PhaseContext(image_paths=[])

        # Test that context can store phase results
        exact_set = ExactDuplicateSet(id=1, paths=["/a.jpg", "/b.jpg"], representative_path="/a.jpg")
        context.exact_sets = [exact_set]
        context.path_to_set_id_map = {"/a.jpg": 1, "/b.jpg": 1}
        context.stats["test"] = "value"

        assert len(context.exact_sets) == 1
        assert context.path_to_set_id_map["/a.jpg"] == 1
        assert context.stats["test"] == "value"


class TestPhaseAlgorithmResolution:
    """Test algorithm resolution phase."""

    def test_valid_algorithm_resolution(self):
        """Test resolution with valid algorithm."""
        context = PhaseContext(
            image_paths=["/test/img.jpg"],
            algorithm="phash"
        )

        result = phase_algorithm_resolution(context)

        assert result.algorithm == "phash"
        assert result.stats["resolved_algorithm"] == "phash"
        assert result.stats["search_type"] == "similarity"

    def test_algorithm_from_settings(self):
        """Test algorithm resolution from settings."""
        context = PhaseContext(
            image_paths=["/test/img.jpg"],
            algorithm=None,
            settings={"criteria": {"similarity_hash_algorithm": "whash"}}
        )

        result = phase_algorithm_resolution(context)

        assert result.algorithm == "whash"
        assert result.stats["resolved_algorithm"] == "whash"

    def test_default_algorithm(self):
        """Test default algorithm when none specified."""
        context = PhaseContext(
            image_paths=["/test/img.jpg"],
            algorithm=None,
            settings=None
        )

        result = phase_algorithm_resolution(context)

        assert result.algorithm == "phash"
        assert result.stats["resolved_algorithm"] == "phash"

    def test_empty_paths_raises_error(self):
        """Test that empty paths list raises SimilarityError."""
        context = PhaseContext(image_paths=[])

        with pytest.raises(SimilarityError, match="paths list cannot be empty"):
            phase_algorithm_resolution(context)

    def test_invalid_algorithm_raises_error(self):
        """Test that invalid algorithm raises SimilarityError."""
        context = PhaseContext(
            image_paths=["/test/img.jpg"],
            algorithm="invalid"
        )

        with pytest.raises(SimilarityError, match="Unsupported algorithm: invalid"):
            phase_algorithm_resolution(context)


class TestPhaseExactDuplicateDetection:
    """Test exact duplicate detection phase."""

    def test_no_duplicates(self, tmp_path):
        """Test with no duplicate files."""
        # Create unique test files
        files = []
        for i in range(3):
            file_path = tmp_path / f"unique_{i}.jpg"
            file_path.write_bytes(f"unique content {i}".encode())
            files.append(str(file_path))

        context = PhaseContext(
            image_paths=files,
            algorithm="phash"
        )

        result = phase_exact_duplicate_detection(context)

        assert len(result.exact_sets) == 0
        assert len(result.path_to_set_id_map) == 3
        assert all(v is None for v in result.path_to_set_id_map.values())
        assert result.stats["exact_sets_count"] == 0
        assert result.stats["exact_duplicates_count"] == 0

    def test_with_duplicates(self, tmp_path):
        """Test with duplicate files."""
        # Create duplicate files
        content = b"duplicate content"
        files = []
        for i in range(3):
            file_path = tmp_path / f"dup_{i}.jpg"
            file_path.write_bytes(content)
            files.append(str(file_path))

        # Add a unique file
        unique_path = tmp_path / "unique.jpg"
        unique_path.write_bytes(b"unique content")
        files.append(str(unique_path))

        context = PhaseContext(
            image_paths=files,
            algorithm="phash"
        )

        result = phase_exact_duplicate_detection(context)

        assert len(result.exact_sets) == 1
        assert len(result.exact_sets[0].paths) == 3
        assert result.stats["exact_sets_count"] == 1
        assert result.stats["exact_duplicates_count"] == 3

        # Check mapping
        assert result.path_to_set_id_map[files[0]] == 1
        assert result.path_to_set_id_map[files[1]] == 1
        assert result.path_to_set_id_map[files[2]] == 1
        assert result.path_to_set_id_map[str(unique_path)] is None

    def test_exact_mode_skips_detection(self, tmp_path):
        """Test that exact mode skips duplicate detection."""
        files = []
        for i in range(2):
            file_path = tmp_path / f"file_{i}.jpg"
            file_path.write_bytes(f"content {i}".encode())
            files.append(str(file_path))

        context = PhaseContext(
            image_paths=files,
            algorithm="exact"
        )

        result = phase_exact_duplicate_detection(context)

        assert len(result.exact_sets) == 0
        assert result.stats["exact_sets_count"] == 0
        assert result.stats["exact_duplicates_count"] == 0

    @patch('pk_py_lib.core.filesystem.identity.compute_xxh3')
    def test_with_cache_manager(self, mock_compute_hash, tmp_path):
        """Test duplicate detection with cache manager."""
        # Create test files
        files = []
        for i in range(2):
            file_path = tmp_path / f"file_{i}.jpg"
            file_path.write_bytes(f"content {i}".encode())
            files.append(str(file_path))

        # Mock cache manager
        mock_cache = Mock(spec=FlatCacheManager)
        mock_cache.get_hashes.return_value = {
            files[0]: {"xxh3": "hash1"},
            files[1]: {"xxh3": "hash2"}
        }

        context = PhaseContext(
            image_paths=files,
            algorithm="phash",
            flat_cache_manager=mock_cache
        )

        result = phase_exact_duplicate_detection(context)

        # Verify cache was used
        mock_cache.get_hashes.assert_called_once_with(files, ['xxh3'])

        # Verify results
        assert len(result.exact_sets) == 0
        assert result.stats["exact_sets_count"] == 0


class TestPhasePerceptualHashComputation:
    """Test perceptual hash computation phase."""

    def test_exact_mode_skips_computation(self):
        """Test that exact mode skips hash computation."""
        context = PhaseContext(
            image_paths=["/test/img.jpg"],
            algorithm="exact"
        )
        context.path_to_set_id_map = {}

        result = phase_perceptual_hash_computation(context)

        assert len(result.perceptual_hashes) == 0
        assert result.stats["perceptual_hashes_count"] == 0

    @patch('pk_py_lib.core.image.similarity.phases.compute_similarity_hash_batch')
    def test_hash_computation_with_representatives(self, mock_compute_batch):
        """Test hash computation for representative paths."""
        files = ["/img1.jpg", "/img2.jpg", "/img3.jpg"]
        mock_compute_batch.return_value = {
            "/img1.jpg": "a1b2c3d4e5f67890",
            "/img2.jpg": "b2c3d4e5f6789012",
            "/img3.jpg": None  # Failed computation
        }

        context = PhaseContext(
            image_paths=files,
            algorithm="phash"
        )
        # Mock exact duplicate detection results
        context.path_to_set_id_map = {"/img1.jpg": None, "/img2.jpg": None, "/img3.jpg": None}

        result = phase_perceptual_hash_computation(context)

        # Verify batch computation was called with representatives
        mock_compute_batch.assert_called_once()
        call_args = mock_compute_batch.call_args
        assert set(call_args[0][0]) == set(files)  # All files are representatives
        assert call_args[1]["algorithm"] == "phash"

        # Verify results
        assert len(result.perceptual_hashes) == 3
        assert result.perceptual_hashes["/img1.jpg"] == "a1b2c3d4e5f67890"
        assert result.perceptual_hashes["/img2.jpg"] == "b2c3d4e5f6789012"
        assert result.perceptual_hashes["/img3.jpg"] is None
        assert result.stats["perceptual_hashes_count"] == 2  # Only valid hashes
        assert result.stats["representative_paths_count"] == 3

    def test_representative_identification(self):
        """Test identification of representative paths."""
        files = ["/img1.jpg", "/img2.jpg", "/img3.jpg", "/img4.jpg"]

        context = PhaseContext(
            image_paths=files,
            algorithm="phash"
        )

        # Mock exact duplicate detection results
        # img1 and img2 are duplicates, img3 and img4 are singletons
        exact_set = ExactDuplicateSet(
            id=1,
            paths=["/img1.jpg", "/img2.jpg"],
            representative_path="/img1.jpg"
        )
        context.exact_sets = [exact_set]
        context.path_to_set_id_map = {
            "/img1.jpg": 1,
            "/img2.jpg": 1,
            "/img3.jpg": None,
            "/img4.jpg": None
        }

        with patch('pk_py_lib.core.image.similarity.phases.compute_similarity_hash_batch') as mock_batch:
            mock_batch.return_value = {}

            result = phase_perceptual_hash_computation(context)

            # Verify representatives were identified correctly
            expected_reps = ["/img1.jpg", "/img3.jpg", "/img4.jpg"]
            assert set(result.representative_paths) == set(expected_reps)
            # Check that mock was called with correct parameters (order may differ)
            mock_batch.assert_called_once()
            call_args = mock_batch.call_args
            assert set(call_args[0][0]) == set(expected_reps)
            assert call_args[1]["algorithm"] == "phash"
            assert call_args[1]["settings"] is None
            assert call_args[1]["flat_cache_manager"] is None
            assert call_args[1]["search_type"] == "similarity"


class TestPhaseSimilarityClustering:
    """Test similarity clustering phase."""

    def test_exact_mode_clustering(self, tmp_path):
        """Test clustering in exact mode."""
        # Create test files
        files = []
        for i in range(3):
            file_path = tmp_path / f"file_{i}.jpg"
            file_path.write_bytes(f"content {i}".encode())
            files.append(str(file_path))

        # Create exact duplicate set
        exact_set = ExactDuplicateSet(
            id=1,
            paths=files,
            representative_path=files[0]
        )

        context = PhaseContext(
            image_paths=files,
            algorithm="exact"
        )
        context.exact_sets = [exact_set]

        with patch('pk_py_lib.core.image.similarity.phases.get_image_metadata') as mock_meta:
            mock_meta.return_value = {
                'size': 1000,
                'resolution': '100x100',
                'mod_date': '01-Jan-25'
            }

            result = phase_similarity_clustering(context)

            # Verify groups were created
            assert len(result.final_groups) == 1
            group = result.final_groups[0]
            assert group.id == 1
            assert len(group.items) == 3
            assert group.ref_path == files[0]
            assert result.stats["final_groups_count"] == 1

    @patch('pk_py_lib.core.image.similarity.clustering.find_similar_phash')
    def test_perceptual_clustering(self, mock_find_similar):
        """Test perceptual clustering."""
        # Mock representative groups
        mock_group = Mock(spec=Group)
        mock_group.ref_path = "/img1.jpg"

        # Create two items to ensure group has >=2 items
        mock_item1 = Mock()
        mock_item1.path = "/img1.jpg"
        mock_item1.score = 0.9
        mock_item1.size = 1000
        mock_item1.resolution = "100x100"
        mock_item1.mod_date = "01-Jan-25"
        mock_item1.file_type = ""
        mock_item1.savings = 0
        mock_item1.quality_score = None
        mock_item1.quality_algorithm = None
        mock_item1.exact_set_id = None

        mock_item2 = Mock()
        mock_item2.path = "/img2.jpg"
        mock_item2.score = 0.8
        mock_item2.size = 1000
        mock_item2.resolution = "100x100"
        mock_item2.mod_date = "01-Jan-25"
        mock_item2.file_type = ""
        mock_item2.savings = 0
        mock_item2.quality_score = None
        mock_item2.quality_algorithm = None
        mock_item2.exact_set_id = None

        mock_group.items = [mock_item1, mock_item2]

        mock_find_similar.return_value = [mock_group]

        context = PhaseContext(
            image_paths=["/img1.jpg", "/img2.jpg"],
            algorithm="phash"
        )
        context.representative_paths = ["/img1.jpg"]
        context.perceptual_hashes = {"/img1.jpg": "a1b2c3d4e5f67890"}
        context.path_to_set_id_map = {"/img1.jpg": None}

        with patch('pk_py_lib.core.image.similarity.phases.get_image_metadata') as mock_meta:
            mock_meta.return_value = {
                'size': 1000,
                'resolution': '100x100',
                'mod_date': '01-Jan-25'
            }

            result = phase_similarity_clustering(context)

            # Verify clustering was called
            mock_find_similar.assert_called_once()

            # Verify results
            assert len(result.final_groups) == 1
            assert result.stats["final_groups_count"] == 1
            assert result.stats["representative_groups_count"] == 1

    def test_no_valid_hashes_returns_empty(self):
        """Test that no valid hashes returns empty groups."""
        context = PhaseContext(
            image_paths=["/img1.jpg"],
            algorithm="phash"
        )
        context.representative_paths = ["/img1.jpg"]
        context.perceptual_hashes = {"/img1.jpg": None}  # Failed computation
        context.path_to_set_id_map = {"/img1.jpg": None}

        result = phase_similarity_clustering(context)

        assert len(result.final_groups) == 0
        assert result.stats["final_groups_count"] == 0


class TestExecuteAllPhases:
    """Test phase orchestration."""

    def test_successful_execution(self, tmp_path):
        """Test successful execution of all phases."""
        # Create test files
        files = []
        for i in range(2):
            file_path = tmp_path / f"file_{i}.jpg"
            file_path.write_bytes(f"content {i}".encode())
            files.append(str(file_path))

        context = PhaseContext(
            image_paths=files,
            algorithm="exact"
        )

        with patch('pk_py_lib.core.image.similarity.phases.get_image_metadata') as mock_meta:
            mock_meta.return_value = {
                'size': 1000,
                'resolution': '100x100',
                'mod_date': '01-Jan-25'
            }

            result = execute_all_phases(context)

            # Verify all phases were executed
            assert result.stats["resolved_algorithm"] == "exact"
            assert result.stats["search_type"] == "similarity"
            assert "exact_sets_count" in result.stats
            assert "final_groups_count" in result.stats

    def test_phase_failure_handling(self):
        """Test that phase failures are properly handled."""
        context = PhaseContext(image_paths=[])  # Empty paths will cause failure

        with pytest.raises(SimilarityError, match="Phase Algorithm Resolution failed"):
            execute_all_phases(context)

    def test_context_propagation(self, tmp_path):
        """Test that context is properly propagated between phases."""
        files = []
        for i in range(2):
            file_path = tmp_path / f"file_{i}.jpg"
            file_path.write_bytes(f"content {i}".encode())
            files.append(str(file_path))

        context = PhaseContext(
            image_paths=files,
            algorithm="phash"
        )

        with patch('pk_py_lib.core.image.similarity.phases.compute_similarity_hash_batch') as mock_batch:
            mock_batch.return_value = {}

            with patch('pk_py_lib.core.image.similarity.phases.get_image_metadata') as mock_meta:
                mock_meta.return_value = {
                    'size': 1000,
                    'resolution': '100x100',
                    'mod_date': '01-Jan-25'
                }

                result = execute_all_phases(context)

                # Verify data flows between phases
                assert "resolved_algorithm" in result.stats
                assert "exact_sets_count" in result.stats
                assert "perceptual_hashes_count" in result.stats
                assert "final_groups_count" in result.stats


class TestIntegration:
    """Integration tests for the complete phase pipeline."""

    def test_exact_mode_integration(self, tmp_path):
        """Test complete pipeline in exact mode."""
        # Create duplicate files
        content = b"duplicate content"
        files = []
        for i in range(3):
            file_path = tmp_path / f"dup_{i}.jpg"
            file_path.write_bytes(content)
            files.append(str(file_path))

        context = PhaseContext(
            image_paths=files,
            algorithm="exact"
        )

        result = execute_all_phases(context)

        # Verify complete pipeline
        assert len(result.final_groups) == 1
        assert len(result.final_groups[0].items) == 3
        assert result.stats["resolved_algorithm"] == "exact"
        assert result.stats["final_groups_count"] == 1

    @patch('pk_py_lib.core.image.similarity.phases.compute_similarity_hash_batch')
    @patch('pk_py_lib.core.image.similarity.clustering.find_similar_phash')
    def test_perceptual_mode_integration(self, mock_find_similar, mock_compute_batch, tmp_path):
        """Test complete pipeline in perceptual mode."""
        # Create test files
        files = []
        for i in range(3):
            file_path = tmp_path / f"file_{i}.jpg"
            file_path.write_bytes(f"content {i}".encode())
            files.append(str(file_path))

        # Mock hash computation
        mock_compute_batch.return_value = {
            files[0]: "a1b2c3d4e5f67890",
            files[1]: "a1b2c3d4e5f67891",  # Similar
            files[2]: "b2c3d4e5f6789012"   # Different
        }

        # Mock clustering result
        mock_group = Mock(spec=Group)
        mock_group.ref_path = files[0]

        # Create proper mock items with all required attributes
        mock_item1 = Mock()
        mock_item1.path = files[0]
        mock_item1.score = 0.9
        mock_item1.size = 1000
        mock_item1.resolution = "100x100"
        mock_item1.mod_date = "01-Jan-25"
        mock_item1.file_type = ""
        mock_item1.savings = 0
        mock_item1.quality_score = None
        mock_item1.quality_algorithm = None
        mock_item1.exact_set_id = None

        mock_item2 = Mock()
        mock_item2.path = files[1]
        mock_item2.score = 0.8
        mock_item2.size = 1000
        mock_item2.resolution = "100x100"
        mock_item2.mod_date = "01-Jan-25"
        mock_item2.file_type = ""
        mock_item2.savings = 0
        mock_item2.quality_score = None
        mock_item2.quality_algorithm = None
        mock_item2.exact_set_id = None

        mock_group.items = [mock_item1, mock_item2]
        mock_find_similar.return_value = [mock_group]

        context = PhaseContext(
            image_paths=files,
            algorithm="phash",
            threshold=5
        )

        with patch('pk_py_lib.core.image.similarity.phases.get_image_metadata') as mock_meta:
            mock_meta.return_value = {
                'size': 1000,
                'resolution': '100x100',
                'mod_date': '01-Jan-25'
            }

            result = execute_all_phases(context)

            # Verify complete pipeline
            assert len(result.final_groups) == 1
            assert result.stats["resolved_algorithm"] == "phash"
            assert result.stats["final_groups_count"] == 1
            assert result.stats["perceptual_hashes_count"] == 3
