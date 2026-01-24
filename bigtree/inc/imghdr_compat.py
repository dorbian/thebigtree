"""Python 3.13 compatibility shim for removed imghdr module."""

def what(file, h=None):
    """Detect image type from file or bytes."""
    if h is None:
        if isinstance(file, (str, bytes)):
            with open(file, 'rb') as f:
                h = f.read(32)
        else:
            h = file.read(32)
            file.seek(0)
    
    # Check common image formats by magic numbers
    if h[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    elif h[:3] == b'\xff\xd8\xff':
        return 'jpeg'
    elif h[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    elif h[:2] in (b'BM', b'BA'):
        return 'bmp'
    elif h[:4] == b'RIFF' and h[8:12] == b'WEBP':
        return 'webp'
    return None
