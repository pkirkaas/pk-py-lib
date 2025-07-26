These are the general software coding guidelines for every software development project

The development environment is a Windows 11 Pro machine, but the shells used are always `bash` - either Cygwin Bash, or WSL Bash.

## Style Guidelines
- Code indentation level is 2 spaces - except for Python, which uses 4 spaces
- Code should be as compact as possible
- Code should have rich, detailed, explanatory comments throughout
- All function/class/etc components should be fully documented with JSDoc/PyDoc/TSDoc comments FULLY AND DETAILED, with FULL description of all parameters, types, purpose, return, usage explanation & examples, etc.
- Functions/etc can be overloaded - with different behaviors & parameters - all possible overloads should be documented

## Coding Guidelines
- Projects are in early development/proof of concept phase, implemented by a single developer. Therefore:
- Whenever possible, use standard, 3rd party libraries/packages (pip,npm) to implement functionality - don't reinvent the wheel.
- Since these are in development, backwards compatibility is not an issue. Assume the latest versions of Python3, Node, and all libraries and packages.
- Since these projects are in development/PoC, production issues are not a concern.
- Since these projects are in development/PoC, performance optimization & speed of execution are not a concern.
- Since these projects are in development/PoC, logical & architectural elegance are a top priority.
- Since these projects are in development/PoC, prefer simplicity and clarity over complexity and performance.
- All code, functions, classes, etc, should be as generic & reusable as possible - with optional parameters for flexibility, but reasonable defaults for simplicity.
- Edge cases should be handled & considered. 
- All possible errors should be considered and should throw full, informative exceptions with all relevant details.
- Since these projects are in development and not production, errors/exceptions do not need to be handled elegantly - just reported in the terminal/console with all possible details required for debugging.

## Artifact/Code Creation Guidelines
- Every work product created - GUI component, function, class, etc, should be reusable and exportable to other projects/circumstances.
- Work Products (for example, a GUI Component) should be able to be used in multiple instances/places in the projects. This requires considerable modularization and effort to allow work products to communicate/share data, etc.
- Each artifact (GUI component, function, class, etc) should be as flexible as possible and as configurable as possible, to anticipate all possible future use-cases. 
- Each artifact should accept multiple custom configuration options/parameters, but provide reasonable defaults for as much as possible.

## Accuracy, correctness & completeness
- Correct, elegant, well thought out, error free code is essential
- Speed of response is not
- You will think through the question & your response very carefully, step by step, before proposing/implementing a solution.
- IT IS VITAL YOU ARE A Responsible Senior Developer Partner & Advisor!
- Carefully analyze the task and evaluate my proposed approach - DO NOT BLINDLY FOLLOW MY INSTRUCTIONS! If my proposed approach/design seems poor or you have any concerns, identify your concerns to me before implementing anything, and propose alternative approaches.
- If ANY of the task description is unclear or incomplete, you will ask for clarification before proceeding
- You will ask any clarifying questions required before responding. 

## Your implementation of user coding/design instructions
- The user (me) will provide coding/architectural instructions/specifications
- Before implementation, you should review the proposed design/approach carefully, and provide feedback/suggestions/improvements of the user's suggested implementation.
- Ensure the development plan is complete, comprehensive, and robust before implementation, through interactive dialog if necessary for clarification. 

## Implementing Tasks defined in `./.roo/tasks/` subfolder
- If the `./.roo/tasks/` subfolder exists, it will contain one or more numbered task.md files
- 