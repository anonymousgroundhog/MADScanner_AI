#!/usr/bin/env python3
"""
Open WebUI API Script for PDF-based Chat

This script allows users to interact with Open WebUI API by providing:
- An API key for authentication
- A prompt of their choice
- A PDF file to process
- Selection of model from available options

Usage:
    python openwebui_pdf_chat.py --api-key YOUR_API_KEY --prompt "Your prompt here" --pdf /path/to/file.pdf
"""

import argparse
import json
import sys
from io import BytesIO
from pathlib import Path

import requests

try:
    import PyPDF2
except ImportError:
    print("Error: PyPDF2 is required. Install with: pip install PyPDF2")
    sys.exit(1)

try:
    from PIL import Image, ImageEnhance
except ImportError:
    Image = None
    ImageEnhance = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    from pdf2image import convert_from_path
except ImportError:
    convert_from_path = None


def read_pdf_file(pdf_path: str) -> tuple[bytes, str]:
    """
    Read a PDF file and return its contents as bytes and filename.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Tuple of (file_bytes, filename)
    """
    path = Path(pdf_path)

    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"File must be a PDF, got: {path.suffix}")

    with open(path, "rb") as f:
        return f.read(), path.name


def is_text_quality_acceptable(text: str, min_readable_ratio: float = 0.3) -> bool:
    """
    Check if extracted text is mostly readable (not binary garbage).

    Args:
        text: The extracted text
        min_readable_ratio: Minimum ratio of readable characters (0.0-1.0)

    Returns:
        True if text quality is acceptable
    """
    if not text or len(text) < 10:
        return False

    # Count readable characters (letters, digits, common punctuation, whitespace)
    readable_chars = sum(
        1
        for c in text
        if c.isalnum()
        or c.isspace()
        or c in ".,!?;:\"-'()/&@#$%"
    )

    readable_ratio = readable_chars / len(text)
    return readable_ratio >= min_readable_ratio


def clean_extracted_text(text: str) -> str:
    """
    Clean extracted text by removing control characters and excessive symbols.

    Args:
        text: The raw extracted text

    Returns:
        Cleaned text
    """
    # Remove control characters but keep newlines and tabs
    cleaned = "".join(
        c if c.isprintable() or c in "\n\t\r" else "" for c in text
    )

    # Remove excessive repeated special characters
    import re

    cleaned = re.sub(r"([^\w\s])\1{3,}", r"\1\1", cleaned)

    return cleaned


def extract_images_from_pdf(pdf_bytes: bytes) -> list[tuple[int, bytes]]:
    """
    Extract images from PDF pages.

    Args:
        pdf_bytes: The PDF file contents as bytes

    Returns:
        List of tuples (page_number, image_bytes) in PNG format
    """
    if Image is None:
        raise ImportError(
            "Pillow is required for image extraction. Install with: pip install Pillow"
        )

    pdf_file = BytesIO(pdf_bytes)
    reader = PyPDF2.PdfReader(pdf_file)

    images = []

    for page_num, page in enumerate(reader.pages, 1):
        if "/XObject" not in page["/Resources"]:
            continue

        xObject = page["/Resources"]["/XObject"].get_object()

        for obj_name in xObject:
            obj = xObject[obj_name].get_object()

            if obj["/Subtype"] == "/Image":
                try:
                    # Extract image data
                    data = obj.get_data()
                    width = obj["/Width"]
                    height = obj["/Height"]

                    # Try to create PIL image
                    if obj["/ColorSpace"] == "/DeviceRGB":
                        image = Image.frombytes("RGB", (width, height), data)
                    elif obj["/ColorSpace"] == "/DeviceGray":
                        image = Image.frombytes("L", (width, height), data)
                    else:
                        # Skip unsupported color spaces
                        continue

                    # Convert to PNG bytes
                    png_bytes = BytesIO()
                    image.save(png_bytes, format="PNG")
                    images.append((page_num, png_bytes.getvalue()))

                except Exception:
                    # Skip problematic images
                    continue

    return images


def ocr_image(image_bytes: bytes) -> str:
    """
    Extract text from an image using OCR.

    Args:
        image_bytes: Image data in bytes

    Returns:
        Extracted text from the image
    """
    if pytesseract is None:
        raise ImportError(
            "pytesseract is required for OCR. Install with: pip install pytesseract\n"
            "Also install Tesseract: "
            "- Ubuntu/Debian: sudo apt-get install tesseract-ocr\n"
            "- macOS: brew install tesseract\n"
            "- Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki"
        )

    if Image is None:
        raise ImportError("Pillow is required. Install with: pip install Pillow")

    try:
        image = Image.open(BytesIO(image_bytes))
        text = pytesseract.image_to_string(image)
        return text.strip() if text else ""
    except Exception as e:
        raise ValueError(f"OCR failed: {str(e)}")


def pdf_to_images_optimized(
    pdf_path: str, dpi: int = 300, scale: float = 2.0
) -> list:
    """
    Convert PDF to images optimized for OCR.

    Args:
        pdf_path: Path to PDF file
        dpi: DPI for conversion (higher = better for OCR but slower)
        scale: Upscaling factor after conversion

    Returns:
        List of PIL Image objects
    """
    if convert_from_path is None:
        raise ImportError(
            "pdf2image is required. Install with: pip install pdf2image\n"
            "Also install poppler: sudo apt-get install poppler-utils (Linux) or brew install poppler (macOS)"
        )

    print(f"  Converting PDF to images at {dpi} DPI...")
    images = convert_from_path(pdf_path, dpi=dpi)

    print(f"  Preprocessing images for OCR (upscaling {scale}x and enhancing contrast)...")
    processed_images = []

    for i, image in enumerate(images, 1):
        # Upscale image for better OCR
        new_width = int(image.width * scale)
        new_height = int(image.height * scale)
        upscaled = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Enhance contrast
        enhancer = ImageEnhance.Contrast(upscaled)
        enhanced = enhancer.enhance(2.5)

        processed_images.append(enhanced)

        if i % 5 == 0:
            print(f"    Processed {i} pages...")

    print(f"  ✓ Processed {len(processed_images)} pages")
    return processed_images


def extract_text_from_images(pdf_path: str) -> tuple[str, dict]:
    """
    Extract text from a PDF using OCR (image-based approach).
    Works best for scanned documents or PDFs that are website screenshots.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Tuple of (extracted_text, metadata)
    """
    metadata = {
        "num_pages": 0,
        "quality_issues": [],
        "extraction_method": "OCR (pdf2image + Tesseract)",
        "images_processed": 0,
    }

    try:
        # Convert PDF to images with high quality
        images = pdf_to_images_optimized(pdf_path, dpi=300, scale=2.0)
        metadata["num_pages"] = len(images)

        print(f"  Running OCR on {len(images)} page(s)...")
        text_content = []

        for page_num, image in enumerate(images, 1):
            try:
                # Run OCR with optimized settings
                extracted_text = pytesseract.image_to_string(
                    image, config="--psm 6 --oem 3"
                )

                if extracted_text and len(extracted_text.strip()) > 0:
                    text_content.append(f"--- Page {page_num} (OCR) ---\n{extracted_text}")
                    metadata["images_processed"] += 1
                else:
                    metadata["quality_issues"].append(f"Page {page_num}: No text detected")

            except Exception as e:
                metadata["quality_issues"].append(
                    f"Page {page_num}: OCR failed - {str(e)}"
                )

        if not text_content:
            raise ValueError("OCR failed to extract text from any images")

        print(f"  ✓ OCR complete: Extracted text from {metadata['images_processed']} pages")

        if metadata["quality_issues"]:
            print(f"  ⚠️  Issues with {len(metadata['quality_issues'])} page(s)")

        return "\n\n".join(text_content), metadata

    except Exception as e:
        raise ValueError(
            f"Image-based OCR extraction failed: {str(e)}\n"
            "This may require: pip install pdf2image pytesseract Pillow\n"
            "And system package: sudo apt-get install poppler-utils tesseract-ocr"
        )


def extract_text_with_pdfplumber(pdf_bytes: bytes) -> tuple[str, dict]:
    """
    Extract text using pdfplumber (alternative method).

    Args:
        pdf_bytes: The PDF file contents as bytes

    Returns:
        Tuple of (extracted_text, metadata)
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError(
            "pdfplumber is not installed. Install with: pip install pdfplumber"
        )

    from io import BytesIO

    metadata = {
        "num_pages": 0,
        "quality_issues": [],
        "extraction_method": "pdfplumber",
    }

    try:
        pdf_file = BytesIO(pdf_bytes)

        text_content = []
        with pdfplumber.open(pdf_file) as pdf:
            metadata["num_pages"] = len(pdf.pages)

            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()

                if not text:
                    metadata["quality_issues"].append(f"Page {page_num}: No text extracted")
                    continue

                if not is_text_quality_acceptable(text):
                    metadata["quality_issues"].append(
                        f"Page {page_num}: Contains binary/encoded data (likely scanned image)"
                    )
                    text = f"[WARNING: Page {page_num} contains mostly binary data]\n{text}"
                else:
                    text = clean_extracted_text(text)

                text_content.append(f"--- Page {page_num} ---\n{text}")

        if not text_content:
            raise ValueError("No text could be extracted using pdfplumber")

        return "\n\n".join(text_content), metadata

    except Exception as e:
        raise ValueError(f"pdfplumber extraction failed: {str(e)}")


def extract_text_from_pdf(
    pdf_bytes: bytes, fallback_to_ocr: bool = True
) -> tuple[str, dict]:
    """
    Extract text content from a PDF file with quality checks and OCR fallback.

    Args:
        pdf_bytes: The PDF file contents as bytes
        fallback_to_ocr: Automatically try OCR if text extraction fails

    Returns:
        Tuple of (extracted_text, metadata)
        metadata contains: 'num_pages', 'quality_issues', 'extraction_method'
    """
    metadata = {
        "num_pages": 0,
        "quality_issues": [],
        "extraction_method": "PyPDF2",
    }

    try:
        pdf_file = BytesIO(pdf_bytes)
        reader = PyPDF2.PdfReader(pdf_file)

        metadata["num_pages"] = len(reader.pages)
        text_content = []
        pages_with_issues = 0
        pages_with_no_text = 0

        for page_num, page in enumerate(reader.pages, 1):
            text = page.extract_text()

            if not text:
                pages_with_no_text += 1
                metadata["quality_issues"].append(f"Page {page_num}: No text extracted")
                pages_with_issues += 1
                continue

            # Check text quality
            if not is_text_quality_acceptable(text):
                metadata["quality_issues"].append(
                    f"Page {page_num}: Contains binary/encoded data (likely scanned image or corrupted)"
                )
                pages_with_issues += 1
                # Still include it but mark it
                text = f"[WARNING: Page {page_num} contains mostly binary data]\n{text}"
            else:
                text = clean_extracted_text(text)

            text_content.append(f"--- Page {page_num} ---\n{text}")

        # Check if we should try OCR fallback
        if (
            fallback_to_ocr
            and pages_with_no_text > 0
            and pages_with_no_text >= metadata["num_pages"] * 0.8
        ):
            print(
                f"\n  ℹ️  Most pages ({pages_with_no_text}/{metadata['num_pages']}) have no text."
            )
            print("  Attempting OCR extraction instead...")
            # Return a special marker for OCR fallback
            raise ValueError("TRIGGER_OCR_FALLBACK")

        if not text_content:
            if fallback_to_ocr:
                print("\n  ℹ️  No text extracted from PDF. Attempting OCR extraction...")
                raise ValueError("TRIGGER_OCR_FALLBACK")
            else:
                raise ValueError(
                    "No text could be extracted from the PDF. This PDF may contain only images or be corrupted."
                )

        if pages_with_issues > 0:
            metadata["quality_issues"].append(
                f"{pages_with_issues}/{metadata['num_pages']} pages appear to have quality issues"
            )

        return "\n\n".join(text_content), metadata

    except ValueError:
        # Re-raise ValueError from extraction attempts
        raise
    except Exception as e:
        if fallback_to_ocr:
            print(f"\n  ℹ️  Text extraction failed: {str(e)}")
            print("  Attempting OCR extraction as fallback...")
            return extract_text_from_images(pdf_bytes)
        else:
            raise ValueError(
                f"Failed to extract text from PDF: {str(e)}. "
                "This PDF may be corrupted, encrypted, or contain only images."
            )


def get_available_models(base_url: str, api_key: str) -> list[dict]:
    """
    Fetch available models from Open WebUI.

    Args:
        base_url: Base URL of Open WebUI instance
        api_key: API key for authentication

    Returns:
        List of model dictionaries with 'id' and 'name' fields
    """
    url = f"{base_url}/api/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    data = response.json()

    # Extract models from the response
    models = data.get("data", [])
    if not models:
        raise ValueError("No models available on this Open WebUI instance")

    return models


def select_model_from_menu(models: list[dict]) -> str:
    """
    Display a menu of available models and let user select one.

    Args:
        models: List of model dictionaries

    Returns:
        Selected model ID
    """
    print("\n" + "=" * 60)
    print("AVAILABLE MODELS:")
    print("=" * 60)

    for idx, model in enumerate(models, 1):
        model_id = model.get("id", "unknown")
        model_name = model.get("name", model_id)
        print(f"{idx}. {model_name} (ID: {model_id})")

    print("=" * 60)

    while True:
        try:
            choice = input(f"\nSelect a model (1-{len(models)}): ").strip()
            choice_idx = int(choice) - 1

            if 0 <= choice_idx < len(models):
                selected_model = models[choice_idx]
                model_id = selected_model.get("id")
                model_name = selected_model.get("name", model_id)
                print(f"\n✓ Selected model: {model_name}")
                return model_id
            else:
                print(f"Invalid choice. Please enter a number between 1 and {len(models)}")
        except ValueError:
            print(f"Invalid input. Please enter a number between 1 and {len(models)}")


def upload_file_to_openwebui(
    base_url: str, api_key: str, file_bytes: bytes, filename: str
) -> str:
    """
    Upload a file to Open WebUI and return the file ID.

    Args:
        base_url: Base URL of Open WebUI instance
        api_key: API key for authentication
        file_bytes: The file contents as bytes
        filename: Name of the file

    Returns:
        File ID from the API response
    """
    url = f"{base_url}/api/v1/files/"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    files = {"file": (filename, file_bytes, "application/pdf")}

    response = requests.post(url, headers=headers, files=files)
    response.raise_for_status()

    data = response.json()
    file_id = data.get("id")

    if not file_id:
        raise ValueError(f"No file ID returned from API: {data}")

    print(f"✓ File uploaded successfully. File ID: {file_id}")
    return file_id


def send_chat_completion(
    base_url: str,
    api_key: str,
    prompt: str,
    model: str,
    pdf_content: str = None,
) -> str:
    """
    Send a chat completion request to Open WebUI.

    Args:
        base_url: Base URL of Open WebUI instance
        api_key: API key for authentication
        prompt: The user's prompt/message
        model: Model ID to use
        pdf_content: Extracted text content from PDF (optional)

    Returns:
        The assistant's response
    """
    url = f"{base_url}/api/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Prepare the message content - include PDF text if available
    if pdf_content:
        content = f"Here is the content of the PDF file:\n\n{pdf_content}\n\nBased on the above content, please:\n{prompt}"
    else:
        content = prompt

    payload = {
        "messages": [{"role": "user", "content": content}],
        "model": model,
        "stream": False,
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    data = response.json()

    # Extract the response content
    if "choices" in data and len(data["choices"]) > 0:
        message_content = data["choices"][0].get("message", {}).get("content", "")
        return message_content

    raise ValueError(f"Unexpected API response format: {data}")


def main():
    parser = argparse.ArgumentParser(
        description="Interact with Open WebUI API using a PDF file and prompt"
    )

    parser.add_argument(
        "--api-key",
        required=True,
        help="API key for Open WebUI authentication",
    )

    parser.add_argument(
        "--prompt",
        required=True,
        help="Prompt/question to send to the API",
    )

    parser.add_argument(
        "--pdf",
        required=True,
        help="Path to PDF file to upload and process",
    )

    parser.add_argument(
        "--base-url",
        default="http://sushi.it.ilstu.edu:8080",
        help="Base URL of Open WebUI instance (default: http://sushi.it.ilstu.edu:8080)",
    )

    parser.add_argument(
        "--output",
        help="File path to save the response to (optional)",
    )

    parser.add_argument(
        "--use-pdfplumber",
        action="store_true",
        help="Use pdfplumber for extraction instead of PyPDF2 (requires: pip install pdfplumber)",
    )

    parser.add_argument(
        "--use-ocr",
        action="store_true",
        help="Force OCR extraction for image-based PDFs (requires: pip install pytesseract Pillow)",
    )

    parser.add_argument(
        "--no-ocr-fallback",
        action="store_true",
        help="Disable automatic OCR fallback when text extraction fails",
    )

    args = parser.parse_args()

    try:
        # Read PDF file
        print(f"Reading PDF file: {args.pdf}")
        file_bytes, filename = read_pdf_file(args.pdf)
        print(f"✓ PDF file loaded ({len(file_bytes)} bytes)")

        # Extract text from PDF
        print(f"\nExtracting text from PDF...")
        enable_ocr_fallback = not args.no_ocr_fallback

        try:
            if args.use_ocr:
                print("  Using OCR extraction (Tesseract)...")
                pdf_text, metadata = extract_text_from_images(args.pdf)
            elif args.use_pdfplumber:
                print("  Using pdfplumber extraction method...")
                pdf_text, metadata = extract_text_with_pdfplumber(file_bytes)
            else:
                pdf_text, metadata = extract_text_from_pdf(
                    file_bytes, fallback_to_ocr=enable_ocr_fallback
                )
        except ValueError as e:
            if str(e) == "TRIGGER_OCR_FALLBACK":
                print("  Using OCR extraction as fallback...")
                pdf_text, metadata = extract_text_from_images(args.pdf)
            else:
                raise

        print(f"✓ Extracted {len(pdf_text)} characters of text from {metadata['num_pages']} pages")
        print(f"  Extraction method: {metadata['extraction_method']}")

        # Display any quality issues
        if metadata["quality_issues"]:
            print("\n⚠️  Quality Issues Detected:")
            for issue in metadata["quality_issues"]:
                print(f"   - {issue}")
            print(
                "\n   Note: This PDF may contain scanned images or binary data."
            )
            print("   The model may have difficulty processing this content.")

        # Fetch available models
        print(f"\nConnecting to {args.base_url}...")
        models = get_available_models(args.base_url, args.api_key)

        # Display model selection menu
        selected_model = select_model_from_menu(models)

        # Send chat completion
        print(f"\nSending prompt to API...")
        response = send_chat_completion(
            args.base_url,
            args.api_key,
            args.prompt,
            model=selected_model,
            pdf_content=pdf_text,
        )

        print("\n" + "=" * 60)
        print("RESPONSE:")
        print("=" * 60)
        print(response)
        print("=" * 60)

        # Save to file if requested
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(response)
            print(f"\n✓ Response saved to: {args.output}")

        return 0

    except FileNotFoundError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        error_msg = str(e)
        # Check for OCR-related errors
        if "image-based OCR" in error_msg or "pdf2image" in error_msg:
            print(f"❌ OCR Extraction Error: {e}", file=sys.stderr)
            print(
                "\nTo use OCR, install the required packages:",
                file=sys.stderr,
            )
            print("  pip install pdf2image pytesseract Pillow", file=sys.stderr)
            print(
                "  sudo apt-get install poppler-utils tesseract-ocr",
                file=sys.stderr,
            )
        else:
            print(f"❌ Validation Error: {e}", file=sys.stderr)
        return 1
    except requests.exceptions.RequestException as e:
        print(f"❌ API Error: {e}", file=sys.stderr)
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            print(f"Response: {e.response.text}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Unexpected Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
