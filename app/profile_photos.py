"""Validated, re-encoded student avatars stored outside public static files."""
from pathlib import Path
from io import BytesIO
from flask import current_app

def photo_path(user_id):
    return Path(current_app.instance_path)/'profile-photos'/f'{int(user_id)}.jpg'

def prepare_photo(stream):
    from PIL import Image,ImageOps,UnidentifiedImageError
    data=stream.read(2*1024*1024+1)
    if not data or len(data)>2*1024*1024:raise ValueError('Choose a photo smaller than 2 MB.')
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in ('JPEG','PNG','WEBP') or source.width*source.height>16000000:raise ValueError('Choose a JPG, PNG or WebP photo up to 16 megapixels.')
            source.load();image=ImageOps.fit(ImageOps.exif_transpose(source).convert('RGB'),(512,512))
            output=BytesIO();image.save(output,'JPEG',quality=88);return output.getvalue()
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as error:raise ValueError('The uploaded file is not a valid photo.') from error
