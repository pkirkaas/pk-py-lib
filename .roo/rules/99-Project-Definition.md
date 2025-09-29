# Pk-Py-Lib & img-app project definitions

@/architecture-plan.md

@/pyproject.toml

IMPORTANT!! Refer to/read the project specification and progress documents in `/docs` & `/docs/roo` and update them to reflect all changes made to the project requirements, specifications, and progress!!

The application/library should support multi-platform - Windows, Mac, Linux - but the primary platform is modern Windows 10/11.

## Standard Libraries/Packages
- If the requested functionality/instruction is best supported by installing an open source 3rd party library/package available from standard Python/Pip package providers, feel free to add them & update the `pyproject.toml` file.

- The criteria for added packages are they should be current, maintained, and widely used. If in doubt, ask. 


## Objective

This is a Python project, with two primary components that will eventually be separated into two separate projects:

- A library of re-usable, exportable Python GUI Components, Classes, Functions, etc, that will be imported by other Python projects. 
- A GUI `img_app` image organizing desktop application which imports/implements functionality from the library
- All generic, reusable functionality should be added to the library
- Code specific for the application should be added to the img_app application, and import functionality from the library

- The focus of the library will be to support manipulating huge collections of images - modify them, classify them, detect duplicates, detect features, etc.
- All these functionalities will be available to GUI Windowed Desktop Applications, API Web based services, CLI/terminal applications, etc

- You will NOT simply execute requests, but evaluate requests against general project goals and suggest alternative approaches if appropriate

- If any request is unclear, incomplete or ambiguous, you will require full clarification before proceeding, rather than making a best guess 

- The included `architecture-plan.md` document is a general project guideline

- You will update the `architecture-plan.md` on an ongoing basis to reflect refinements determined during chat interactions

- You will update the specification/requirements/design documents in `/docs` on an ongoing basis to reflect refinements determined during chat interactions

## Libraries

We have the latest version of the `opencv-contrib-python` image processing library installed. Ensure you consider all available contributed modules in `opencv-contrib-python` when choosing/implementing image processing features. Consider all other installed python image processing libraries as well, and select the most appropriate library to implement desired image processing functionality. 

## Run the application in the terminal after changes to code
When you complete a task that makes changes to the code, run the app in the VSCode terminal with the command `pdm run imgapp` and monitor the terminal output and logs to identify errors/results.

## Adding CLI Options/Arguments

When asked to add a CLI option, add it to the `img_app/app.py` `main` function. Assure that options/parameters are passed both when invoking the application from the `imgapp` script AND the `pdm run imgapp` command in `pyproject.toml`

## GUI Component Definitions
The project has many GUI components - here are some definitions I will use when requesting GUI changes:
- `Results Dialogs` - the results dialogs that appear after running the comparison. There are two sublcasses, for similarity results & duplicate results
- `Similar Image Manager` - the dialog that pops up after running the similar image finder 
- `Duplicate File Manager` - the dialog after running duplicate finder
- Each results dialog is divided into vertical panes
- The top pane is `Summary Report Pane`, tabbed with "Summary" & "Report"