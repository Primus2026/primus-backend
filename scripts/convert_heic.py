import sys
import os
from PIL import Image
from pillow_heif import register_heif_opener


def convert_heic_to_png(source_path):
    register_heif_opener()

    if os.path.isdir(source_path):
        files = [os.path.join(source_path, f) for f in os.listdir(source_path)]
    else:
        files = [source_path]

    for file_path in files:
        if file_path.lower().endswith(".heic"):
            try:
                img = Image.open(file_path)
                target_path = os.path.splitext(file_path)[0] + ".png"
                img.save(target_path, "PNG")
                print(f"Converted: {file_path} -> {target_path}")
            except Exception as e:
                print(f"Error converting {file_path}: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert_heic.py <file_or_directory>")
        sys.exit(1)

    convert_heic_to_png(sys.argv[1])
