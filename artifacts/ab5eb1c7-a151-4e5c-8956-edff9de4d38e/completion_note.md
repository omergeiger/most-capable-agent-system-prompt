# Task Completion Note

**Task:** ab5eb1c7-a151-4e5c-8956-edff9de4d38e  
**Description:** Write a Google-style docstring for `reverse_string`

## What was done

Drafted a Google-style docstring for `reverse_string` in `reverse_string.py`. No file edits were made (per scope).

## Docstring text

```python
"""Returns the reverse of the given string.

Args:
    s (str): The string to reverse.

Returns:
    str: A new string with the characters of `s` in reverse order.

Examples:
    >>> reverse_string("hello")
    'olleh'
    >>> reverse_string("")
    ''
"""
```

## Verification

- Args section: present (`s (str)`)
- Returns section: present (`str`)
- Example: present (two cases including edge case empty string)
- Format: PEP 257 triple-quote, Google style
- No function logic or type hints were added or changed
