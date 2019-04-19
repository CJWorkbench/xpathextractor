#!/usr/bin/env python3

from typing import Callable, List, Tuple
import warnings
from html5lib.constants import DataLossWarning
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


def _item_to_string(item) -> str:
    """Convert an XPath-returned item to a string.

    Rules:
    text node => text contents
    """
    if hasattr(item, 'itertext'):
        # This is an Element.
        return ''.join(item.itertext())
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
    else:
        # count(//a) => float. Return list of float.
        return [result]


# Extract columns separately, then zip them together. 
# This essentially the IMPORTXML method
def add_rows_by_zip(tree, colselectors, outtable):
    column_lists = {}
    maxlen = 0
    for col in colselectors:
        try:
            colxpath = col['colxpath']
            colname = col['colname']
            colvals = select(tree, xpath(colxpath))

        except etree.XPathSyntaxError as err:
            raise ColumnExtractionError('Invalid xpath syntax for column %s: %s' % (colname, colxpath))
        except etree.XPathEvalError as err:
            raise ColumnExtractionError('XPath error for column %s: %s' % (colname, err))

        maxlen = max(maxlen, len(colvals))
        column_lists[colname] = pd.Series(colvals) # cast to Series to enable null-padding

    # Pad all column lists to the same length
    # DataFrame constructor will automatically do this if given Series
    newrows = pd.DataFrame(column_lists, columns=outtable.columns)

    # If they're not all the same length, this may mean extraction failed. 
    # Let the user see the data, and give them a warning
    warn_user = (len(set(len(v) for v in column_lists.values())) != 1)

    outtable = pd.concat([outtable, newrows], axis=0).reset_index(drop=True)
    return (outtable, warn_user)


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

    colselectors = params['colselectors']

    outcolnames = [c['colname'] for c in colselectors]
    if '' in outcolnames:
        return 'Missing column name'
    outcolpaths = [c['colxpath'] for c in colselectors]
    if '' in outcolpaths:
        return 'Missing column selector'

    outtable = pd.DataFrame(columns=outcolnames)

    # Loop over rows of input html column, each of which is a complete html document
    # Concatenate rows extracted from each document.
    first_different_length_row = None
    for index,row in table.iterrows():
        html_text = row[inputcol]

        tree = parse_document(html_text, True) # is_html=true 

        try:
            outtable,warn = add_rows_by_zip(tree, colselectors, outtable)
        except ColumnExtractionError as err:
            return str(err)

        # track the first row where the extracted columns are not all the same length
        if warn and not first_different_length_row: 
            first_different_length_row = index

    if first_different_length_row:
        return (outtable, 
                'Extracted columns of differing lengths from HTML on row %d' % first_different_length_row)
    else:
        return outtable

