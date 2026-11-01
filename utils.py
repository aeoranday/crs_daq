"""
Utility functions that may be used anywhere.
"""

def datetime_now() -> str:
    """ Return a string with the common datetime format. """
    from time import strftime
    return strftime("%Y_%m_%d_%H_%M_%S_%Z")
