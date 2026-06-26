from reverse_string import reverse_string


def test_normal_string():
    assert reverse_string("hello") == "olleh"


def test_empty_string():
    assert reverse_string("") == ""


def test_single_character():
    assert reverse_string("a") == "a"


def test_palindrome():
    assert reverse_string("racecar") == "racecar"
