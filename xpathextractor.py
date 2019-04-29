#!/usr/bin/env python3

from typing import Dict, List, Optional, Tuple
import warnings
from html5lib.constants import DataLossWarning
import html5lib.filters.whitespace
from lxml import etree
from lxml.html import html5parser
import pandas as pd

# Custom exception class used to pass a problem with a particular column
class ColumnExtractionError(Exception):
     pass

# GLOBALLY ignore the warnings that (hopefully) only this module will emit. The
# warnings all have to do with "invalid" HTML, but that HTML is often good
# enough for our users so it isn't worth dumping anything to stderr.
warnings.filterwarnings('ignore', category=DataLossWarning,
                        module=r'html5lib\._ihatexml')

def xpath(s: str) -> etree.XPath:
    """
    Parse an XPath selector, or raise etree.XPathSyntaxError.

    A word on namespaces: this module parses HTML without a namespace.
    It parses embedded SVGs in the "svg" namespace. So your XPath
    selectors can look like:

    xpath('//p')           # all <p> tags (in HTML)
    xpath('//order/@id')   # all <order> id attributes (in XML)
    xpath('//svg:path/@d') # all <path> tags (in SVG embedded within HTML)
    """
    return etree.XPath(
        s,
        smart_strings=True,  # so result strings don't ref XML doc
        namespaces={
            'svg': 'http://www.w3.org/2000/svg',
        }
    )


def parse_document(text: str, is_html: bool) -> etree._Element:
    """Build a etree root node from `text`.

    Throws TODO what errors?
    """
    if is_html:
        parser = html5parser.HTMLParser(namespaceHTMLElements=False)
        tree = html5parser.fromstring(text, parser=parser)
        return tree
    else:
        parser = etree.XMLParser(
            encoding='utf-8',
            # Disable as much as we can, for security
            load_dtd=False,
            collect_ids=False,
            resolve_entities=False
        )
        return etree.fromstring(text.encode('utf-8'), parser)


TreeWalker = html5lib.getTreeWalker('etree')
WhitespaceFilter = html5lib.filters.whitespace.Filter


def _item_to_string(item) -> str:
    """Convert an XPath-returned item to a string.

    Rules:
    text node => text contents
    """
    if hasattr(item, 'itertext'):
        # This is an Element.
        #
        # We need to strip insignificant whitespace but preserve _significant_
        # whitespace. For instance, "<p>a <b> b</b></p>" becomes "a  b" (two
        # spaces); "<p>a  <b>b</b>" becomes one.
        #
        # Many websites have stylesheets that hide _significant_ whitespace --
        # using font-size:0, negative margins, or some-such. We don't use the
        # stylesheet, so we don't get that.
        #
        # Finally, we strip the output. That's what IMPORTXML() does, and the
        # user probably wants it.
        texts = [token['data']
                 for token in WhitespaceFilter(TreeWalker(item))
                 if token['type'] in ('Characters', 'SpaceCharacters')]
        return ''.join(texts).strip()
    else:
        # item.is_attribute
        # item.is_text
        # item.is_tail
        return str(item)


def select(tree: etree._Element, selector: etree.XPath) -> List[str]:
    """
    Run an xpath expression on `tree` and convert results to strings.

    Raise XPathEvalError on error.
    """
    # TODO avoid DoS. xpath selectors can take enormous amounts of CPU/memory
    result = selector(tree)
    if hasattr(result, '__iter__') and not isinstance(result, str):
        return list(_item_to_string(item) for item in result)
    elif isinstance(result, bool):
        # boolean(//a) => bool. Return list of str. (Workbench does not support
        # bool.)
        return [str(result)]
    else:
        # count(//a) => float. Return list of float.
        return [result]


def extract_dataframe_by_zip(
    html: str,
    columns_to_parse: Dict[str, etree.XPath]
) -> Tuple[pd.DataFrame, bool]:
    """
    Extract columns separately, then zip them together.

    This essentially Excel's IMPORTXML() function.

    Returns (dataframe, should_warn); should_warn is True when the columns have
    different lengths.
    """
    tree = parse_document(html, True)  # is_html=true

    # data: {name: Series of text values per selector}, in order.
    # The series may be of different length.
    data = {}
    for name, selector in columns_to_parse.items():
        try:
            data[name] = pd.Series(select(tree, selector), dtype=str)
        except etree.XPathEvalError as err:
            raise ColumnExtractionError('XPath error for column "%s": %s'
                                        % (name, str(err)))

    # Pad all column lists to the same length
    # DataFrame constructor will automatically do this if given Series
    table = pd.DataFrame(data)

    # If they're not all the same length, this may mean extraction failed.
    # Let the user see the data, and give them a warning
    #
    # We detect by checking if any value in the last row is null.
    should_warn = len(table) and table.iloc[-1].isnull().any()

    return (table, should_warn)


def render(table, params):
    # Suggest quickfix of adding Scrape HTML if 'html' col not found
    inputcol = 'html'
    if inputcol not in table.columns:
        return {
            'error': "No 'html' column found. Do you need to scrape?",
            'quick_fixes': [{
                'text': 'Add HTML scraper',
                'action': 'prependModule',
                'args': [
                    'urlscraper',
                    {}
                ],
            }]
        }

    # load params
    # dict of { name: str -> etree.XPath } -- ordered as the input is ordered.
    columns_to_parse = {}
    for c in params['colselectors']:
        colname = c['colname']
        colxpath = c['colxpath']
        if not colname:
            return 'Missing column name'
        if colname in columns_to_parse:
            return f'Duplicate column name "{colname}"'
        if not colxpath:
            return 'Missing column selector'
        try:
            selector = xpath(c['colxpath'])
        except etree.XPathSyntaxError as err:
            return (
                'Invalid XPath syntax for column "%s": %s'
                % (colname, str(err))
            )
        columns_to_parse[colname] = selector

    if not columns_to_parse:
        # User hasn't input anything. Return input, as is our convention.
        return table

    # Loop over rows of input html column, each of which is a complete html document
    # Concatenate rows extracted from each document.
    result_tables = []
    input_row_with_warning = None
    for index, html in table['html'].iteritems():
        if html is None:
            continue
        try:
            one_result, warn = extract_dataframe_by_zip(html, columns_to_parse)
        except ColumnExtractionError as err:
            return str(err)
        result_tables.append(one_result)
        # track the first row where the extracted columns are not all the same
        # length
        if warn and input_row_with_warning is None:
            input_row_with_warning = index

    if result_tables:
        outtable = pd.concat(result_tables, ignore_index=True)
    else:
        # Empty table
        outtable = pd.DataFrame(
            {colname: [] for colname in columns_to_parse.keys()},
            dtype=str
        )

    if input_row_with_warning is not None:
        return (
            outtable,
            (
                'Extracted columns of differing lengths from HTML on row %d'
                % (input_row_with_warning + 1)
            )
        )
    else:
        return outtable
