#!/usr/bin/env python3
"""Collect verified public Omega photos for a one-time migration audit."""
import argparse
import json
from pathlib import Path

from omega_images import download_source_images


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sources = json.loads(args.source_file.read_text(encoding='utf-8'))['sources']
    images = download_source_images(sources, args.output)
    print(f'Fotografías de Omega verificadas: {sum(bool(name) for name in images.values())}; ausentes: {sum(name is None for name in images.values())}.')


if __name__ == '__main__':
    main()
