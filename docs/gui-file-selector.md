# GUI File Selector Widgets

## Goal

Two collaborative interactive GUI widgets to select multiple file system paths

### File/Folder/Path selector widget

- The Path selector widget should be a modal dialog to implement a tree view of the file system to allow the selection of a single path - directory or file

- The path selector widget should be configurable to filter file types shown based on file extensions with white lists ('jpg','gif') (only show files with these extensions), black lists ('sys', 'exe')  - EXCLUDE files with these extensions, or named types/categories ('audio', 'video') - both white and black lists.
- On Windows, the root drive entries must be displayed in ascending alphabetical order by drive letter to maintain consistency with native file explorers.

- The initial/default width of the PathSelectorDialog widget should be 100% of the width of the containing application window
- The width of the table should be 100% of available space in the containing box
- The total width of all the columns in the table should fill all the available width of the table/container
- The initial width of the `Name` column of the PathSelectorDialog should expand to take all of the table width not taken by the `Size`, `Type` & `Date Modified` columns
- All the columns & column data in the table should be separated by a thin, light gray line
- The OK/Accept action must validate the current selection, dismiss the dialog when valid, and propagate the chosen path back to the invoker (e.g., Edit Pool Paths workflow).

### Multi Path Selector

The multi-path selector should contain a list of multiple file system paths.
Each path should have a "delete" option to remove the path from the list
It should use the above path selector widget to add individual paths
Before a new path is added to the path list, it should use the core library file system utilities to ensure:

- The new path exists
- The new path is not already in the list
- The new path is not contained within any subdirectories of the existing list
- The new path itself does not contain any of the existing paths in the list

If there are any errors, the widget will inform the user and prompt for retry.

