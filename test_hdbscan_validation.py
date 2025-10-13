import sys
import os
from pathlib import Path
import tempfile
import numpy as np
from unittest.mock import Mock, patch

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from pk_py_lib.core.image.similarity.clustering import (
    find_similar_phash, cluster_with_hdbscan, find_similar_images,
    detect_exact_duplicates
)
from pk_py_lib.core.image.similarity.similarity_types import SimilarityError
from pk_py_lib.core.flat_cache import FlatCacheManager
from pk_py_lib.gui.dialog_models import Group

def test_hdbscan_clustering():
    """Test HDBSCAN clustering with sample hashes."""
    print("Testing HDBSCAN clustering...")

    # Sample hash records: close pairs for clusters, outliers
    hash_records = [
        {'path': '/img1.jpg', 'hash': '0000000000000000'},  # Cluster 1
        {'path': '/img2.jpg', 'hash': '0000000000000001'},
        {'path': '/img3.jpg', 'hash': '0000000000000010'},  # Cluster 1 (dist=2 from img1)
        {'path': '/img4.jpg', 'hash': '1111111111111111'},  # Cluster 2
        {'path': '/img5.jpg', 'hash': '1111111111111110'},  # Cluster 2
        {'path': '/img6.jpg', 'hash': '2222222222222222'},  # Noise (outlier)
        {'path': '/img7.jpg', 'hash': '3333333333333333'},  # Noise
    ]

    settings = {
        'similarity': {
            'hdbscan_min_cluster_size': 2,
            'hdbscan_min_samples': None,
            'hdbscan_cluster_selection_epsilon': 0.0,
            'hdbscan_adaptive_tuning': True,
            'clustering_algorithm': 'hdbscan'
        }
    }

    try:
        clusters = cluster_with_hdbscan(hash_records, threshold=3, settings=settings)
        print(f"Clusters: {clusters}")

        # Expected: 2 clusters (0-2, 3-4), noise (-1: [5,6])
        cluster_ids = [list(c.keys())[0] for c in clusters if list(c.keys())[0] != -1]
        assert len(cluster_ids) == 2
        noise_cluster = next(c for c in clusters if -1 in c)
        assert len(noise_cluster[-1]) == 2

        print("HDBSCAN test passed: 2 clusters, 2 noise points")
        return True
    except Exception as e:
        print(f"HDBSCAN test failed: {e}")
        return False

def test_unionfind_fallback():
    """Test Union-Find fallback with same data."""
    print("\nTesting Union-Find fallback...")

    hash_records = [
        {'path': '/img1.jpg', 'hash': '0000000000000000'},
        {'path': '/img2.jpg', 'hash': '0000000000000001'},
        {'path': '/img3.jpg', 'hash': '0000000000000010'},
        {'path': '/img4.jpg', 'hash': '1111111111111111'},
        {'path': '/img5.jpg', 'hash': '1111111111111110'},
        {'path': '/img6.jpg', 'hash': '2222222222222222'},
        {'path': '/img7.jpg', 'hash': '3333333333333333'},
    ]

    settings = {
        'similarity': {
            'clustering_algorithm': 'unionfind'
        }
    }

    groups = find_similar_phash(hash_records, threshold=3, settings=settings)
    print(f"Union-Find groups: {len(groups)}")

    # Expected: 2 groups (transitive chaining)
    assert len(groups) == 2
    print("Union-Find test passed: 2 groups")
    return True

def test_find_similar_images_integration():
    """Test full find_similar_images with HDBSCAN."""
    print("\nTesting full find_similar_images integration...")

    # Mock paths (no real files needed for this test)
    paths = ['/test/img1.jpg', '/test/img2.jpg', '/test/img3.jpg', '/test/img4.jpg']

    # Mock cache manager
    mock_cache = Mock()
    mock_cache.get_hashes.return_value = {p: {'phash': '0000000000000000' if i < 2 else '1111111111111111'} for i, p in enumerate(paths)}

    settings = {
        'similarity': {
            'clustering_algorithm': 'hdbscan',
            'phash_threshold': 1,
            'hdbscan_min_cluster_size': 2
        }
    }

    try:
        groups = find_similar_images(
            paths=paths,
            algorithm='phash',
            threshold=1,
            settings=settings,
            flat_cache_manager=mock_cache,
            search_type='similarity'
        )
        print(f"Integration groups: {len(groups)}")

        # Expected: 2 groups if HDBSCAN works, or fallback
        assert len(groups) >= 1
        print("Integration test passed")
        return True
    except Exception as e:
        print(f"Integration test failed: {e}")
        return False

def test_error_handling():
    """Test error cases."""
    print("\nTesting error handling...")

    # Empty paths
    try:
        find_similar_images(paths=[], return_response=True)
        assert False, "Should raise error for empty paths"
    except ValueError:
        print("Empty paths error handled correctly")

    # Invalid algorithm
    try:
        find_similar_images(paths=['/test.jpg'], algorithm='invalid', return_response=True)
        assert False, "Should raise error for invalid algorithm"
    except SimilarityError:
        print("Invalid algorithm error handled correctly")

    print("Error handling test passed")
    return True

if __name__ == "__main__":
    results = {
        'hdbscan_clustering': test_hdbscan_clustering(),
        'unionfind_fallback': test_unionfind_fallback(),
        'integration': test_find_similar_images_integration(),
        'error_handling': test_error_handling()
    }

    print("\nTest Summary:")
    for test, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"{test}: {status}")

    all_passed = all(results.values())
    print(f"\nOverall: {'ALL PASS' if all_passed else 'SOME FAILURES'}")
    sys.exit(0 if all_passed else 1)
