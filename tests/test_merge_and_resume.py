import os
from pathlib import Path
import tempfile

import pytest

from main import merge_segment_files, compute_range_start


def test_merge_segments_and_cleanup():
    with tempfile.TemporaryDirectory() as td:
        segs = []
        contents = [b'AAA', b'BBBB', b'CCCCCCCC']
        for i, c in enumerate(contents):
            p = os.path.join(td, f"seg-{i}.part")
            with open(p, 'wb') as f:
                f.write(c)
            segs.append(p)
        dest = os.path.join(td, "out.bin")
        merge_segment_files(dest, segs, cleanup=True)
        # Check file content
        with open(dest, 'rb') as f:
            data = f.read()
        assert data == b''.join(contents)
        # segs should be removed
        for p in segs:
            assert not os.path.exists(p)


def test_compute_range_start_with_existing_file():
    with tempfile.TemporaryDirectory() as td:
        outpath = os.path.join(td, "part.bin")
        with open(outpath, 'wb') as f:
            f.write(b'X' * 1234)
        # start at 100 -> should return 100 + existing
        rs = compute_range_start(100, outpath)
        assert rs == 100 + 1234


def test_compute_range_start_none():
    assert compute_range_start(None, "does_not_matter") is None
