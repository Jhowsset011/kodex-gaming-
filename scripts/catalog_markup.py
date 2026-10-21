"""Small allowlist for descriptions shared by import and static SEO rendering."""
from html import escape
from html.parser import HTMLParser


class DescriptionParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output, self.text, self.stack = [], [], []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'iframe', 'object', 'template'):
            self.skip += 1
        if self.skip:
            return
        mapped = 'p' if tag in ('div', 'li', 'tr', 'h1', 'h2', 'h3') else tag
        if mapped in ('p', 'strong'):
            self.output.append(f'<{mapped}>')
            self.stack.append(mapped)
        elif tag == 'br':
            self.output.append('<br>')
        if tag in ('p', 'br', 'div', 'li', 'tr', 'h1', 'h2', 'h3'):
            self.text.append('\n')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag != 'br': self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'iframe', 'object', 'template'):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip: return
        mapped = 'p' if tag in ('div', 'li', 'tr', 'h1', 'h2', 'h3') else tag
        if mapped in self.stack:
            while self.stack:
                current = self.stack.pop()
                self.output.append(f'</{current}>')
                if current == mapped: break
        if tag in ('p', 'div', 'li', 'tr', 'h1', 'h2', 'h3'):
            self.text.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.output.append(escape(data))
            self.text.append(data)

    def finish(self):
        return ''.join(self.output) + ''.join(f'</{tag}>' for tag in reversed(self.stack))


def clean_description(value):
    parser = DescriptionParser()
    parser.feed(str(value or ''))
    return parser.finish().strip()


def description_text(value):
    parser = DescriptionParser()
    parser.feed(str(value or ''))
    return '\n'.join(' '.join(line.split()) for line in ''.join(parser.text).splitlines() if line.strip())
