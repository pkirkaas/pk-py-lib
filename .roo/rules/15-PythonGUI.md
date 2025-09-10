# Python GUI

The project will support both terminal/CLI interface, as well as a Windowed Desktop GUI, built with `PySide6` QT GUI library. 


The project source code will include a src/lib library folder which implements all the shared project functionality which will be provided to both the GUI & CLI interfaces.

There will also be a src/cli subfolder containing all the CLI code/functionality.

There will also be a src/gui subfolder with all the GUI application & widget code.

## Selectable Text in ALL Dialogs
All dialog/message/error/GUI pop ups with message/error texts should be selectable/copyable by the mouse/GUI. 

It is VERY important to be able to copy/paste error dialog text messages for debugging/diagnostics

## Error/Warning Reporting/Logging
ALL errors and warnings in the GUI should be reported in the GUI with an appropriate error dialog, or within the appropriate GUI component.  

FURTHERMORE - ALL errors/warnings occurring in the GUI should be reported in MUCH greater detail to `STDERR` - the terminal or whatever designated STDERR output. 

The error details to STDERR must include AT LEAST the following:
- The full error text/description
- The full file path of the component where the error occurred.
- The parameters/values that caused the error
- The call stack that led to the error.



## GUI widget/component rules
All the GUI components should be as modular as possible, as configurable as possible, as reusable as possible.

Widgets should be designed/implemented to be included/used in a containing widget or main app window

Widgets should both receive and return data to the enclosing parent widget/component.

The widgets & containing widgets/components should be designed so the containing widget can contain multiple instances of the contained widget, which operate independently. For example, if we implement a file selector widget, the containing app/widget window should be able to include 2 instances of the file selector widgets, separately configurable, and maintain separate states/data, etc.

## Images included in chat prompts for RooCode
Images may be included in a Roo chat prompt. If the text prompt does not specifically identify what that image is or describe it, your default assumption should be that it is a screenshot of the current GUI implementation that needs to be fixed/changed.

