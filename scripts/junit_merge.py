"""Merge JUnit files into one (the named-test check reads a single junit.xml). Usage: junit_merge.py OUT IN..."""

import sys
import xml.etree.ElementTree as ET

root = ET.Element("testsuites")
for f in sys.argv[2:]:
    root.extend(ET.parse(f).getroot().iter("testsuite"))
ET.ElementTree(root).write(sys.argv[1])
