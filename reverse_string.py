def reverse_string(s):
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
    return s[::-1]
