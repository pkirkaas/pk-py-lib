"""
tests/test_settings_schema.py

Tests for the SettingsProfileOptionA JSON schema and validation system.

This module tests the new structured settings profile system including:
- JSON schema validation
- Custom validation rules
- Normalization functionality
- Compatibility checking
- Path validation

Note: Syntax validation performed per project rules using Python ast.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from src.pk_py_lib.core.settings_schema import (
    SETTINGS_PROFILE_SCHEMA,
    validate_settings_schema,
    normalize_settings,
    create_default_profile,
    is_valid_for_save,
    is_valid_for_run,
    SettingsValidationError
)


class TestSettingsSchema:
    """Test the JSON schema validation and normalization."""

    def test_schema_structure(self):
        """Test that the schema has the expected structure."""
        assert SETTINGS_PROFILE_SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "properties" in SETTINGS_PROFILE_SCHEMA
        assert "pools" in SETTINGS_PROFILE_SCHEMA["properties"]
        assert "mode" in SETTINGS_PROFILE_SCHEMA["properties"]
        assert "criteria" in SETTINGS_PROFILE_SCHEMA["properties"]
        assert "scope" in SETTINGS_PROFILE_SCHEMA["properties"]
        assert "output" in SETTINGS_PROFILE_SCHEMA["properties"]
        assert "similarity" in SETTINGS_PROFILE_SCHEMA["properties"]
        assert "image_quality_evaluator" in SETTINGS_PROFILE_SCHEMA["properties"]
        assert "use_flat_cache" in SETTINGS_PROFILE_SCHEMA["properties"]

    def test_create_default_profile(self):
        """Test creating a default profile."""
        profile = create_default_profile("Test Profile", "Test description")

        assert profile["name"] == "Test Profile"
        assert profile["description"] == "Test description"
        assert profile["mode"] == "duplicates"
        assert profile["scope"]["kind"] == "single_pool"
        assert profile["output"]["mode"] == "report_only"
        assert "id" in profile
        assert "created_at" in profile
        assert "updated_at" in profile
        assert profile["similarity"]["phash_threshold"] == 10
        assert profile["similarity"]["enabled_algorithms"] == ["phash"]
        assert profile["criteria"]["algorithm"] == "xxh3"
        assert profile["pools"]["A"]["paths"] == [str(Path.home())]
        assert profile["image_quality_evaluator"] == "brisque"
        assert profile["use_flat_cache"] is True

    @patch('src.pk_py_lib.core.settings_schema.Path')
    def test_validate_minimal_duplicates_profile(self, mock_path):
        """Test validation of a minimal duplicates profile."""
        # Mock path to exist
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_instance.is_dir.return_value = True
        mock_path.return_value = mock_path_instance

        profile = {
            "id": "12345678-1234-5678-1234-567812345678",
            "name": "Test Duplicates",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "pools": {
                "A": {
                    "paths": ["/tmp/test"]
                }
            },
            "mode": "duplicates",
            "criteria": {
                "algorithm": "blake3"
            },
            "scope": {
                "kind": "single_pool"
            },
            "output": {
                "mode": "report_only"
            }
        }

        is_valid, errors = validate_settings_schema(profile)
        assert is_valid, f"Validation failed: {errors}"

    @patch('src.pk_py_lib.core.settings_schema.Path')
    def test_validate_minimal_similarity_profile(self, mock_path):
        """Test validation of a minimal similarity profile."""
        # Mock path to exist
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_instance.is_dir.return_value = True
        mock_path.return_value = mock_path_instance

        profile = {
            "id": "12345678-1234-5678-1234-567812345678",
            "name": "Test Similarity",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "pools": {
                "A": {
                    "paths": ["/tmp/test"]
                }
            },
            "mode": "similarity",
            "criteria": {
                "algorithm": "phash",
                "similarity_hash_algorithm": "phash",
                "degree_ui": 90
            },
            "scope": {
                "kind": "single_pool"
            },
            "output": {
                "mode": "report_only"
            }
        }

        is_valid, errors = validate_settings_schema(profile)
        assert is_valid, f"Validation failed: {errors}"

    @patch('src.pk_py_lib.core.settings_schema.Path')
    def test_validate_two_pool_profile(self, mock_path):
        """Test validation of a two-pool profile."""
        # Mock path to exist
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_instance.is_dir.return_value = True
        mock_path.return_value = mock_path_instance

        profile = {
            "id": "12345678-1234-5678-1234-567812345678",
            "name": "Test Two Pool",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "pools": {
                "A": {
                    "paths": ["/tmp/test1"]
                },
                "B": {
                    "paths": ["/tmp/test2"]
                }
            },
            "mode": "similarity",
            "criteria": {
                "algorithm": "phash",
                "similarity_hash_algorithm": "phash",
                "degree_ui": 90
            },
            "scope": {
                "kind": "two_pool",
                "direction": "duplicates"
            },
            "output": {
                "mode": "report_only"
            }
        }

        is_valid, errors = validate_settings_schema(profile)
        assert is_valid, f"Validation failed: {errors}"

    @patch('src.pk_py_lib.core.settings_schema.Path')
    def test_validation_fails_missing_required_fields(self, mock_path):
        """Test validation fails when required fields are missing."""
        # Mock path to exist
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_instance.is_dir.return_value = True
        mock_path.return_value = mock_path_instance

        profile = {
            "name": "Test Profile",
            "pools": {
                "A": {
                    "paths": ["/tmp/test"]
                }
            }
        }

        is_valid, errors = validate_settings_schema(profile)
        assert not is_valid
        # JSON schema validation should catch missing required fields
        assert any("id" in error or "required" in error for error in errors)
        assert any("created_at" in error or "required" in error for error in errors)
        assert any("updated_at" in error or "required" in error for error in errors)

    @patch('src.pk_py_lib.core.settings_schema.Path')
    def test_validation_fails_invalid_mode(self, mock_path):
        """Test validation fails with invalid mode."""
        # Mock path to exist
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_instance.is_dir.return_value = True
        mock_path.return_value = mock_path_instance

        profile = {
            "id": "12345678-1234-5678-1234-567812345678",
            "name": "Test Profile",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "pools": {
                "A": {
                    "paths": ["/tmp/test"]
                }
            },
            "mode": "invalid_mode",
            "criteria": {
                "algorithm": "blake3"
            },
            "scope": {
                "kind": "single_pool"
            },
            "output": {
                "mode": "report_only"
            }
        }

        is_valid, errors = validate_settings_schema(profile)
        assert not is_valid
        assert any("mode" in error or "enum" in error for error in errors)

    @patch('src.pk_py_lib.core.settings_schema.Path')
    def test_validation_fails_duplicates_with_degree(self, mock_path):
        """Test validation fails when duplicates mode has degree_ui."""
        # Mock path to exist
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_instance.is_dir.return_value = True
        mock_path.return_value = mock_path_instance

        profile = {
            "id": "12345678-1234-5678-1234-567812345678",
            "name": "Test Profile",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "pools": {
                "A": {
                    "paths": ["/tmp/test"]
                }
            },
            "mode": "duplicates",
            "criteria": {
                "algorithm": "blake3",
                "degree_ui": 90
            },
            "scope": {
                "kind": "single_pool"
            },
            "output": {
                "mode": "report_only"
            }
        }

        is_valid, errors = validate_settings_schema(profile)
        assert not is_valid
        # JSON schema should catch this with "not" constraint
        assert any("degree_ui" in error or "not" in error for error in errors)

    @patch('src.pk_py_lib.core.settings_schema.Path')
    def test_validation_fails_similarity_without_degree(self, mock_path):
        """Test validation fails when similarity mode lacks degree_ui."""
        # Mock path to exist
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_instance.is_dir.return_value = True
        mock_path.return_value = mock_path_instance

        profile = {
            "id": "12345678-1234-5678-1234-567812345678",
            "name": "Test Profile",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "pools": {
                "A": {
                    "paths": ["/tmp/test"]
                }
            },
            "mode": "similarity",
            "criteria": {
                "algorithm": "phash",
                "similarity_hash_algorithm": "phash"
            },
            "scope": {
                "kind": "single_pool"
            },
            "output": {
                "mode": "report_only"
            }
        }

        is_valid, errors = validate_settings_schema(profile)
        assert not is_valid
        # JSON schema should require degree_ui for similarity mode
        assert any("degree_ui" in error or "required" in error for error in errors)

    @patch('src.pk_py_lib.core.settings_schema.Path')
    def test_validation_fails_two_pool_without_pool_b(self, mock_path):
        """Test validation fails when two-pool mode lacks pool B."""
        # Mock path to exist
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_instance.is_dir.return_value = True
        mock_path.return_value = mock_path_instance

        profile = {
            "id": "12345678-1234-5678-1234-567812345678",
            "name": "Test Profile",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "pools": {
                "A": {
                    "paths": ["/tmp/test"]
                }
            },
            "mode": "similarity",
            "criteria": {
                "algorithm": "phash",
                "similarity_hash_algorithm": "phash",
                "degree_ui": 90
            },
            "scope": {
                "kind": "two_pool",
                "direction": "duplicates"
            },
            "output": {
                "mode": "report_only"
            }
        }

        is_valid, errors = validate_settings_schema(profile)
        assert not is_valid
        # JSON schema should require Pool B for two-pool mode
        assert any("pools" in error or "required" in error for error in errors)

    def test_normalize_settings_applies_defaults(self):
        """Test that normalization applies default values."""
        minimal_profile = {
            "id": "12345678-1234-5678-1234-567812345678",
            "name": "Test Profile",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "pools": {
                "A": {
                    "paths": ["/tmp/test"]
                }
            },
            "mode": "duplicates",
            "criteria": {
                "algorithm": "blake3"
            },
            "scope": {
                "kind": "single_pool"
            },
            "output": {
                "mode": "report_only"
            }
        }

        normalized = normalize_settings(minimal_profile)

        # Check that defaults are applied
        assert normalized["pools"]["A"]["recurse"] is True
        assert normalized["pools"]["A"]["max_depth"] == 0
        assert normalized["pools"]["A"]["include"] == ["**/*"]
        assert normalized["pools"]["A"]["exclude"] == []
        assert normalized["pools"]["A"]["follow_symlinks"] is False
        assert normalized["pools"]["A"]["include_hidden"] is False
        assert normalized["pools"]["A"]["type_filters"] == [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]

    def test_normalize_settings_two_pool(self):
        """Test normalization with two-pool configuration."""
        minimal_profile = {
            "id": "12345678-1234-5678-1234-567812345678",
            "name": "Test Profile",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "pools": {
                "A": {
                    "paths": ["/tmp/test1"]
                },
                "B": {
                    "paths": ["/tmp/test2"]
                }
            },
            "mode": "similarity",
            "criteria": {
                "algorithm": "phash",
                "similarity_hash_algorithm": "phash",
                "degree_ui": 90
            },
            "scope": {
                "kind": "two_pool",
                "direction": "duplicates"
            },
            "output": {
                "mode": "report_only"
            }
        }

        normalized = normalize_settings(minimal_profile)

        # Check that defaults are applied to both pools
        assert normalized["pools"]["A"]["recurse"] is True
        assert normalized["pools"]["B"]["recurse"] is True
        assert normalized["scope"]["direction"] == "duplicates"

    @patch('src.pk_py_lib.core.settings_schema.Path')
    def test_path_validation_existing_directory(self, mock_path):
        """Test path validation with existing directory."""
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_instance.is_dir.return_value = True
        mock_path.return_value = mock_path_instance

        profile = {
            "id": "12345678-1234-5678-1234-567812345678",
            "name": "Test Profile",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "pools": {
                "A": {
                    "paths": ["/tmp/test"]
                }
            },
            "mode": "duplicates",
            "criteria": {
                "algorithm": "blake3"
            },
            "scope": {
                "kind": "single_pool"
            },
            "output": {
                "mode": "report_only"
            }
        }

        is_valid, errors = validate_settings_schema(profile)
        assert is_valid, f"Validation failed: {errors}"

    @patch('src.pk_py_lib.core.settings_schema.Path')
    def test_path_validation_nonexistent_directory(self, mock_path):
        """Test path validation with non-existent directory."""
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = False
        mock_path_instance.is_dir.return_value = False
        mock_path.return_value = mock_path_instance

        profile = {
            "id": "12345678-1234-5678-1234-567812345678",
            "name": "Test Profile",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "pools": {
                "A": {
                    "paths": ["/tmp/nonexistent"]
                }
            },
            "mode": "duplicates",
            "criteria": {
                "algorithm": "blake3"
            },
            "scope": {
                "kind": "single_pool"
            },
            "output": {
                "mode": "report_only"
            }
        }

        is_valid, errors = validate_settings_schema(profile)
        assert not is_valid
        assert any("does not exist" in error for error in errors)

    def test_is_valid_for_save_with_valid_profile(self):
        """Test is_valid_for_save with a valid profile."""
        profile = {
            "id": "12345678-1234-5678-1234-567812345678",
            "name": "Test Profile",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "pools": {
                "A": {
                    "paths": ["/tmp/test"]
                }
            },
            "mode": "duplicates",
            "criteria": {
                "algorithm": "blake3"
            },
            "scope": {
                "kind": "single_pool"
            },
            "output": {
                "mode": "report_only"
            }
        }

        # Mock path validation to avoid filesystem dependency
        with patch('src.pk_py_lib.core.settings_schema.Path') as mock_path:
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = True
            mock_path_instance.is_dir.return_value = True
            mock_path.return_value = mock_path_instance

            is_valid, errors = is_valid_for_save(profile)
            assert is_valid, f"Validation failed: {errors}"

    def test_is_valid_for_save_with_missing_path(self):
        """Test is_valid_for_save with missing path."""
        profile = {
            "id": "12345678-1234-5678-1234-567812345678",
            "name": "Test Profile",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "pools": {
                "A": {
                    "paths": [""]
                }
            },
            "mode": "duplicates",
            "criteria": {
                "algorithm": "blake3"
            },
            "scope": {
                "kind": "single_pool"
            },
            "output": {
                "mode": "report_only"
            }
        }

        is_valid, errors = is_valid_for_save(profile)
        assert not is_valid
        assert len(errors) > 0  # Ensure there are validation errors

    def test_is_valid_for_run_with_valid_profile(self):
        """Test is_valid_for_run with a valid profile."""
        profile = {
            "id": "12345678-1234-5678-1234-567812345678",
            "name": "Test Profile",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "pools": {
                "A": {
                    "paths": ["/tmp/test"]
                }
            },
            "mode": "duplicates",
            "criteria": {
                "algorithm": "blake3"
            },
            "scope": {
                "kind": "single_pool"
            },
            "output": {
                "mode": "report_only"
            }
        }

        # Mock path validation to avoid filesystem dependency
        with patch('src.pk_py_lib.core.settings_schema.Path') as mock_path:
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = True
            mock_path_instance.is_dir.return_value = True
            mock_path.return_value = mock_path_instance

            is_valid, errors = is_valid_for_run(profile)
            assert is_valid, f"Validation failed: {errors}"

    def test_is_valid_for_run_with_invalid_profile(self):
        """Test is_valid_for_run with an invalid profile."""
        profile = {
            "id": "12345678-1234-5678-1234-567812345678",
            "name": "Test Profile",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "pools": {
                "A": {
                    "paths": ["/tmp/nonexistent"]
                }
            },
            "mode": "duplicates",
            "criteria": {
                "algorithm": "blake3"
            },
            "scope": {
                "kind": "single_pool"
            },
            "output": {
                "mode": "report_only"
            }
        }

        # Mock path validation to return false
        with patch('src.pk_py_lib.core.settings_schema.Path') as mock_path:
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = False
            mock_path_instance.is_dir.return_value = False
            mock_path.return_value = mock_path_instance

            is_valid, errors = is_valid_for_run(profile)
            assert not is_valid
            assert any("does not exist" in error for error in errors)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
