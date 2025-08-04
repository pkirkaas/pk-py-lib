# Example Application

The following instructions add additional components/functionality to the project described in the `architecture-plan.md` document.

Review the instructions that follow. If they are clear, unambiguous, and seem reasonable, devise a careful, step by step plan to implement the request, update the `architecture-plan.md` document with the new functionality & approach, and create a new, detailed, step by step implementation plan called `/docs/add-app-plan.md`

## Goal

Create a new top level `/img_app/` folder, on the same level as the existing `/showcase` & `/src` folders. This folder should contain the source code for a full image comparison application that uses the library components defines in the `/src/` folder.

This `img_app` application is included in this library project just for development purposes, to allow quicker development & debugging of the library and application at the same time in the same project. Ultimately the code for the `img_app` will be moved into a separate repository and import reusable library components, so the code for the img_app should reflect that future.

## Structure

The structure of the `img_app` application subfolder should conform to best practices, 

## Invocation

The `pyproject.toml` `[tool.pdm.scripts]` section should include a new runnable command invoked from the terminal by `pdm run imgapp`, which launches the img_app

## Development Process
The application will be developed incrementally, step by step. The first step is to implement the main application window. The application title bar should be labeled "KDC Image Organizer"

The application should have a standard application menu - initially `File`, `View`, `Help`, which initially don't need to do anything.

The first/demo application window/body can just contain the centered text "The KDC Image Organizer will go here"
