from io import BytesIO
from typing import TYPE_CHECKING, Optional

import graphene
import magic
from django.core.files.storage import default_storage
from django.urls import reverse
from PIL import Image

from . import (
    DEFAULT_THUMBNAIL_SIZE,
    MIME_TYPE_TO_PIL_IDENTIFIER,
    THUMBNAIL_SIZES,
    ThumbnailFormat,
)

if TYPE_CHECKING:
    from .models import Thumbnail


def get_image_or_proxy_url(
    thumbnail: Optional["Thumbnail"],
    instance_id: str,
    object_type: str,
    size: int,
    format: Optional[str],
):
    """Return the thumbnail ULR if thumbnails is provided, otherwise the proxy url."""
    return (
        prepare_image_proxy_url(instance_id, object_type, size, format)
        if thumbnail is None
        else thumbnail.image.url
    )


def prepare_image_proxy_url(
    instance_pk: str, object_type: str, size: int, format: Optional[str]
):
    instance_id = graphene.Node.to_global_id(object_type, instance_pk)
    kwargs = {"instance_id": instance_id, "size": size}
    if format and format.lower() != ThumbnailFormat.ORIGINAL:
        kwargs["format"] = format.lower()
    return reverse("thumbnail", kwargs=kwargs)


def get_thumbnail_size(size: Optional[int]) -> int:
    """Return the closest size to the given one of the available sizes."""
    if size is None:
        requested_size = DEFAULT_THUMBNAIL_SIZE
    else:
        requested_size = size
    if requested_size in THUMBNAIL_SIZES:
        return requested_size

    return min(THUMBNAIL_SIZES, key=lambda x: abs(x - requested_size))


def get_thumbnail_format(format: Optional[str]) -> Optional[str]:
    """Return the thumbnail format if it's supported, otherwise None."""
    if format is None:
        return None

    format = format.lower()
    if format == ThumbnailFormat.ORIGINAL:
        return None

    return format


def prepare_thumbnail_file_name(
    file_name: str, size: int, format: Optional[str]
) -> str:
    file_path, file_ext = file_name.rsplit(".", 1)
    file_ext = format or file_ext
    return file_path + f"_thumbnail_{size}." + file_ext


class ProcessedImage:
    EXIF_ORIENTATION_KEY = 274
    # Whether to create progressive JPEGs. Read more about progressive JPEGs
    # here: https://optimus.io/support/progressive-jpeg/
    PROGRESSIVE_JPEG = False
    # If true, instructs the WebP writer to use lossless compression.
    # https://pillow.readthedocs.io/en/latest/handbook/image-file-formats.html#webp
    # Defaults to False
    LOSSLESS_WEBP = False
    # The save quality of modified JPEG images. More info here:
    # https://pillow.readthedocs.io/en/latest/handbook/image-file-formats.html#jpeg
    JPEG_QUAL = 70
    # The save quality of modified WEBP images. More info here:
    # https://pillow.readthedocs.io/en/latest/handbook/image-file-formats.html#webp
    WEBP_QUAL = 70
    AVIF_QUAL = 70

    def __init__(
        self,
        image_path: str,
        size: int,
        format: Optional[str] = None,
        storage=default_storage,
    ):
        self.image_path = image_path
        self.size = size
        self.format = format
        self.storage = storage

    def create_thumbnail(self):
        image, image_format = self.retrieve_image()
        image, save_kwargs = self.preprocess(image, image_format)
        image_file = self.process_image(
            image=image,
            save_kwargs=save_kwargs,
        )
        return image_file

    def retrieve_image(self):
        """Return a PIL Image instance stored at `image_path`."""
        image = self.storage.open(self.image_path, "rb")
        image_format = 