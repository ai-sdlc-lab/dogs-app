"""Merge JUnit files into one (the named-test check reads a single junit.xml). Usage: junit_merge.py OUT IN...

The inputs come from PR-controlled tests, so they are parsed as named_tests.py does: at most 5 MiB,
no DOCTYPE or entity declarations (no XXE, no entity expansion); any violation fails.
"""

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_BYTES = 5 * 1024 * 1024
FORBIDDEN = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


def load(path: str) -> ET.Element:
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BYTES or FORBIDDEN.search(raw):
        sys.exit(f"{path}: refused (larger than 5 MiB, or a DOCTYPE/entity declaration)")
    return ET.fromstring(raw)


root = ET.Element("testsuites")
for f in sys.argv[2:]:
    root.extend(load(f).iter("testsuite"))
ET.ElementTree(root).write(sys.argv[1])
