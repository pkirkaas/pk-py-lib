# Documentation Consistency Fixes Summary

## Date: 2025-08-20
## Scope: Documentation-only changes for cross-document consistency alignment

This document summarizes the documentation-only edits made to ensure consistency across the pk-py-lib and img_app project documentation suite, particularly aligning with canonical decisions and Settings Profiles v1 (Option A).

## Changes Applied

### 1. docs/roo/img-app-data-model.md
**Issue:** Thumbnails were defined as BLOBs in database schema, conflicting with canonical decision §10 requiring file-backed storage.  
**Fix:** 
- Updated `thumbnails` table schema to use `relative_path TEXT` instead of `thumbnail_data BLOB`
- Moved `scan_sessions` and `scan_results` tables to new Sessions Database section
- Added `settings_profiles` table with JSON payload column for Option A
- Added bridging note explaining transition from typed tables to JSON-based Option A approach

### 2. docs/roo/img-app-technical-architecture.md
**Issue:** Missing sessions.db in three-database architecture; thumbnails shown as BLOBs; incorrect results_panel path.  
**Fix:**
- Added sessions.db schema section with canonical decision §11 reference
- Added comment noting three-database architecture (settings, sessions, cache)
- Updated thumbnails table to file-backed with `relative_path` field
- Added clarifying comment for results_panel location
- Removed duplicate scan_sessions/scan_results tables from cache.db section

### 3. docs/roo/img-app-implementation-guide.md
**Issue:** Using hardcoded paths instead of platformdirs; missing three-database clarity.  
**Fix:**
- Updated platformdirs usage with Vendor "Pk" and App "Img App"
- Added PK_IMG_APP_HOME environment override documentation
- Clarified three-database architecture with purpose of each database
- Updated DatabaseManager initialization to use platformdirs
- Added sessions.db to database creation flow

### 4. docs/roo/img-app-api-specifications.md
**Issue:** Potential confusion between BLAKE3 (Option A duplicates) and SHA-256 (general cache).  
**Fix:**
- Added clarification note in FileIdentityAPI section explaining:
  - Option A duplicates detection uses BLAKE3 per canonical decision §18
  - SHA-256 remains for general cache identity and file validation

### 5. docs/roo/img-app-specification.md
**Issue:** Missing Option A override notes in algorithm sections.  
**Fix:**
- Added Option A override note in section 2.1.3 referencing canonical decision §18
- Added note that Option A uses BLAKE3 for duplicates (not SHA-256)
- Added Option A algorithm selection note in section 2.1.4:
  - Duplicates mode: BLAKE3 (fixed)
  - Similarity mode: pHash with degree normalization

### 6. docs/roo/acceptance-review-checklist.md
**Issue:** Missing verification items for three-database architecture and file-backed thumbnails.  
**Fix:**
- Added checklist items for three-database architecture verification:
  - settings.db, sessions.db, cache.db locations and purposes
- Added checklist items for file-backed thumbnails policy:
  - Files stored in cache/thumbnails/{size}x{size}/
  - Database stores only metadata with relative_path
  - No BLOB storage for thumbnails

## Canonical Decisions Referenced

The following canonical decisions were consistently applied across all documents:

- **Decision §10**: File-backed thumbnails (not BLOBs)
- **Decision §11**: Three-database architecture (settings.db, sessions.db, cache.db)
- **Decision §18**: Settings Profiles v1 (Option A) with:
  - BLAKE3 for duplicates detection
  - pHash for similarity with degree normalization
  - Balanced defaults
  - Package A specifics
  - Set A initial states

## Verification

All changes are documentation-only and maintain consistency with:
- Canonical decisions document
- Settings Profiles v1 (Option A) specifications
- Balanced defaults configuration
- Package A algorithm specifics
- Set A UI initial states

## Impact Assessment

- **Code Impact**: None - all changes are documentation-only
- **API Impact**: None - clarifications only, no contract changes
- **Schema Impact**: Documentation now correctly reflects intended implementation
- **UI Impact**: None - clarifications align with existing design

## Review Recommendations

1. Verify that implementation follows the corrected documentation
2. Update any code generation tools that might use these schemas
3. Ensure test cases align with the documented three-database architecture
4. Validate that thumbnail storage implementation uses file-backed approach

## Approval

These documentation-only changes ensure consistency across the project documentation suite and accurately reflect the canonical decisions and Option A specifications. No code changes are included in this update.

---
*End of Document*