# GUI File Selector Widgets

## Goal

Two collaborative interactive GUI widgets to select multiple file system paths

### File/Folder/Path selector widget

The Path selector widget should be a modal dialog to implement a tree view of the file system to allow the selection of a single path - directory or file

The path selector widget should be configurable to filter file types shown based on file extensions with white lists ('jpg','gif') (only show files with these extensions), black lists ('sys', 'exe')  - EXCLUDE files with these extensions, or named types/categories ('audio', 'video') - both white and black lists.

### Multi Path Selector

The multi-path selector should contain a list of multiple file system paths.
Each path should have a "delete" option to remove the path from the list
It should use the above path selector widget to add individual paths
Before a new path is added to the path list, it should use the core library file system utilities to ensure:

- The new path exists
- The new path is not already in the list
- The new path is not contained within any subdirectories of the existing list

If there are any errors, the widget will inform the user and prompt for retry.
 
