#!/usr/bin/env python3
import unittest
import warnings
import pandas as pd
from pandas.testing import assert_frame_equal
from xpathextractor import parse_document, select, xpath, render

class UnittestRunnerThatDoesntAddWarningFilter(unittest.TextTestRunner):
    def __init(self, *args, **kwargs):
        print(repr((args, kwargs)))
        super().__init__(*args, **kwargs, warnings=None)


class Xml1(unittest.TestCase):
    def setUp(self):
        self.tree = parse_document(
            (
                '<a><b><c>c</c><d foo="bar">d</d></b><b><c>C</c>'
                '<d foo="baz">D</d></b><e>ehead<f>f</f>etail</e></a>'
            ),
            False
        )

    def select(self, selector):
        return select(self.tree, xpath(selector))

    def test_convert_node_to_text(self):
        self.assertEqual(self.select('//c'), ['c', 'C'])

    def test_convert_subnodes_to_text(self):
        self.assertEqual(self.select('//b'), ['cd', 'CD'])

    def test_attributes(self):
        self.assertEqual(self.select('//d/@foo'), ['bar', 'baz'])

    def test_text(self):
        self.assertEqual(self.select('//d/text()'), ['d', 'D'])

    def test_head(self):
        self.assertEqual(self.select('//f/preceding-sibling::text()'),
                         ['ehead'])

    def test_tail(self):
        self.assertEqual(self.select('//f/following-sibling::text()'),
                         ['etail'])

    def test_count(self):
        self.assertEqual(self.select('count(//d)'), [2.0])

    def test_bool(self):
        self.assertEqual(self.select('boolean(//f)'), [True])
        self.assertEqual(self.select('boolean(//g)'), [False])


class Html1(unittest.TestCase):
    def setUp(self):
        self.tree = parse_document(
            '''<!DOCTYPE html><html>
              <head>
                <meta charset="utf-16be">
                <title>Hello, world!</title>
                <link rel="stylesheet" href="/style.css"/>
                <script src="/script.js"></script>
              </head>
              <body>
                <img src="/logo.png" alt="logo" />
                <p>Foo</p>
                <p>Bar</p>
                <table><td>Single-cell table</table>
                <a href="/foo">Foo</a>
                <a href="/bar">Bar</a>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2">
                  <path d="M0 0L2 2"/>
                </svg>
              </body>
            </html>''',
            True
        )

    def select(self, selector):
        return select(self.tree, xpath(selector))

    def test_simple(self):
        self.assertEqual(self.select('//p'), ['Foo', 'Bar'])

    def test_do_not_expand_single_string(self):
        self.assertEqual(self.select("'ab'"), ['ab'])

    def test_svg_namespace(self):
        # Works across namespaces
        self.assertEqual(self.select('//svg:path/@d'), ['M0 0L2 2'])

    def test_add_missing_elements(self):
        # Parse invalid HTML by adding missing elements
        self.assertEqual(self.select('//tr'), ['Single-cell table'])


# class HtmlTest(unittest.TestCase):
#     def test_no_warning_coercing_non_xml_name(self):
#         # Turn warning into error (just for this test -- the test runner resets
#         # filters each test)
#         warnings.simplefilter('error', append=True)
#         parse_document('<ns:html></ns:html>', True)


class XpathExtractorTest(unittest.TestCase):

    def test_multiple_columns_unequal_lengths(self):
        # Use the "zip" extraction algorithm. Should pad all columns to same length
        # if needed, and give a warning if we did.

        doc1 = '''
            <!DOCTYPE html><html>
              <head>
                <meta charset="utf-16be">
                <title>Scrape me please</title>
                <link rel="stylesheet" href="/style.css"/>
                <script src="/script.js"></script>
              </head>
              <body>
                <h2>This is outside the l1</h2>
                <img src="/logo.png" alt="logo" />
                <ul>
                    <li>
                        <h1>A title</h1>
                        <p>A description</p>
                    </li>
                    <li>
                        <h1>B title</h1>
                        <p>B description</p>
                    </li>
                </ul>
              </body>'''

        doc2 = '''
            <!DOCTYPE html><html>
              <head>
                <meta charset="utf-16be">
                <title>Link scraping test</title>
                <link rel="stylesheet" href="/style.css"/>
                <script src="/script.js"></script>
              </head>
              <body>
                <img src="/logo.png" alt="logo" />
                <ul>
                    <li>
                        <h1>C title</h1>
                        <p>C description</p>
                        <p>D description</p>
                    </li>
                </ul>
                <table>
                    <tr>
                        <th>Name<th>
                        <th>link<th>
                    </tr>
                    <tr>
                        <td>Orange<td>
                        <td><a href='http://orange.com'>Orange link</a></td>
                    </tr>
                    <tr>
                        <td>Red<td>
                        <td><a>Red no href</a></td>
                    </tr>
                    <tr>
                        <td>Blue<td>
                        <td><a href='http://blue.com'>Blue link</a></td>
                    </tr>
                </table>
              </body>'''

        table = pd.DataFrame({'html':[doc1, doc2]})


        params = {
            'rowxpath':'',
            'colselectors' : [
                {'colxpath':'//h1', 'colname':'Title'},
                {'colxpath':'//p', 'colname':'Description'},
            ]}
        expected = pd.DataFrame({
            'Title':['A title', 'B title', 'C title', None],
            'Description':['A description','B description', 'C description', 'D description']
        })

        out = render(table, params)
        assert_frame_equal(out[0], expected)
        self.assertEqual(out[1], (
            'Extracted columns of differing lengths from HTML on row 2'
        ))

    def test_bad_html(self):
        params = {
            'colselectors' : [
                {'colxpath':'//body', 'colname':'Body'},
            ]}
        # We haven't found an example where parse_document() throws an error;
        # so let's just test that _something_ comes out....
        out = render(pd.DataFrame({'html':['<a', '<html><body>x</head></html>']}),
                     params)
        assert_frame_equal(out, pd.DataFrame({'Body': ['x']}))

    def test_empty_input_table(self):
        # No rows in, no rows out (but output the columns the user has specified)
        params = {
            'colselectors' : [
                {'colxpath':'h1', 'colname':'Title'},
                {'colxpath':'p', 'colname':'Description'},
            ]}
        out = render(pd.DataFrame({'html':[]}), params)
        expected = pd.DataFrame({'Title': [], 'Description': []}, dtype=str)
        assert_frame_equal(out, expected)

    def test_parse_null(self):
        # No rows in, no rows out (but output the columns the user has specified)
        params = {
            'colselectors' : [
                {'colxpath':'//body', 'colname': 'A'},
            ]
        }
        out = render(pd.DataFrame({'html': [None]}, dtype=str), params)
        expected = pd.DataFrame({'A': []}, dtype=str)
        assert_frame_equal(out, expected)

    def test_empty_colselector(self):
        # missing xpath should error
        params = {
            'colselectors' : [
                {'colxpath':'', 'colname':'Title'},
                {'colxpath':'p', 'colname':'Description'},
            ]}
        out = render(pd.DataFrame({'html':['<p>foo</p>']}), params)
        self.assertEqual(out, 'Missing column selector')

    def test_empty_colname(self):
        # missing column name should error
        table = pd.DataFrame({'html':['<p>foo</p>']})
        params = {
            'colselectors' : [
                {'colxpath':'.', 'colname':'Title'},
                {'colxpath':'p', 'colname':''},
            ]}
        out = render(table, params)
        self.assertEqual(out, 'Missing column name')

    def test_duplicate_colname(self):
        table = pd.DataFrame({'html':['<p>foo</p>']})
        params = {
            'colselectors' : [
                {'colxpath':'//a', 'colname':'Title'},
                {'colxpath':'//p', 'colname':'Title'},
            ]}
        out = render(table, params)
        self.assertEqual(out, 'Duplicate column name "Title"')

    def test_bad_xpath(self):
        table = pd.DataFrame({'html':['<p>foo</p>']})
        params = {
            'colselectors' : [
                {'colxpath':'totes not an xpath', 'colname':'Title'},
                {'colxpath':'p', 'colname':'Description'},
            ]}
        out = render(table, params)
        self.assertEqual(
            out,
            'Invalid XPath syntax for column "Title": Invalid expression'
        )

    def test_valid_xpath_eval_error(self):
        table = pd.DataFrame({'html':['<p>foo</p>']})
        params = {
            'colselectors' : [
                # valid xpath -- but not valid for this document
                {'colxpath':'//badns:a', 'colname':'Title'},
            ]}
        out = render(table, params)
        self.assertEqual(
            out,
            'XPath error for column "Title": Undefined namespace prefix'
        )

    def test_no_colselectors(self):
        table = pd.DataFrame({'html':['<p>foo</p>']})
        params = {'colselectors': []}
        out = render(table, params)
        # For now, output the input table
        expected = pd.DataFrame({'html':['<p>foo</p>']})
        assert_frame_equal(out, expected)


if __name__ == '__main__':
    unittest.main(testRunner=UnittestRunnerThatDoesntAddWarningFilter())
