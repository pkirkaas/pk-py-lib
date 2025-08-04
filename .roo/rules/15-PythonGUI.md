# Python GUI

The project will support both terminal/CLI interface, as well as a Windowed Desktop GUI, built with `PySide6` QT GUI library. 


The project source code will include a src/lib library folder which implements all the shared project functionality which will be provided to both the GUI & CLI interfaces.

There will also be a src/cli subfolder containing all the CLI code/functionality.

There will also be a src/gui subfolder with all the GUI application & widget code.

## GUI widget/component rules
All the GUI components should be as modular as possible, as configurable as possible, as reusable as possible.

Widgets should be designed/implemented to be included/used in a containing widget or main app window

Widgets should both receive and return data to the enclosing parent widget/component.

The widgets & containing widgets/components should be designed so the containing widget can contain multiple instances of the contained widget, which operate independently. For example, if we implement a file selector widget, the containing app/widget window should be able to include 2 instances of the file selector widgets, separately configurable, and maintain separate states/data, etc.



