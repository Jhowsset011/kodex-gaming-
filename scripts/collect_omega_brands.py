#!/usr/bin/env python3
"""Audit public Omega brand searches without publishing or reading sale rules."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode

from omega_public import BASE_URL, _RateLimiter, make_tls_context, read_public_url

BRANDS = ('MSI', 'AOC', 'ANTEC', 'SAMSUNG')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    context = make_tls_context(args.output / 'tls')
    limiter = _RateLimiter()
    pages = [('home', BASE_URL + '/es')]
    pages.extend((brand, BASE_URL + '/es/product/search?' + urlencode({'Terms': brand}))
                 for brand in BRANDS)
    report = []
    for name, url in pages:
        body = read_public_url(url, context=context, limiter=limiter)
        (args.output / (name + '.html')).write_bytes(body)
        report.append({'name': name, 'url': url, 'bytes': len(body)})
        print('Consulta pública:', name, len(body), 'bytes', flush=True)
    (args.output / 'searches.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
