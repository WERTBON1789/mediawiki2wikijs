#!/usr/bin/env python3
import unittest
import fix_links

class Tests(unittest.TestCase):
    def test_html_link(self):
        input_str = '<a href="Company" title="oitrjrthjoritjhorijthoritj">DOMOLOGIC</a>'
        converted_content = fix_links.fix_hyper_links(input_str)

        self.assertEqual(converted_content,
                         '<a href="/Company" title="DOMOLOGIC">DOMOLOGIC</a>')

    def test_qoutes(self):
        input_str = '[Flash-Partitionierung beim "OP7000"](Customers:DA:OP7000:FlashPartitioning "wikilink")'
        converted_content = fix_links.fix_hyper_links(input_str)

        self.assertEqual(converted_content,
                         '[Flash-Partitionierung beim "OP7000"](/Customers/DA/OP7000/FlashPartitioning "Flash-Partitionierung beim \\"OP7000\\"")')

    def test_html_img_link(self):
        input_str = '<img src="Thumbnail_company.png" title="Thumbnail company.png|link=Company" alt="Thumbnail company.png|link=Company" />'
        converted_content = fix_links.fix_hyper_links(input_str)

        self.assertEqual(converted_content,'<img src="/assets/thumbnail_company.png" title="Thumbnail company.png|link=Company"  alt="Thumbnail company.png|link=Company"  />')
    
    def test_markdown_img_link(self):
        input_str = '![Aufnahme der Einstellung](GatewayPowerMng.jpg "Aufnahme der Einstellung")'
        converted_content = fix_links.fix_hyper_links(input_str)

        self.assertEqual(converted_content, '![Aufnahme der Einstellung](/assets/gatewaypowermng.jpg "Aufnahme der Einstellung")')

if __name__ == "__main__":
    unittest.main()
