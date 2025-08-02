When generating Python code, you MUST follow this validation workflow:

1. **Generate the initial code** based on the user's requirements
2. **Syntax Check**: Before presenting any Python code to the user, validate it using Python's ast module
3. **Error Handling**: If syntax errors are found:
   - Fix the errors automatically
   - Explain what was wrong and how it was fixed
   - Present only the corrected version
4. **Verification**: Confirm the final code is syntactically valid
5. **Documentation**: Include a brief comment indicating syntax validation was performed

Never present Python code that hasn't been syntax-validated.
