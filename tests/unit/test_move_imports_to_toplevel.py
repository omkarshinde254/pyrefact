#!/usr/bin/env python3


import sys
from pathlib import Path

from pyrefact import fixes

sys.path.append(str(Path(__file__).parents[1]))
import testing_infra


def main() -> int:
    test_cases = (
        (
            """
#!/usr/bin/env python3
'''docstring'''
import time
import os
import sys

sys.path.append(os.getcwd())
from somewhere import something

def function_call():
    from somewhere import something_else
    return something_else()

def call2():
    from somewhere_else import qwerty
    return qwerty()

def call3():
    import math
    print(math.sum([3]))
            """,
            """
#!/usr/bin/env python3
'''docstring'''
import time
import os
import sys
import math

sys.path.append(os.getcwd())
from somewhere import something
from somewhere import something_else

def function_call():
    return something_else()

def call2():
    from somewhere_else import qwerty
    return qwerty()

def call3():
    print(math.sum([3]))
            """,
        ),
        (
            """
import os
from numpy import (
    integer, ndarray, dtype as _dtype, asarray, frombuffer
)
from numpy.core.multiarray import _flagdict, flagsobj
def foo():
    from numpy import intp as c_intp
    print(199)
def woo():
    from numpy import intp as c_intp
    print(199)
def hoo():
    from numpy import intp as c_intp
    print(199)
            """,
            """
import os
from numpy import intp as c_intp
from numpy import (
    integer, ndarray, dtype as _dtype, asarray, frombuffer
)
from numpy.core.multiarray import _flagdict, flagsobj
def foo():
    print(199)
def woo():
    print(199)
def hoo():
    print(199)
            """,
        ),
    )

    for source, expected_abstraction in test_cases:
        processed_content = fixes.move_imports_to_toplevel(source)
        if not testing_infra.check_fixes_equal(processed_content, expected_abstraction):
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
