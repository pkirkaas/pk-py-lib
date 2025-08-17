# Create Application Specification Document

- Your task is to create a detailed application specification document for the application described below, at `/docs/img-app-spec-gen.md`
- Your process should be interactive - the description below is a just a rough initial outline. 
- You should consider the description deeply & think through it step by step
- Before attempting to create the application specification, you should interactively prompt for clarification, details, etc
- Be sure to ask multiple follow-up questions to fully define the requirements
- You should also propose additional features, functionality, behavior that would add value
- The specification document should be optimized for use by an AI coding/design assistant (RooCode, etc)
- It should be complete and detailed, but terse, not chatty, very professional
- To ensure all requirements are clear and complete, you will not create the specification document until you ask for confirmation to proceed 
- Create the full specification document, as well as any additional documents required for implementation (architecture, design, etc), in the /docs/roo subdirectory, as markdown/.md files.
- Double check EVERYTHING! Think through everything step by step - and check again.

- Make absolutely certain that the generated specification/design documents are correct, complete, and fully detailed.

- Take all the time you need - speed of response is not a priority - fully considered, thought through, correct response IS THE ONLY Priority.

- RECALL: The documents should be optimized/focused for input/guidelines for AI Code Generation, by RooCode

## Image App project description

- The img-app project is a desktop GUI application intended to manage & organize tens of thousands of photographs stored on the local file system
- It should be cross-platform - Windows, Linux, Mac, etc
- It will use the latest Python 13+, PySide6, and additional supporting libraries/packages
- The appearance/layout is a standard GUI application - title bar, menu bar, GUI main window interface
- The application will be highly configurable/customizable, and provide support for saving multiple configurations/settings/profiles.
- Use SQLite for persistent data across three databases: settings.db, sessions.db, and cache.db; each contains a meta table with schema_version and participates in managed migrations (Alembic) with timestamped backups (retain 10 most recent, purge older than 30 days).
- Use platformdirs for data locations with Vendor "Pk" and App "Img App"; allow PK_IMG_APP_HOME to override the base directory for both data and cache trees. Place settings.db and sessions.db in user_data_dir, and cache.db plus thumbnails under user_cache_dir.
- On startup, validate databases with PRAGMA quick_check (then integrity_check on failure); rebuild flows: preserve/export settings where possible for settings.db, prompt rebuild/repair for sessions.db, and auto-rebuild cache.db.

### Image File Selection

- The app should provide a GUI interface to select files/folders for the img-app.
- The GUI Selector should allow selection of multiple image files or folders possibly containing image files
- A possible implementation of this is a GUI component with a list of currently selected files/folders, and a tree structured GUI file/folder selector dialog that allows a single selection of an img file or folder, to add to the list 

- The app will allow for a single list/collection of files/folders, but also allow for two collections of image files, with the first being the "reference" image files, and the second the collection of files/paths to operate on.
- For example, if searching for similar images:
  - The app would allow a single collection of image files to search & group similar images
  - But it would also allow for a reference set of image files, and a targets set of image files, that are searched for images similar in group 1

### Similar Image Search

- The app provides a GUI image file selector that allows the user to select a set of image files/folders to search/compare/group for similar images
- The app will also offer the option to choose two sets of image files - the first as a reference set, the second the files to search for similar images to those in the first set
- The app will support/provide multiple image comparison algorithms/methods, such as pHash, dHash, etc. Future methods will include AI LLMs
- The app will allow the user to specify the degree/threshold of similarity, shown in the UI as 0-100% (internally stored as 0.0-1.0 per canonical convention)
- When the image sets are selected, the user will initiate the similarity search
- The result of the similarity search will present groups of similar images within the threshold.
- The left side of the results pane will contain the groups. Each group will have a group header, & list all files within the group, with full path, file size, resolution, modification date, & similarity score.
- The right side of the results pane will provide image previews. Selecting a group header will preview all images of the group, selecting a single image from a group will preview just that image
- Each listed image in a group will provide a select/checkbox to delete that image/file
- The results pane will provide a "Delete Now" button to delete the selected files

### Caching Strategy
- Image thumbnails cached in the application cache folder (platformdirs user_cache_dir or PK_IMG_APP_HOME/cache)
- Thumbnails stored as files under cache/thumbnails/{size}/; the database stores metadata and relative paths
- Maximum cache size user configurable, initial/default size 5GB
- Cache invalidation by absolute_path, file_size, mtime_ns (nanoseconds), and inode (where available)
- Thumbnails on demand
- Provide user options to clear cache & clean/verify/validate cache

### Database Schema Approach
- Use SQLite for persistent data with three databases: settings.db, sessions.db, cache.db
- Data locations via platformdirs (Vendor "Pk", App "Img App"); support PK_IMG_APP_HOME override
- Each database contains a meta table with schema_version
- On startup run PRAGMA quick_check; if it fails run PRAGMA integrity_check; if corrupt:
  - settings.db: attempt to export/preserve settings then rebuild
  - sessions.db: prompt to rebuild or attempt repair
  - cache.db: safe to auto-rebuild
- Implement Alembic migrations on schema_version mismatch; create timestamped backup before migrating
- Backup retention: keep 10 most recent per database; purge backups older than 30 days
- File identity strategy: robust move/rename detection using SHA-256 content hash and, where available, (device, inode); do not treat moved/renamed files as new when content hash matches
- Image file paths are absolute, not relative

### Memory Management
- Use lazy loading for large result sets
- Implement memory usage monitoring & warning

### Error Handling & Recovery
- All errors should be logged and reported to the user, but ignored when possible & execution should continue
- Basic attempt of recovery of corrupt databases

Ask if you want additional clarification
