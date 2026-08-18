import re

import index_graph


def test_version_is_semver():
    # Read the real version rather than pin a literal: the string is bumped every
    # release and a hardcoded assertion just breaks the build on the bump commit.
    assert re.fullmatch(r"\d+\.\d+\.\d+", index_graph.__version__)
