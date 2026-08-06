import os
import pytest
from pathlib import Path
from backend.utils import read_last_lines

def test_read_last_lines_nonexistent():
    assert read_last_lines("nonexistent_file_xyz.log", 10) == []

def test_read_last_lines_empty(tmp_path):
    empty_file = tmp_path / "empty.log"
    empty_file.touch()
    assert read_last_lines(empty_file, 10) == []

def test_read_last_lines_small(tmp_path):
    small_file = tmp_path / "small.log"
    lines = [f"Line {i}" for i in range(1, 11)]
    small_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    
    # Request fewer lines than exist
    assert read_last_lines(small_file, 5) == lines[-5:]
    
    # Request exactly the number of lines that exist
    assert read_last_lines(small_file, 10) == lines
    
    # Request more lines than exist
    assert read_last_lines(small_file, 20) == lines

def test_read_last_lines_large(tmp_path):
    # Create a larger file to trigger seek-back logic (chunk_size < file_size)
    large_file = tmp_path / "large.log"
    # Write 2000 lines, total size will be ~30KB
    lines = [f"Line {i} with some dummy data to make it longer and verify correctness of seeking" for i in range(1, 2001)]
    large_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    
    # read_last_lines has chunk_size = min(file_size, max(4096, limit * 256))
    # For limit=10, chunk_size = max(4096, 2560) = 4096 bytes.
    # 30KB is larger than 4KB, so it will seek and read from the end.
    read_lines = read_last_lines(large_file, 10)
    assert len(read_lines) == 10
    assert read_lines == lines[-10:]
    
    # Test reading larger amount (e.g. 500 lines)
    # chunk_size = max(4096, 500 * 256) = 128000 bytes, which is larger than file size, so it reads the whole file
    read_lines_500 = read_last_lines(large_file, 500)
    assert len(read_lines_500) == 500
    assert read_lines_500 == lines[-500:]

def test_is_safe_url_ssrf():
    import socket
    from backend.auth_utils import is_safe_url
    
    # 1. Loopback / Private IP addresses -> False
    assert is_safe_url("http://127.0.0.1/test") is False
    assert is_safe_url("http://10.0.0.1/test") is False
    assert is_safe_url("http://192.168.1.1/test") is False
    assert is_safe_url("http://169.254.169.254/latest/meta-data/") is False

    # 2. Invalid or unresolvable hostname -> False (SSRF guard default deny)
    assert is_safe_url("http://this-domain-does-not-exist-123456789.invalid/") is False

    # 3. Empty or malformed URL -> False
    assert is_safe_url("") is False
    assert is_safe_url("not_a_url") is False

