import unittest
from autoscribe.ingest import IngestError, frontmatter_slug, split_frontmatter


class FrontmatterWritebackTests(unittest.TestCase):
    def test_raw_prefix_and_slug_preserved(self):
        prefix='---\r\nslug: "psg.test" # original\r\ntitle: Keep *raw*\r\n---\r\n'
        raw,body=split_frontmatter(prefix+'Body\r\n')
        self.assertEqual(raw,prefix)
        self.assertEqual(body,'Body\r\n')
        self.assertEqual(frontmatter_slug(raw),'psg.test')

    def test_ambiguous_or_unclosed_frontmatter_fails(self):
        with self.assertRaises(IngestError):split_frontmatter('---\nslug: psg.test\nBody')
        with self.assertRaises(IngestError):frontmatter_slug('---\nslug: psg.a\nslug: psg.b\n---\n')
