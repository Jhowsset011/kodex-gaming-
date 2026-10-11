"""Allow technical citations only on the product manufacturer's public sites."""

from urllib.parse import urlsplit


MANUFACTURER_DOMAINS = {
    'aoc': ('aoc.com', 'aoc.com.br', 'aoc-europe.com'),
    'agiler': ('agiler.com', 'agilerusa.com'),
    'antec': ('antec.com',),
    'argom': ('argomtech.com',),
    'benq': ('benq.com',),
    'corsair': ('corsair.com',),
    'dell': ('dell.com',),
    'elo': ('elotouch.com',),
    'grandstream': ('grandstream.com',),
    'hp': ('hp.com',),
    'hpe': ('hpe.com',),
    'hiksemi': ('hiksemi.com', 'hiksemitech.com'),
    'hikvision': ('hikvision.com',),
    'intel': ('intel.com',),
    'jbl': ('jbl.com',),
    'kingston': ('kingston.com',),
    'klip xtreme': ('klipxtreme.com',),
    'klipsch': ('klipsch.com',),
    'lenovo': ('lenovo.com',),
    'lexar': ('lexar.com',),
    'logitech': ('logitech.com', 'logitechg.com', 'logi.com'),
    'microsoft': ('microsoft.com',),
    'msi': ('msi.com',),
    'primus': ('primusgaming.com',),
    'roku': ('roku.com',),
    'samsung': ('samsung.com',),
    'sandisk': ('sandisk.com',),
    'seagate': ('seagate.com',),
    'sonos': ('sonos.com',),
    'verbatim': ('verbatim.com', 'verbatim-europe.com'),
    'viewsonic': ('viewsonic.com',),
    'western digital': ('westerndigital.com', 'wd.com'),
    'xtech': ('xtechamericas.com',),
}


def validate_manufacturer_url(url, brand):
    """Reject unrelated stores, spoofed hosts, credentials and insecure URLs."""
    if not isinstance(url, str) or not isinstance(brand, str):
        raise ValueError('Fuente oficial de fabricante inválida')
    try:
        parts = urlsplit(url)
        domains = MANUFACTURER_DOMAINS.get(brand.strip().casefold(), ())
        valid = (parts.scheme == 'https' and parts.hostname
                 and parts.port in (None, 443) and not parts.username
                 and not parts.password and parts.path.strip('/')
                 and not any(character.isspace() for character in url)
                 and any(parts.hostname == domain or parts.hostname.endswith('.' + domain)
                         for domain in domains))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('La fuente técnica no corresponde al fabricante del producto')
    return url
