import unittest
from realtime.dde import parse_link


class DdeLinkTests(unittest.TestCase):
    def test_vendor_public_link(self):
        value=parse_link(b'Sky2008\x00MIN1\x00YJHGHC2\x00\x00')
        self.assertEqual(value,dict(service='Sky2008',topic='MIN1',item='YJHGHC2'))

    def test_unicode_vendor_link(self):
        value=parse_link('Sky2020\0MIN1\0YJHGHC2\0\0'.encode('utf-16le'))
        self.assertEqual(value['service'],'Sky2020')

    def test_unrelated_or_command_link_rejected(self):
        for value in [b'Excel\0System\0anything\0\0',b'Sky2008\0System\0anything\0\0',
                      b'Sky2008\0MIN1\0bad\nitem\0\0',b'Sky2008\0MIN1\0',b'Sky2008\0MIN1\0YJHGHC2',b'x'*9000]:
            with self.subTest(value=value[:30]),self.assertRaises(ValueError):parse_link(value)


if __name__=='__main__':unittest.main()
