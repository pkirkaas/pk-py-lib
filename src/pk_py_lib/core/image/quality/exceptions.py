"""
src/pk_py_lib/core/image/quality/exceptions.py

Custom exceptions for the image quality evaluation subsystem.

These exceptions provide a hierarchy for handling various errors during image quality assessment,
including file-related issues and computation failures. All exceptions include optional path and
original error details for informative error reporting and logging.
"""

from typing import Optional


class ImageQualityError(Exception):
    """Base exception for all image quality evaluation errors.

    This is the root of the exception hierarchy for the image quality subsystem.
    Subclasses provide more specific error types. Intended to be raised by evaluators
    when general quality assessment fails, with details for debugging.

    Parameters
    ----------
    message : str
        A descriptive error message explaining the failure.
    path : str, optional
        The file path associated with the error, if applicable (e.g., the image being evaluated).
    original_error : Exception, optional
        The underlying exception that caused this error, if any (e.g., an OpenCV or OS error).

    Attributes
    ----------
    path : str or None
        The file path, if provided during initialization.
    original_error : Exception or None
        The original error, if provided.

    Raises
    ------
    This class itself should not be raised directly; use subclasses for specificity.

    Examples
    --------
    # General usage in an evaluator
    raise ImageQualityError("Failed to evaluate image quality due to invalid format", path="/path/to/image.jpg")

    # With original error
    try:
        # Some computation
        pass
    except Exception as e:
        raise ImageQualityError("Computation failed", path="/path/to/image.jpg", original_error=e)
    """
    def __init__(self, message: str, path: Optional[str] = None, original_error: Optional[Exception] = None) -> None:
        # Initialize base exception with message
        super().__init__(message)
        # Store path for context in error reporting
        self.path = path
        # Store original error for chain-of-responsibility debugging
        self.original_error = original_error

    def __str__(self) -> str:
        # Build string representation with additional context
        base = super().__str__()
        # Append path if available for traceability
        if self.path:
            base += f" (path: {self.path})"
        # Append original error details if present
        if self.original_error:
            base += f"; original: {self.original_error}"
        return base


class ImageQualityFileError(ImageQualityError):
    """Raised for file-related errors in image quality evaluation, such as missing files, read failures, or unsupported formats.

    This exception is specific to issues with accessing or loading the image file before quality computation.
    It inherits from ImageQualityError and should be raised when file operations fail.

    Parameters
    ----------
    message : str
        A descriptive error message (e.g., "File not found or unreadable").
    path : str, optional
        The problematic file path.
    original_error : Exception, optional
        The underlying file system or I/O error (e.g., FileNotFoundError, PermissionError).

    Raises
    ------
    ImageQualityFileError
        Raised explicitly in file validation steps.

    Examples
    --------
    # In file validation
    if not os.path.exists(path):
        raise ImageQualityFileError("Image file not found", path=path)

    # With original OS error
    try:
        with open(path, 'rb') as f:
            # Check file
            pass
    except IOError as e:
        raise ImageQualityFileError("Failed to read image file", path=path, original_error=e)
    """
    # Inherits __init__ and __str__ from ImageQualityError
    # No additional attributes or methods needed for this subclass
    pass


class ImageQualityComputationError(ImageQualityError):
    """Raised for errors during the computation of image quality scores, such as OpenCV processing failures, corrupted images, or model loading issues.

    This exception is specific to failures in the quality metric calculation after successful file loading.
    It inherits from ImageQualityError and should be raised when algorithmic computation fails.

    Parameters
    ----------
    message : str
        A descriptive error message (e.g., "BRISQUE model computation failed due to invalid image data").
    path : str, optional
        The file path of the image that failed computation.
    original_error : Exception, optional
        The underlying computation error (e.g., cv2.error, ValueError from metric library).

    Raises
    ------
    ImageQualityComputationError
        Raised explicitly in the evaluate method during score calculation.

    Examples
    --------
    # In evaluator compute step
    try:
        score = brisque.compute(image)
    except cv2.error as e:
        raise ImageQualityComputationError("Failed to compute quality score", path=path, original_error=e)

    # For corrupted image data
    if image is None or image.size == 0:
        raise ImageQualityComputationError("Loaded image is empty or corrupted", path=path)
    """
    # Inherits __init__ and __str__ from ImageQualityError
    # No additional attributes or methods needed for this subclass
    pass


__all__ = [
    "ImageQualityError",
    "ImageQualityFileError",
    "ImageQualityComputationError"
]