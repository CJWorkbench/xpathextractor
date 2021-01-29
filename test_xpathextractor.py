#!/usr/bin/env python3
import unittest
import warnings
import pandas as pd
from pandas.testing import assert_frame_equal
from xpathextractor import parse_document, select, xpath, render, migrate_params
from cjwmodule.testing.i18n import cjwmodule_i18n_message, i18n_message


class Settings:
    MAX_BYTES_PER_COLUMN_NAME: int = 100


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
            False,
        )

    def select(self, selector):
        return select(self.tree, xpath(selector))

    def test_convert_node_to_text(self):
        self.assertEqual(self.select("//c"), ["c", "C"])

    def test_convert_subnodes_to_text(self):
        self.assertEqual(self.select("//b"), ["cd", "CD"])

    def test_attributes(self):
        self.assertEqual(self.select("//d/@foo"), ["bar", "baz"])

    def test_text(self):
        self.assertEqual(self.select("//d/text()"), ["d", "D"])

    def test_head(self):
        self.assertEqual(self.select("//f/preceding-sibling::text()"), ["ehead"])

    def test_tail(self):
        self.assertEqual(self.select("//f/following-sibling::text()"), ["etail"])

    def test_count(self):
        self.assertEqual(self.select("count(//d)"), [2.0])

    def test_bool(self):
        self.assertEqual(self.select("boolean(//f)"), ["True"])
        self.assertEqual(self.select("boolean(//g)"), ["False"])


class Html1(unittest.TestCase):
    def setUp(self):
        self.tree = parse_document(
            """<!DOCTYPE html><html>
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
            </html>""",
            True,
        )

    def select(self, selector):
        return select(self.tree, xpath(selector))

    def test_simple(self):
        self.assertEqual(self.select("//p"), ["Foo", "Bar"])

    def test_do_not_expand_single_string(self):
        self.assertEqual(self.select("'ab'"), ["ab"])

    def test_svg_namespace(self):
        # Works across namespaces
        self.assertEqual(self.select("//svg:path/@d"), ["M0 0L2 2"])

    def test_add_missing_elements(self):
        # Parse invalid HTML by adding missing elements
        self.assertEqual(self.select("//tr"), ["Single-cell table"])

    def test_clean_insignificant_whitespace(self):
        tree = parse_document(
            '<html><body><p>\n  hi <b class="X"> !</b>\n</p></body></html>', True
        )
        result = select(tree, xpath("//p"))
        self.assertEqual(result, ["hi  !"])


# class HtmlTest(unittest.TestCase):
#     def test_no_warning_coercing_non_xml_name(self):
#         # Turn warning into error (just for this test -- the test runner resets
#         # filters each test)
#         warnings.simplefilter('error', append=True)
#         parse_document('<ns:html></ns:html>', True)

# Parameter helper dictionary, ensures that a complete set of parameters is passed,
# while making it easy to set just the parameters we want to non-defaults
defParams = {"method": "xpath", "tablenum": 0, "colselectors": []}


class XpathExtractorTest(unittest.TestCase):
    def test_multiple_columns_unequal_lengths(self):
        # Use the "zip" extraction algorithm. Should pad all columns to same length
        # if needed, and give a warning if we did.

        doc1 = """
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
              </body>"""

        doc2 = """
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
              </body>"""

        table = pd.DataFrame({"html": [doc1, doc2]})

        params = {
            **defParams,
            "colselectors": [
                {"colxpath": "//h1", "colname": "Title"},
                {"colxpath": "//p", "colname": "Description"},
            ],
        }
        expected = pd.DataFrame(
            {
                "Title": ["A title", "B title", "C title", None],
                "Description": [
                    "A description",
                    "B description",
                    "C description",
                    "D description",
                ],
            }
        )

        out, errors = render(table, params, settings=Settings())
        assert_frame_equal(out, expected)
        self.assertEqual(
            errors, [i18n_message("warning.extractedDifferentLengths", {"row": 2})]
        )

    def test_bad_html(self):
        params = {
            **defParams,
            "colselectors": [
                {"colxpath": "//body", "colname": "Body"},
            ],
        }
        # We haven't found an example where parse_document() throws an error;
        # so let's just test that _something_ comes out....
        out, errors = render(
            pd.DataFrame({"html": ["<a", "<html><body>x</head></html>"]}),
            params,
            settings=Settings(),
        )
        assert_frame_equal(out, pd.DataFrame({"Body": ["x"]}))
        self.assertEqual(errors, [])

    def test_empty_input_table(self):
        # No rows in, no rows out (but output the columns the user has specified)
        params = {
            **defParams,
            "colselectors": [
                {"colxpath": "h1", "colname": "Title"},
                {"colxpath": "p", "colname": "Description"},
            ],
        }
        out, errors = render(pd.DataFrame({"html": []}), params, settings=Settings())
        expected = pd.DataFrame({"Title": [], "Description": []}, dtype=str)
        assert_frame_equal(out, expected)
        self.assertEqual(errors, [])

    def test_parse_null(self):
        # No rows in, no rows out (but output the columns the user has specified)
        params = {
            **defParams,
            "colselectors": [
                {"colxpath": "//body", "colname": "A"},
            ],
        }
        out, errors = render(
            pd.DataFrame({"html": [None]}, dtype=str), params, settings=Settings()
        )
        expected = pd.DataFrame({"A": []}, dtype=str)
        assert_frame_equal(out, expected)
        self.assertEqual(errors, [])

    def test_empty_colselector(self):
        # missing xpath should error
        params = {
            **defParams,
            "colselectors": [
                {"colxpath": "", "colname": "Title"},
                {"colxpath": "p", "colname": "Description"},
            ],
        }
        out, errors = render(
            pd.DataFrame({"html": ["<p>foo</p>"]}), params, settings=Settings()
        )
        self.assertIsNone(out)
        self.assertEqual(errors, [i18n_message("badParam.colxpath.missing")])

    def test_empty_colname(self):
        # missing column name should error
        table = pd.DataFrame({"html": ["<p>foo</p>"]})
        params = {
            **defParams,
            "colselectors": [
                {"colxpath": ".", "colname": "Title"},
                {"colxpath": "p", "colname": ""},
            ],
        }
        out, errors = render(table, params, settings=Settings())
        self.assertIsNone(out)
        self.assertEqual(errors, [i18n_message("badParam.colname.missing")])

    def test_duplicate_colname(self):
        table = pd.DataFrame({"html": ["<p>foo</p>"]})
        params = {
            **defParams,
            "colselectors": [
                {"colxpath": "//a", "colname": "Title"},
                {"colxpath": "//p", "colname": "Title"},
            ],
        }
        out, errors = render(table, params, settings=Settings())
        self.assertIsNone(out)
        self.assertEqual(
            errors,
            [i18n_message("badParam.colname.duplicate", {"column_name": "Title"})],
        )

    def test_bad_xpath(self):
        table = pd.DataFrame({"html": ["<p>foo</p>"]})
        params = {
            **defParams,
            "colselectors": [
                {"colxpath": "totes not an xpath", "colname": "Title"},
                {"colxpath": "p", "colname": "Description"},
            ],
        }
        out, errors = render(table, params, settings=Settings())
        self.assertIsNone(out)
        self.assertEqual(
            errors,
            [
                i18n_message(
                    "badParam.colxpath.invalid",
                    {"column_name": "Title", "error": "Invalid expression"},
                )
            ],
        )

    def test_valid_xpath_eval_error(self):
        table = pd.DataFrame({"html": ["<p>foo</p>"]})
        params = {
            **defParams,
            "colselectors": [
                # valid xpath -- but not valid for this document
                {"colxpath": "//badns:a", "colname": "Title"},
            ],
        }
        out, errors = render(table, params, settings=Settings())
        self.assertIsNone(out)
        self.assertEqual(
            errors,
            [
                i18n_message(
                    "ColumnExtractionError.message",
                    {"column_name": "Title", "error": "Undefined namespace prefix"},
                )
            ],
        )

    def test_no_colselectors(self):
        table = pd.DataFrame({"html": ["<p>foo</p>"]})
        params = {**defParams, "colselectors": []}
        out, errors = render(table, params, settings=Settings())
        # For now, output the input table
        expected = pd.DataFrame({"html": ["<p>foo</p>"]})
        assert_frame_equal(out, expected)
        self.assertEqual(errors, [])

    def test_html5lib_ignore_comments(self):
        # User found a page where `//h3` selector causes TreeWalker to crash
        # https://www.kpu.ca/calendar/2018-19/courses/jrnl/index.html as of 2019-5-20
        html = """<h3> <a><!--jrnl1160--></a>JRNL 1160<span>3 Credits</span> </h3>"""
        table = pd.DataFrame({"html": [html]})

        params = {
            **defParams,
            "colselectors": [{"colxpath": "//h3", "colname": "Title"}],
        }
        out, errors = render(table, params, settings=Settings())
        assert_frame_equal(out, pd.DataFrame({"Title": ["JRNL 11603 Credits"]}))
        self.assertEqual(errors, [])

    def test_clean_insignificant_whitespace(self):
        tree = parse_document(
            "<html><body><div>\n  hi<div>\n    there\n  </div></body></html>", True
        )
        result = select(tree, xpath("/html/body/div"))
        self.assertEqual(result, ["hi there"])

    def test_preserve_significant_whitespace(self):
        tree = parse_document(
            '<html><body><p>\n  hi <b class="X"> !</b>\n</p></body></html>', True
        )
        result = select(tree, xpath("//p"))
        self.assertEqual(result, ["hi  !"])


defTableParams = {**defParams, "method": "table", "tablenum": 1}

# Optional URL column, to test error messages when we do and don't have url
def make_html_input(html, url=None):
    if not url:
        return pd.DataFrame({"html": [html]})
    else:
        return pd.DataFrame({"url": [url], "html": [html]})


class TableExtractorTest(unittest.TestCase):

    a_table_html = """
    <html>
        <body>
            <table>
                <thead><tr><th>B</th><th>A</th></tr></thead>
                <tbody>
                    <tr><td>1</td><td>2</td></tr>
                    <tr><td>2</td><td>3</td></tr>
                </tbody>
            </table>
        </body>
    </html>
    """
    b_table_html = """
    <html>
        <body>
            <table>
                <thead><tr><th>C</th><th>A</th></tr></thead>
                <tbody>
                    <tr><td>5</td><td>4</td></tr>
                    <tr><td>6</td><td>5</td></tr>
                </tbody>
            </table>
        </body>
    </html>
    """

    def test_one_input_row(self):
        table = make_html_input(self.a_table_html)
        result, errors = render(table, defTableParams, settings=Settings())
        assert_frame_equal(result, pd.DataFrame({"B": [1, 2], "A": [2, 3]}))
        self.assertEqual(errors, [])

    def test_multiple_input_rows_differing_columns(self):
        # also tests merging of tables with different columns,
        # and ensures that we don't sort columns when concatenating
        table = pd.DataFrame({"html": [self.a_table_html, self.b_table_html]})
        result, errors = render(table, defTableParams, settings=Settings())
        assert_frame_equal(
            result,
            pd.DataFrame(
                {"B": [1, 2, None, None], "A": [2, 3, 4, 5], "C": [None, None, 5, 6]}
            ),
        )
        self.assertEqual(errors, [])

    def test_multiple_input_rows_with_warning(self):
        # If we have multiple rows with warnings, return warning for the first
        # and skip extraction for the others
        ok_html = self.a_table_html
        no_table_html = "<h1>Hell yeah!</h2>"
        table = pd.DataFrame({"html": [ok_html, no_table_html, no_table_html, ok_html]})

        out, errors = render(table, defTableParams, settings=Settings())
        assert_frame_equal(out, pd.DataFrame({"B": [1, 2, 1, 2], "A": [2, 3, 2, 3]}))
        self.assertEqual(
            errors, [i18n_message("error.noTable", {"rowname": "input html row 2"})]
        )

    def test_multiple_input_rows_url_in_warning(self):
        # if there is a 'url' column it should appear in warning messages
        ok_html = self.a_table_html
        no_table_html = "<h1>Hell yeah!</h2>"
        table = pd.DataFrame(
            {
                "url": [
                    "http://foo.com/a",
                    "http://foo.com/b",
                    "http://foo.com/c",
                    "http://foo.com/d",
                ],
                "html": [ok_html, no_table_html, no_table_html, ok_html],
            }
        )

        out, errors = render(table, defTableParams, settings=Settings())
        assert_frame_equal(out, pd.DataFrame({"B": [1, 2, 1, 2], "A": [2, 3, 2, 3]}))
        self.assertEqual(
            errors, [i18n_message("error.noTable", {"rowname": "http://foo.com/b"})]
        )

    def test_table_index_under(self):
        table = make_html_input(self.a_table_html)
        params = {**defTableParams, "first_row_is_header": True, "tablenum": 0}
        result, errors = render(table, params, settings=Settings())
        self.assertIsNone(result)
        self.assertEqual(errors, [i18n_message("badParam.tablenum.negative")])

    def test_table_index_over(self):
        table = make_html_input(self.a_table_html)
        params = {**defTableParams, "first_row_is_header": True, "tablenum": 2}
        result, errors = render(table, params, settings=Settings())
        self.assertIsNone(result)
        self.assertEqual(
            errors,
            [
                i18n_message(
                    "badParam.tableNum.tooBig",
                    {"n_tables": 1, "rowname": "input html row 1"},
                )
            ],
        )

        table = make_html_input(self.a_table_html, url="http://foo.com")
        result, errors = render(table, params, settings=Settings())
        self.assertIsNone(result)
        self.assertEqual(
            errors,
            [
                i18n_message(
                    "badParam.tableNum.tooBig",
                    {"n_tables": 1, "rowname": "http://foo.com"},
                )
            ],
        )

    def test_only_some_colnames(self):
        # pandas read_table() does odd stuff when there are multiple commas at
        # the ends of rows. Test that read_html() doesn't do the same thing.
        table = make_html_input(
            """
            <html>
                <body>
                    <table>
                        <tbody>
                            <tr><th>A</th></tr>
                            <tr><th>a</th><td>1</td></tr>
                            <tr><th>b</th><td>2</td></tr>
                        </tbody>
                    </table>
                </body>
            </html>
            """
        )

        result, errors = render(table, defTableParams, settings=Settings())
        assert_frame_equal(
            result,
            pd.DataFrame(
                {
                    "A": ["a", "b"],
                    "Unnamed: 1": [1, 2],
                }
            ),
        )
        self.assertEqual(errors, [])

    def test_no_tables(self):
        table = make_html_input("<html><body>No table</body></html>")
        result, errors = render(table, defTableParams, settings=Settings())
        self.assertIsNone(result)
        self.assertEqual(
            errors, [i18n_message("error.noTable", {"rowname": "input html row 1"})]
        )

    def test_empty_str_is_empty_str(self):
        # Add two columns. pd.read_html() will not return an all-empty
        # row, and we're not testing what happens when it does. We want
        # to test what happens when there's an empty _value_.
        table = make_html_input(
            """
            <table>
                <tr><th>A</th><th>B</th></tr>
                <tr><td>a</td><td></td></tr>
            </table>
            """
        )
        result, errors = render(table, defTableParams, settings=Settings())
        assert_frame_equal(result, pd.DataFrame({"A": ["a"], "B": [""]}))
        self.assertEqual(errors, [])

    def test_empty_table(self):
        table = make_html_input("<html><body><table></table></body></html>")
        result, errors = render(table, defTableParams, settings=Settings())
        self.assertIsNone(result)
        self.assertEqual(
            errors, [i18n_message("error.noTable", {"rowname": "input html row 1"})]
        )

    def test_header_only_table(self):
        table = make_html_input(
            """
            <html><body><table>
                <thead><tr><th>A</th></tr></thead>
                <tbod></tbody>
            </table></body></html>
            """
        )
        result, errors = render(table, defTableParams, settings=Settings())
        assert_frame_equal(result, pd.DataFrame({"A": []}, dtype=str))
        self.assertEqual(errors, [])

    def test_avoid_duplicate_colnames(self):
        table = make_html_input(
            """
            <table>
               <thead><tr><th>A</th><th>A</th></tr></thead>
               <tbod><tr><td>1</td><td>2</td></tr></tbody>
            </table>
            """
        )
        result, errors = render(table, defTableParams, settings=Settings())
        # We'd prefer 'A 2', but pd.read_html() doesn't give us that choice.
        assert_frame_equal(result, pd.DataFrame({"A": [1], "A.1": [2]}))
        self.assertEqual(errors, [])

    def test_merge_thead_colnames(self):
        table = make_html_input(
            """
            <table>
                <thead>
                    <tr><th colspan="2">Category</th></tr>
                    <tr><th>A</th><th>B</th></tr>
                </thead>
                <tbody>
                    <tr><td>a</td><td>b</td></tr>
                </tbody>
            </table>
            """
        )

        result, errors = render(table, defTableParams, settings=Settings())
        assert_frame_equal(
            result, pd.DataFrame({"Category - A": ["a"], "Category - B": ["b"]})
        )
        self.assertEqual(errors, [])

    def test_no_colnames(self):
        table = make_html_input(
            "<table><tbody><tr><td>a</td><td>b</td></tr></tbody></table>"
        )
        result, errors = render(table, defTableParams, settings=Settings())
        assert_frame_equal(result, pd.DataFrame({"Column 1": ["a"], "Column 2": ["b"]}))
        self.assertEqual(
            errors,
            [
                cjwmodule_i18n_message(
                    "util.colnames.warnings.default",
                    {"n_columns": 2, "first_colname": "Column 1"},
                )
            ],
        )

    def test_merge_thead_duplicate_colnames(self):
        table = make_html_input(
            """
            <table>
                <thead>
                    <tr><th colspan="2">Category</th><th rowspan="2">Category - A</th></tr>
                    <tr><th>A</th><th>B</th></tr>'
                </thead>
                <tbody>
                    <tr><td>a</td><td>b</td><td>c</td></tr>'
                </tbody>
            </table>
            """
        )
        result, errors = render(table, defTableParams, settings=Settings())
        assert_frame_equal(
            result,
            pd.DataFrame(
                {"Category - A": ["a"], "Category - B": ["b"], "Category - A 2": ["c"]}
            ),
        )
        self.assertEqual(
            errors,
            [
                cjwmodule_i18n_message(
                    "util.colnames.warnings.numbered",
                    {"n_columns": 1, "first_colname": "Category - A 2"},
                )
            ],
        )

    def test_prevent_empty_colname(self):
        # https://www.pivotaltracker.com/story/show/162648330
        table = make_html_input(
            """
            <table>
                <thead>
                    <tr><th></th><th>Column 1</th></tr>
                </thead>
                <tbody>
                    <tr><td>a</td><td>b</td><td>c</td></tr>
                </tbody>
            </table>
            """
        )
        result, errors = render(table, defTableParams, settings=Settings())

        # We'd prefer 'Column 1 1', but pd.read_html() doesn't give us that choice.
        assert_frame_equal(
            result,
            pd.DataFrame({"Unnamed: 0": ["a"], "Column 1": ["b"], "Unnamed: 2": ["c"]}),
        )
        self.assertEqual(errors, [])


class MigrationTest(unittest.TestCase):
    def test_migrate_v0(self):
        v0_params = {"colselectors": [{"colxpath": "foo", "colname": "bar"}]}
        v1_params = {"method": "xpath", **v0_params, "tablenum": 1}

        new_params = migrate_params(v0_params)
        self.assertEqual(new_params, v1_params)


if __name__ == "__main__":
    unittest.main(testRunner=UnittestRunnerThatDoesntAddWarningFilter())
