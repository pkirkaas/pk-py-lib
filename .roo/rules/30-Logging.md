# Logging

It is essential to implement several logging solutions. The most basic required is file logging:

- In the project root, ensure the subdirectory `logs` exists
- Ensure the top level `.gitignore` excludes the `logs` directory

## Terminal/Command Line invocation file logging

File based logging should be implemented for every invocation of the application from the terminal, whether by a python script, invoked via `pdm run ...` or whatever.

- The name of the logfile should be `/logs/[app-name]-terminal.log`
- Upon each invocation, the application should check for the existence of the logfile name.
- If the logfile exists, the application should rename/move it by adding the timestamp to the logfile basename
- A new logfile with the appropriate name should be created
- The first line of the newly created logfile should be the full terminal invocation command, with all parameters and arguments
- The second line of the new logfile should be a fully formatted, human friendly date & time stamp, followed by a blank newline
- EVERY ERROR/WARNING encountered during the execution should be recorded to the log, with the call stack, line number, file name, function/method name, parameters, etc.


