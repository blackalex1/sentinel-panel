import os
from pathlib import Path

def read_last_lines(file_path: Path | str, limit: int = 1000) -> list[str]:
    """
    Reads the last N lines of a file efficiently by seeking backwards from the end.
    Avoids reading the entire file into memory (OOM safe).
    """
    path = Path(file_path)
    if not path.exists():
        return []
        
    try:
        file_size = path.stat().st_size
    except Exception:
        file_size = 0
        
    if file_size == 0:
        return []
        
    # We estimate line length is around 256 bytes.
    # We read a chunk that should contain more than `limit` lines.
    # If the file is smaller than that chunk, we just read the whole thing.
    chunk_size = min(file_size, max(4096, limit * 256))
    
    try:
        with open(path, "rb") as f:
            f.seek(-chunk_size, os.SEEK_END)
            data = f.read(chunk_size)
            
        text = data.decode("utf-8", errors="ignore")
        lines = text.splitlines()
        
        # If we didn't read the whole file, the first line in our chunk is likely incomplete/cut off,
        # so we discard it to avoid partial log lines.
        if chunk_size < file_size and lines:
            lines.pop(0)
            
        return lines[-limit:]
    except Exception:
        # Fallback to reading the whole file if seek fails
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return [line.rstrip("\r\n") for line in f.readlines()[-limit:]]
        except Exception:
            return []
