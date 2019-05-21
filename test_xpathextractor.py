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
        self.assertEqual(self.select('boolean(//f)'), ['True'])
        self.assertEqual(self.select('boolean(//g)'), ['False'])


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

    def test_clean_insignificant_whitespace(self):
        tree = parse_document(
            '<html><body><p>\n  hi <b class="X"> !</b>\n</p></body></html>',
            True
        )
        result = select(tree, xpath('//p'))
        self.assertEqual(result, ['hi  !'])


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

    def test_html5lib_whitespace_crash(self):
        # User found a page where `//h3` selector causes TreeWalker to crash
        # https://www.kpu.ca/calendar/2018-19/courses/jrnl/index.html as of 2019-5-20

        html = '''
<!doctype html><html lang="en" dir="ltr"><head>   <title>KPU 2018-19 University Calendar | Journalism (JRNL)</title>   <link rel="stylesheet"         type="text/css"         href="/calendar/2018-19/css/wysiwyg-styles.css"         media="screen"/>   <link rel="stylesheet"         type="text/css"         href="/calendar/2018-19/css/style.css"         media="screen"/>   <link rel="stylesheet"         type="text/css"         href="/calendar/2018-19/css/print.css"         media="print"/>   <meta http-equiv="Content-Type" content="text/html; charset=UTF-8"/>    <!-- com.omniupdate.properties -->        <meta name="keywords" content="Journalism, Courses"/>       <meta name="description" content="Journalism courses"/>   <!-- /com.omniupdate.properties -->   </head><body id="courses">   <a href="#main-content" class="element-invisible element-focusable">Skip to main content</a>   <div id="header-wrapper">      <div class="top-links">         <div class="container">            <ul>               <li>                  <a href="http://www.kpu.ca">KPU.ca</a>               </li>               <li>                  <a href="http://www.kpu.ca/apply">Apply Now</a>               </li>               <li>                  <a href="http://www.kpu.ca/contact">Contact</a>               </li>            </ul>         </div>      </div>      <div class="container">         <header role="banner" class="row">            <div class="siteinfo">               <div class="logo"><!-- com.omniupdate.div label="printlogo" path="/includes/printlogo.inc"--><a title="Home" href="/"> <img class="logo-img" src="/calendar/2018-19/images/logo-mobile-colour.png" alt="KPU Logo" width="96" height="87" /> </a><!-- /com.omniupdate.div --></div>            </div>            <div class="header-region"><!-- com.omniupdate.div label="calendar_year" path="/includes/calendar_year.inc"--><p>2018-19</p><p>University Calendar</p><p>Effective Sep 2018 – Aug 2019</p><!-- /com.omniupdate.div --></div>         </header>      </div>   </div>   <div id="content-wrapper" class="fullwidth">      <div class="container content-container">         <div class="page row">            <div role="main" class="main-content" id="#main-content">               <div id="location">                  <ul>                     <li>                        <a href="http://www.kpu.ca">KPU</a>                     </li>                     <li>                        <a href="http://www.kpu.ca/calendar">Calendars</a>                     </li>                     <li>                        <a href="/calendar/2018-19/">2018-19</a>                     </li>                     <li>                        <a href="/calendar/2018-19/courses/">Course Descriptions</a>                     </li>                     <li>                        <a href="/calendar/2018-19/courses/jrnl/">JRNL</a>                     </li>                     <li>Journalism</li>                  </ul>               </div>               <div class="calendar-search"><!-- com.omniupdate.div label="cal-search" path="/includes/calsearch.inc" --><form id="cal-search" action="http://www.kpu.ca/calendar/2018-19/search.html" name="cal-search">    <label class="visuallyhidden" for="cal-lookup">Search the University Calendar</label>    <input id="cal-lookup" class="placeholder" type="text" name="k" />    <input type="submit" value="Search" /> </form><ul>    <li class="first"><em>Or View:</em></li>    <li><a href="/calendar/2018-19/courses/">Course Descriptions</a></li>    <li><a href="/calendar/2018-19/program_indices.html">Program Index</a></li>    <!-- <li class="last"><a href="/calendar/2018-19/sitemap.html">Calendar Site Map</a></li> --></ul><!-- /com.omniupdate.div --></div>               <div id="user-options">                  <ul>                     <li>                        <a href="index.pdf" class="social_pdf">Download PDF</a>                     </li>                  </ul>               </div>               <div class="main-content-inner">                  <div class="region-content">                     <article class="node node-page" role="article">                        <div class="content">                           <h1 class="page-title">Journalism (JRNL)</h1>                                         <!-- com.omniupdate.div  label="maincontent"  group="Courses"  button="707"  break="break" -->                                  <!-- com.omniupdate.editor csspath="/_resources/ou/editor/maincontent.css" cssmenu="/_resources/ou/editor/cssmenu.txt" width="955" -->                                  <p>This is a list of the Journalism (JRNL) courses available at KPU.</p>                           <p>Enrolment in some sections of these courses is restricted to students in particular programs. See the <a href="/registration/timetables" target="_blank">Course Planner</a> - <a href="/registration/timetables" target="_blank">kpu.ca/registration/timetables</a> - for current information about individual courses.</p>                           <p>For information about transfer of credit amongst institutions in B.C. and to see how individual courses transfer, go to the BC Transfer Guide <a href="http://www.bctransferguide.ca/" target="_blank">bctransferguide.ca</a>                           </p>                                     <!-- /com.omniupdate.div -->                                 <h3>                              <a name="jrnl1160" id="jrnl1160"><!--jrnl1160--></a>JRNL 1160<span>3 Credits</span>                           </h3>                           <h4>Introduction to Journalism</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- com.omniupdate.multiedit type="textarea" prompt="Course Description" alt="Required" rows="3" editor="yes" -->                           <p>Students will explore how journalism fits in a media landscape that includes both traditional mainstream news sources and alternative information sources such as social networking, YouTube, Twitter and blogs. They will also explore reporting by citizen journalists. Students will explore the ramifications of economic and technological change in the industry. They will also study its impact on journalists and journalism, citizens, human rights, community and democracy.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                        <!-- com.omniupdate.div group="Courses" label="pre-reqs" button="hide" --><!-- com.omniupdate.multiedit type="textarea" prompt="Pre-requisites" alt="Optional" rows="3" editor="yes" -->A grade of 'B' in English 12 (or equivalent)<!-- /com.omniupdate.div --></em>                           </p>                           <h3>                              <a name="jrnl1220" id="jrnl1220"><!--jrnl1220--></a>JRNL 1220<span>3 Credits</span>                           </h3>                           <h4>Citizen Journalism</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- ouc:multiedit type="textarea" prompt="Course Description" alt="Required" rows="3" editor="yes"/ -->                           <p>Students will explore the role of citizen journalism in the dissemination of information. They will explore the investigative techniques commonly employed by professional journalists, including but not limited to court searches and Freedom of Information requests. They will learn how to use many of these techniques to find information important to themselves and their communities. They will discover how tools such as blogging, social networking and search engine optimization can be used to share this information with the larger community. They will learn how to write clearly and concisely. Students will also explore how media law affects citizen journalism, and vice versa.</p>                           <!-- /com.omniupdate.div -->                           <h3>                              <a name="jrnl2120" id="jrnl2120"><!--jrnl2120--></a>JRNL 2120<span>3 Credits</span>                           </h3>                           <h4>Storytelling: Writing for Journalism</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- ouc:multiedit type="textarea" prompt="Course Description" alt="Required" rows="3" editor="yes"/ -->                           <p>Students will be introduced to and practice journalistic writing, which is a distinct style of writing. In this class, students will learn the fundamental skills of news writing and reporting, including conducting interviews, covering news events, analyzing source documents and writing clearly and concisely. They will use the Canadian Press Style guide, which is the standard for journalistic writing in Canada.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                         JRNL 1160 and JRNL 1220</em>                           </p>                           <h3>                              <a name="jrnl2230" id="jrnl2230"><!--jrnl2230--></a>JRNL 2230<span>3 Credits</span>                           </h3>                           <h4>Multimedia Storytelling</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- ouc:multiedit type="textarea" prompt="Course Description" alt="Required" rows="3" editor="yes"/ -->                           <p>Students will explore the types of multimedia journalism and other non-fiction storytelling made possible by inexpensive hardware and software tools, and the ability to easily publish on the internet and through social media. They will explore the role of audio, video and interactivity in creating rich, immersive stories, through profiles, event coverage, journalistic storytelling and other modes. Students will learn storytelling and technical skills needed to create and publish effective stories of their own.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                        JRNL 1160 or JRNL 1220</em>                           </p>                           <h3>                              <a name="jrnl2240" id="jrnl2240"><!--jrnl2240--></a>JRNL 2240<span>3 Credits</span>                           </h3>                           <h4>Beyond News: Feature Writing</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- ouc:multiedit type="textarea" prompt="Course Description" alt="Required" rows="3" editor="yes"/ -->                           <p>Students will practice and develop feature writing skills in subject areas including, but not limited to, health and science, education, sports, entertainment, fashion and lifestyles, and opinion writing. Students will explore the evolving mediascape, which includes traditional media and new-media competitors, and examine differences in writing styles and presentation. They will examine the potential for accessing and providing in-depth information in specialist and niche areas, analyze publications, and develop and publish traditional or non-traditional feature stories.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                      JRNL 1160, JRNL 1220, JRNL 2120</em>                           </p>                           <h3>                              <a name="jrnl2360" id="jrnl2360"><!--jrnl2360--></a>JRNL 2360<span>3 Credits</span>                           </h3>                           <h4>Visual Storytelling</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- com.omniupdate.multiedit type="textarea" prompt="Calendar Description" alt="Required" rows="3" editor="yes" -->                           <p>Students will explore a range of visual storytelling techniques and technologies, with an emphasis on still photography for print and online publications, and for social media storytelling. They will gain practical experience while capturing subjects in a variety of lighting conditions and locations, requiring different techniques. Students will learn visual imaging software and the principles of visual journalism design and publishing. Note: Students are required to have camera capable of full manual operation for this course. Specifications will be provided by the department.<br/>NOTE: Students may earn credit for only one of JRNL 2360 or JRNL 3160.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                        <!-- com.omniupdate.div group="Courses" label="pre-reqs" button="hide" --><!-- com.omniupdate.multiedit type="textarea" prompt="Pre-requisites" alt="Optional" rows="3" editor="yes" -->JRNL 1160 or JRNL 1220<!-- /com.omniupdate.div --></em>                           </p>                           <h3>                              <a name="jrnl2370" id="jrnl2370"><!--jrnl2370--></a>JRNL 2370<span>3 Credits</span>                           </h3>                           <h4>Audio Storytelling</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- com.omniupdate.multiedit type="textarea" prompt="Calendar Description" alt="Required" rows="3" editor="yes" -->                           <p>Students will learn the fundamentals of telling true stories using audio. Effective use of recording, editing and publishing tools will be taught, alongside planning, reporting, structuring, writing and editing skills, and ethics. Students will study, produce, and publish audio stories in styles including professional-level broadcast and podcasts.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                        <!-- com.omniupdate.div group="Courses" label="pre-reqs" button="hide" --><!-- com.omniupdate.multiedit type="textarea" prompt="Pre-requisites" alt="Optional" rows="3" editor="yes" -->JRNL 1160 or JRNL 1220<!-- /com.omniupdate.div --></em>                           </p>                           <h3>                              <a name="jrnl3165" id="jrnl3165"><!--jrnl3165--></a>JRNL 3165<span>3 Credits</span>                           </h3>                           <h4>Data Visualization</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- com.omniupdate.multiedit type="textarea" prompt="Calendar Description" alt="Required" rows="3" editor="yes" -->                           <p>Students will learn how to use data visualization techniques to present information in interesting and compelling ways, including interactive maps and graphics. They will explore the principles of data visualization, learn the strengths and weaknesses of various chart types, and create charts that convey information as clearly as possible. They will learn how to use spreadsheets to find interesting patterns in their data and how to turn that data into engaging online tools. They will also learn how to obtain raw data from open-data portals and other sources.<br/>NOTE: Students may earn credit for only one of JRNL 3165 or JRNL 4165.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                      <!-- com.omniupdate.div group="Courses" label="pre-reqs" button="hide" --><!-- com.omniupdate.multiedit type="textarea" prompt="Pre-requisites" alt="Optional" rows="3" editor="yes" -->45 credits from courses at the 1100 level or higher<!-- /com.omniupdate.div --></em>                           </p>                           <p class="preq">                              <em>Attributes:                     <a href="http://www.kpu.ca/calendar/2018-19/courses/attributes.html#QUAN">QUAN</a>                              </em>                           </p>                           <h3>                              <a name="jrnl3170" id="jrnl3170"><!--jrnl3170--></a>JRNL 3170<span>3 Credits</span>                           </h3>                           <h4>Narrative Nonfiction</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- ouc:multiedit type="textarea" prompt="Course Description" alt="Required" rows="3" editor="yes"/ -->                           <p>Students will learn about the art of narrative nonfiction, which marries strong journalism with literary technique to produce compelling stories. Students will analyze published narrative nonfiction, such as magazine articles, books, and personal essays. They will develop their voices as narrative nonfiction writers by practicing the art of this type of journalism.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                      45 credits from courses at the 1100 level or higher, including JRNL 2240 and ENGL 1100.</em>                           </p>                           <h3>                              <a name="jrnl3180" id="jrnl3180"><!--jrnl3180--></a>JRNL 3180<span>3 Credits</span>                           </h3>                           <h4>Sports Journalism</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- ouc:multiedit type="textarea" prompt="Calendar Description" alt="Required" rows="3" editor="yes"/ -->                           <p>Students will explore the full range of sports journalism, analyzing how sports reporters operate across the platforms of print, broadcast, online and social media. They will examine and create a wide range of sports journalism, including but not limited to game coverage and features, sports beat coverage, long-form sports storytelling and in-depth sports packages using text, images, video and interactivity. Students will also analyze the history, contemporary issues and ethics of sports journalism.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                       <!-- com.omniupdate.div group="Courses" label="pre-reqs" button="hide" --><!-- ouc:multiedit type="textarea" prompt="Pre-requisites" alt="Optional" rows="3" editor="yes"/ -->JRNL 2230 and JRNL 2240<!-- /com.omniupdate.div --></em>                           </p>                           <h3>                              <a name="jrnl3260" id="jrnl3260"><!--jrnl3260--></a>JRNL 3260<span>3 Credits</span>                           </h3>                           <h4>Media Economics and Entrepreneurial Journalism</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- ouc:multiedit type="textarea" prompt="Course Description" alt="Required" rows="3" editor="yes"/ -->                           <p>Students will explore the economics of existing and emerging media. They will also explore the implications and opportunities for journalists working in traditional and new media. They will learn skills, techniques and technologies needed for developing a professional reputation and personal brand. Students will learn the organizational, business and personal skills needed for freelance employment, and for leading or working as a team member with media start-up companies.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                      <!-- com.omniupdate.div group="Courses" label="pre-reqs" button="hide" --><!-- ouc:multiedit type="textarea" prompt="Pre-requisites" alt="Optional" rows="3" editor="yes"/ -->45 credits from courses at the 1100 level or higher, including ENGL 1100, JRNL 1220, JRNL 2120, and JRNL 2230.<!-- /com.omniupdate.div --></em>                           </p>                           <h3>                              <a name="jrnl3270" id="jrnl3270"><!--jrnl3270--></a>JRNL 3270<span>3 Credits</span>                           </h3>                           <h4>Advanced Visual Storytelling</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- ouc:multiedit type="textarea" prompt="Course Description" alt="Required" rows="3" editor="yes"/ -->Students will expand their visual storytelling skills with an emphasis on filming, editing and producing video. They will explore the legal and ethical aspects of video storytelling and consider its role in public discourse. They will learn how to apply basic visual storytelling skills to video, and the role images, sound, music and text play in video storytelling. Students will learn video-editing skills using professional-level software and will produce a long-form video documentary.<!-- /com.omniupdate.div --><p class="preq">                              <em>Prerequisites:                       45 credits from courses at the 1100 level or higher, including JRNL 2230, JRNL 2240, and JRNL 2360</em>                           </p>                           <h3>                              <a name="jrnl3370" id="jrnl3370"><!--jrnl3370--></a>JRNL 3370<span>3 Credits</span>                           </h3>                           <h4>Advanced Audio Storytelling</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- com.omniupdate.multiedit type="textarea" prompt="Calendar Description" alt="Required" rows="3" editor="yes" -->                           <p>Students will expand their audio storytelling skills while working throughout the semester, as part of a production team, to produce a long-form audio story. They will explore the legal and ethical aspects of storytelling and consider its role in public discourse. They will further develop technical skills in capturing and editing audio.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                         <!-- com.omniupdate.div group="Courses" label="pre-reqs" button="hide" --><!-- com.omniupdate.multiedit type="textarea" prompt="Pre-requisites" alt="Optional" rows="3" editor="yes" -->45 credits from courses at the 1100 level or higher, including JRNL 2230, JRNL 2240 and JRNL 2370.<!-- /com.omniupdate.div --></em>                           </p>                           <h3>                              <a name="jrnl4141" id="jrnl4141"><!--jrnl4141--></a>JRNL 4141<span>3 Credits</span>                           </h3>                           <h4>Work Experience</h4>                           <!-- com.omniupdate.div group="Admin" label="course-desc" button="hide" -->                           <!-- com.omniupdate.multiedit type="textarea" prompt="Course Description" alt="Required" rows="3" editor="yes" -->                           <p>Students will work for 120 hours, or equivalent, as journalists in one or more media businesses or organizations. They will further their personal and professional development, integrating knowledge and skills acquired from the Journalism curriculum in the context of their practical experience. They will investigate potential job markets through the work-experience placements they choose, such as freelance work, job shadowing and fixed-term placements. They will develop their journalistic skills in areas of interest to build contacts and create networks that will help them in their careers.<br>NOTE: Placements must be approved by the department.</br>                              <br>NOTE: Students must be registered in the Bachelor of Journalism and have a minimum GPA of 3.3.</br>                              <br>NOTE: Equivalency to 120 hours is determined by the department based on work produced in a project- based placement or placements.</br>                           </p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                         <!-- com.omniupdate.div group="Admin" label="pre-reqs" button="hide" --><!-- com.omniupdate.multiedit type="textarea" prompt="Pre-requisites" alt="Optional" rows="3" editor="yes" -->90 credits from courses at the 1100 level or higher, including 18 credits from courses in JRNL at the 3000 level or higher.<!-- /com.omniupdate.div --></em>                           </p>                           <h3>                              <a name="jrnl4180" id="jrnl4180"><!--jrnl4180--></a>JRNL 4180<span>3 Credits</span>                           </h3>                           <h4>Advanced Sports Journalism</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- com.omniupdate.multiedit type="textarea" prompt="Calendar Description" alt="Required" rows="3" editor="yes" -->                           <p>Students will deepen their sports journalism reporting skills, while exploring sports journalism as a profession. They will interview local professional sports journalists and attend and cover large- scale sports events alongside them. They will also explore the differences and similarities in coverage when sports stories move beyond the sports page and into wider public interest, by discussing and covering issues such as: concussion in sports; the relationship between sports and racism; and issues of sexism in sports and sports journalism.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                        <!-- com.omniupdate.div group="Courses" label="pre-reqs" button="hide" --><!-- com.omniupdate.multiedit type="textarea" prompt="Pre-requisites" alt="Optional" rows="3" editor="yes" -->60 credits from courses at the 1100 level or higher, including ENGL 1100 and JRNL 3180<!-- /com.omniupdate.div --></em>                           </p>                           <h3>                              <a name="jrnl4190" id="jrnl4190"><!--jrnl4190--></a>JRNL 4190<span>3 Credits</span>                           </h3>                           <h4>Directed Study Honours I - Research</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- com.omniupdate.multiedit type="textarea" prompt="Course Description" alt="Required" rows="3" editor="yes" -->                           <p>Students working under the supervision of a faculty member will identify a topic for their honours thesis and undertake a research program that includes an extensive reading list developed by the student and faculty supervisor. They will design an outline for their thesis project.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                         JRNL 3200</em>                           </p>                           <h3>                              <a name="jrnl4240" id="jrnl4240"><!--jrnl4240--></a>JRNL 4240<span>3 Credits</span>                              <br/>                              <small>(Formerly                      JRNL 3120)</small>                           </h3>                           <h4>Social Issues Journalism</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- ouc:multiedit type="textarea" prompt="Course Description" alt="Required" rows="3" editor="yes"/ -->                           <p>Students will analyze social-issues journalism, do research and write social-issues journalism on subjects of their choice. They will learn, and draw on, the traditions of social-issues journalism, a long-established branch of journalism that ranges from the work of early social commentators such as Charles Dickens to today's investigative reporters. Students will combine narrative writing and investigative reporting to cover important issues by issuing readers an invitation to work for change.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                        45 credits from courses at the 1100 level or higher, including ENGL 1100 and JRNL 2240.</em>                           </p>                           <h3>                              <a name="jrnl4250" id="jrnl4250"><!--jrnl4250--></a>JRNL 4250<span>3 Credits</span>                           </h3>                           <h4>Politics and Journalism II</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- ouc:multiedit type="textarea" prompt="Course Description" alt="Required" rows="3" editor="yes"/ -->                           <p>Students will produce political journalism by conducting in-depth research and interviews using a variety of sources. They will also explore issues such as the watchdog role of journalism in a democracy and the relationship among politicians, bureaucrats, non-governmental organizations (NGOs) and journalists. Students will learn the importance of political journalism to democracy.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                         45 credits from courses at the 1100 level or higher courses, including ENGL 1100, JRNL 2230, and JRNL 2240.</em>                           </p>                           <h3>                              <a name="jrnl4260" id="jrnl4260"><!--jrnl4260--></a>JRNL 4260<span>3 Credits</span>                           </h3>                           <h4>Computer Coding for Journalists</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- ouc:multiedit type="textarea" prompt="Course Description" alt="Required" rows="3" editor="yes"/ -->                           <p>Students will be exposed to, and work in several programming and scripting languages, including, but not limited to HTML, CSS and JavaScript. These programs are used to create visually rich, interactive apps, websites and webpages. They will apply a range of skills to create and publish interactives; and also, design, develop and deploy applications.<br/>NOTE: This is a hands-on course, which requires basic computer literacy; previous knowledge of computer and website programming is not required.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                      45 credits from courses at the 1100-level or higher, including JRNL 2230 and JRNL 2240.</em>                           </p>                           <h3>                              <a name="jrnl4270" id="jrnl4270"><!--jrnl4270--></a>JRNL 4270<span>3 Credits</span>                           </h3>                           <h4>Advanced Storytelling</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- ouc:multiedit type="textarea" prompt="Course Description" alt="Required" rows="3" editor="yes"/ -->                           <p>Students will work as a newsroom team during the semester to report and produce stories for a single-theme on-line publication (a story package). Students will develop the initial concept and identify stories using the full-range of storytelling methods (narrative text, visualized data, video, audio, photography, etc.). They will also learn or deepen skills in story planning, storytelling, story presentation and interactivity. They will produce a final project that will be a rich and interactive website on the assigned topic.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                      60 credits of 1100-level or higher, including all of the following: (a) ENGL 1100, (b) JRNL 3165, (c) JRNL 3170 or 4240, and (d) JRNL 3270 or 3370.</em>                           </p>                           <h3>                              <a name="jrnl4290" id="jrnl4290"><!--jrnl4290--></a>JRNL 4290<span>3 Credits</span>                           </h3>                           <h4>Honours Thesis</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- com.omniupdate.multiedit type="textarea" prompt="Course Description" alt="Required" rows="3" editor="yes" -->                           <p>Students working under the supervision of a faculty member will write an honours thesis based on the research and outline completed in Journalism 4190. Students will engage in an extensive process of draft-writing and revisions to produce the final thesis.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                      JRNL 4190</em>                           </p>                           <h3>                              <a name="jrnl4295" id="jrnl4295"><!--jrnl4295--></a>JRNL 4295<span>3 Credits</span>                           </h3>                           <h4>Journalism Honours Seminar</h4>                           <!-- com.omniupdate.div group="Courses" label="course-desc" button="hide" -->                           <!-- com.omniupdate.multiedit type="textarea" prompt="Course Description" alt="Required" rows="3" editor="yes" -->                           <p>Students will explore contemporary mass communication and journalism issues and research strategies. They will examine advanced methodological approaches to mass communications and journalism research though critical evaluation and evaluate the strengths and weaknesses of a variety of research methods. This course is mandatory for those students registered in the Bachelor of Applied Journalism Honours Degree.</p>                           <!-- /com.omniupdate.div -->                           <p class="preq">                              <em>Prerequisites:                        Admission to the Bachelor of Applied Journalism</em>                           </p>                           <!-- com.omniupdate.ob --><p class="last-update"><a href="http://a.cms.omniupdate.com/10?skin=oucampus&amp;account=kpu-ca&amp;site=2018-19&amp;action=de&amp;path=/courses/jrnl/index.pcf">Last Updated: 13-Jun-2018</a></p><!-- /com.omniupdate.ob -->                        </div>                     </article>                     <div id="calendar-disclaimer"><!-- com.omniupdate.div label="disclaimer" path="/includes/disclaimer.inc"--><p>This online version of the Kwantlen Polytechnic University Calendar is the official version of the University Calendar. Although every effort is made to ensure accuracy at the time of publication, KPU reserves the right to make any corrections in the contents and provisions of this calendar without notice. In addition, the University reserves the right to cancel, add, or revise contents or change fees at any time without notice. To report errors or omissions, or send comments or suggestions, please email <span style="text-decoration: underline;">Calendar.Editor@kpu.ca</span></p><!-- /com.omniupdate.div --></div>                  </div>               </div>            </div>            <div class="sidebar-first">               <div class="region-sidebar-first">                  <nav id="block-menu-block-1"                       class="block block-menu-block"                       role="navigation">                     <h2 class="title block-title">                        <a href="/calendar/2018-19">University Calendar</a>                     </h2>                     <ul><!-- com.omniupdate.div label="local-sidenav" group="admin" button="702" path="/courses/includes/sidenav.inc" --><!-- ouc:editor csspath="/_resources/ou/editor/sidenav.css" cssmenu="/_resources/ou/editor/sidenav.txt" width="798"/ --><li><em><a href="/calendar/2018-19/courses/attributes.html">Course Attributes</a></em></li><li><em><a href="/calendar/2018-19/courses/mathalternatives.html">Math Alternatives Table</a></em></li><li><em><a href="/calendar/2018-19/courses/quantitative.html">Quantitative Courses</a></em></li><li><em><a href="/calendar/2018-19/courses/pathwaycourses.html">Undergraduate Courses for Pathway Studies</a></em></li><li><em><a href="/calendar/2018-19/courses/outlinereqs.html">Requesting Official Course Outlines</a></em></li><li><a href="/calendar/2018-19/courses/appd/">Access Programs for People with Disabilities (APPD)</a></li><li><a href="/calendar/2018-19/courses/acct/">Accounting (ACCT)</a></li><li><a href="/calendar/2018-19/courses/acup/index.html">Acupuncture (ACUP)</a></li><li><a href="/calendar/2018-19/courses/agri/index.html">Agriculture (AGRI)</a></li><li><a href="/calendar/2018-19/courses/anth/">Anthropology (ANTH)</a></li><li><a href="/calendar/2018-19/courses/appl/">Appliance Servicing (APPL)</a></li><li><a href="/calendar/2018-19/courses/abty/">Applied Business Technology (ABTY)</a></li><li><a href="/calendar/2018-19/courses/cmns/">Applied Communications (CMNS)</a></li><li><a href="/calendar/2018-19/courses/apsc/">Applied Science (APSC)</a></li><li><a href="/calendar/2018-19/courses/arth/">Art History (ARTH)</a></li><li><a href="/calendar/2018-19/courses/arts/index.html">Arts (ARTS)</a></li><li><a href="/calendar/2018-19/courses/asia/">Asian Studies (ASIA)</a></li><li><a href="/calendar/2018-19/courses/astr/">Astronomy (ASTR)</a></li><li><a href="/calendar/2018-19/courses/asta/">Automotive Service Technician (ASTA)</a></li><li><a href="/calendar/2018-19/courses/biol/index.html">Biology (BIOL)</a></li><li><a href="/calendar/2018-19/courses/bioq/index.html">Biology Qualifying (BIOQ)</a></li><li><a href="/calendar/2018-19/courses/hops/index.html">Brewing &amp; Brewery Operations (HOPS)</a></li><li><a href="/calendar/2018-19/courses/buqu/index.html">Business &amp; Quantitative Methods (BUQU)</a></li><li><a href="/calendar/2018-19/courses/busi/index.html">Business (BUSI)</a></li><li><a href="/calendar/2018-19/courses/busm/index.html">Business Management (BUSM)</a></li><li><a href="/calendar/2018-19/courses/carp/index.html">Carpentry/Building Construction (CARP)</a></li><li><a href="/calendar/2018-19/courses/chem/index.html">Chemistry (CHEM)</a></li><li><a href="/calendar/2018-19/courses/cheq/index.html">Chemistry Qualifying (CHEQ)</a></li><li><a href="/calendar/2018-19/courses/comm/index.html">Communications (COMM)</a></li><li><a href="/calendar/2018-19/courses/cahs/index.html">Community And Health Studies (CAHS)</a></li><li><a href="/calendar/2018-19/courses/cadd/index.html">Computer Aided Design &amp; Drafting (CADD)</a></li><li><a href="/calendar/2018-19/courses/cada/index.html">Computer Aided Design &amp; Drafting: Architectural (CADA)</a></li><li><a href="/calendar/2018-19/courses/cadi/index.html">Computer Aided Design &amp; Drafting: Industrial (CADI)</a></li><li><a href="/calendar/2018-19/courses/cadm/index.html">Computer Aided Design &amp; Drafting: Manufacturing and Fabrication (CADM)</a></li><li><a href="/calendar/2018-19/courses/cads/index.html">Computer Aided Design &amp; Drafting: Structural (CADS)</a></li><li><a href="/calendar/2018-19/courses/cbsy/index.html">Computer Business Systems (CBSY)</a></li><li><a href="/calendar/2018-19/courses/cpsc/index.html">Computer Science (CPSC)</a></li><li><a href="/calendar/2018-19/courses/coop/index.html">Co-operative Education (COOP)</a></li><li><a href="/calendar/2018-19/courses/cnps/index.html">Counselling Psychology (CNPS)</a></li><li><a href="/calendar/2018-19/courses/crwr/index.html">Creative Writing (CRWR)</a></li><li><a href="/calendar/2018-19/courses/crim/index.html">Criminology (CRIM)</a></li><li><a href="/calendar/2018-19/courses/cust/index.html">Cultural Studies (CUST)</a></li><li><a href="/calendar/2018-19/courses/desn/index.html">Design (DESN)</a></li><li><a href="/calendar/2018-19/courses/econ/index.html">Economics (ECON)</a></li><li><a href="/calendar/2018-19/courses/edas/index.html">Education Assistant (EDAS)</a></li><li><a href="/calendar/2018-19/courses/educ/index.html">Educational Studies (EDUC)</a></li><li><a href="/calendar/2018-19/courses/elec/index.html">Electrical (ELEC)</a></li><li><a href="/calendar/2018-19/courses/engl/index.html">English (ENGL)</a></li><li><a href="/calendar/2018-19/courses/engt/index.html">English for Trades (ENGT)</a></li><li><a href="/calendar/2018-19/courses/elst/">English Language Studies (ELST)</a></li><li><a href="/calendar/2018-19/courses/elsq/index.html">English Language Studies Qualifying (ELSQ)</a></li><li><a href="/calendar/2018-19/courses/engq/index.html">English Qualifying (ENGQ)</a></li><li><a href="/calendar/2018-19/courses/entr/index.html">Entrepreneurial Leadership (ENTR)</a></li><li><a href="/calendar/2018-19/courses/envi/index.html">Environmental Protection Technology (ENVI)</a></li><li><a href="/calendar/2018-19/courses/farr/index.html">Farrier Training (FARR)</a></li><li><a href="/calendar/2018-19/courses/fasn/index.html">Fashion and Technology (FASN)</a></li><li><a href="/calendar/2018-19/courses/fmrk/index.html">Fashion Marketing (FMRK)</a></li><li><a href="/calendar/2018-19/courses/fnsr/index.html">Financial Services (FNSR)</a></li><li><a href="/calendar/2018-19/courses/fina/index.html">Fine Arts (FINA)</a></li><li><a href="/calendar/2018-19/courses/find/index.html">Foundations in Design (FIND)</a></li><li><a href="/calendar/2018-19/courses/fren/index.html">French (FREN)</a></li><li><a href="/calendar/2018-19/courses/geog/index.html">Geography (GEOG)</a></li><li><a href="/calendar/2018-19/courses/ibus/index.html">Global Business Management (IBUS)</a></li><li><a href="/calendar/2018-19/courses/glbl/index.html">Global Competencies (GLBL)</a></li><li><a href="/calendar/2018-19/courses/gnie/index.html">Graduate Nurse Internationally Educated Re-entry (GNIE)</a></li><li><a href="/calendar/2018-19/courses/gnqu/index.html">Graduate Nurse Qualifying (GNQU)</a></li><li><a href="/calendar/2018-19/courses/gdma/index.html">Graphic Design For Marketing (GDMA)</a></li><li><a href="/calendar/2018-19/courses/grmt/index.html">Green Business Management and Sustainability (GRMT)</a></li><li><a href="/calendar/2018-19/courses/heal/index.html">Health (HEAL)</a></li><li><a href="/calendar/2018-19/courses/hcap/index.html">Health Care Assistant (HCAP)</a></li><li><a href="/calendar/2018-19/courses/hsci/index.html">Health Sciences (HSCI)</a></li><li><a href="/calendar/2018-19/courses/hauc/index.html">Health Unit Coordinator (HAUC)</a></li><li><a href="/calendar/2018-19/courses/hist/index.html">History (HIST)</a></li><li><a href="/calendar/2018-19/courses/hort/index.html">Horticulture (HORT)</a></li><li><a href="/calendar/2018-19/courses/hrmt/index.html">Human Resources Management (HRMT)</a></li><li><a href="/calendar/2018-19/courses/indg/index.html">Indigenous Studies (INDG)</a></li><li><a href="/calendar/2018-19/courses/info/index.html">Information Technology (INFO)</a></li><li><a href="/calendar/2018-19/courses/idea/index.html">Interdisciplinary Expressive Arts (IDEA)</a></li><li><a href="/calendar/2018-19/courses/idsn/index.html">Interior Design (IDSN)</a></li><li><a href="/calendar/2018-19/courses/japn/index.html">Japanese (JAPN)</a></li><li><a href="/calendar/2018-19/courses/jrnl/index.html">Journalism (JRNL)</a></li><li><a href="/calendar/2018-19/courses/lanc/index.html">Language and Cultures (LANC)</a></li><li><a href="/calendar/2018-19/courses/lcom/index.html">Learning Communities (LCOM)</a></li><li><a href="/calendar/2018-19/courses/lgla/index.html">Legal Administrative Studies (LGLA)</a></li><li><a href="/calendar/2018-19/courses/ling/index.html">Linguistics (LING)</a></li><li><a href="/calendar/2018-19/courses/mand/index.html">Mandarin (MAND)</a></li><li><a href="/calendar/2018-19/courses/mrkt/index.html">Marketing (MRKT)</a></li><li><a href="/calendar/2018-19/courses/msry/index.html">Masonry (MSRY)</a></li><li><a href="/calendar/2018-19/courses/matt/index.html">Math for Trades (MATT)</a></li><li><a href="/calendar/2018-19/courses/math/index.html">Mathematics (MATH)</a></li><li><a href="/calendar/2018-19/courses/matq/index.html">Mathematics Qualifying (MATQ)</a></li><li><a href="/calendar/2018-19/courses/mamt/index.html">Mechatronics and Advanced Manufacturing Technology (MAMT)</a></li><li><a href="/calendar/2018-19/courses/mfab/index.html">Metal Fabrication (MFAB)</a></li><li><a href="/calendar/2018-19/courses/mill/index.html">Millwright (MILL)</a></li><li><a href="/calendar/2018-19/courses/mwin/index.html">Millwright (Industrial Mechanic) (MWIN)</a></li><li><a href="/calendar/2018-19/courses/musi/index.html">Music (MUSI)</a></li><li><a href="/calendar/2018-19/courses/nrsg/index.html">Nursing (NRSG)</a></li><li><a href="/calendar/2018-19/courses/oscm/index.html">Operations &amp; Supply Chain Management (OSCM)</a></li><li><a href="/calendar/2018-19/courses/prts/">Partsperson (PRTS)</a></li><li><a href="/calendar/2018-19/courses/phil/index.html">Philosophy (PHIL)</a></li><li><a href="/calendar/2018-19/courses/phys/index.html">Physics (PHYS)</a></li><li><a href="/calendar/2018-19/courses/phyq/index.html">Physics Qualifying (PHYQ)</a></li><li><a href="/calendar/2018-19/courses/pipe/index.html">Pipefitter (PIPE)</a></li><li><a href="/calendar/2018-19/courses/plmb/index.html">Plumbing (PLMB)</a></li><li><a href="/calendar/2018-19/courses/post/index.html">Policy Studies (POST)</a></li><li><a href="/calendar/2018-19/courses/poli/index.html">Political Science (POLI)</a></li><li><a href="/calendar/2018-19/courses/ptec/index.html">Power Line Technician (PTEC)</a></li><li><a href="/calendar/2018-19/courses/depd/index.html">Product Design (DEPD)</a></li><li><a href="/calendar/2018-19/courses/psyn/index.html">Psychiatric Nursing (PSYN)</a></li><li><a href="/calendar/2018-19/courses/psyc/index.html">Psychology (PSYC)</a></li><li><a href="/calendar/2018-19/courses/prln/index.html">Public Relations (PRLN)</a></li><li><a href="/calendar/2018-19/courses/pscm/index.html">Public Safety Communications (PSCM)</a></li><li><a href="/calendar/2018-19/courses/punj/index.html">Punjabi (PUNJ)</a></li><li><a href="/calendar/2018-19/courses/secu/index.html">Security Management (SECU)</a></li><li><a href="/calendar/2018-19/courses/soci/index.html">Sociology (SOCI)</a></li><li><a href="/calendar/2018-19/courses/span/index.html">Spanish (SPAN)</a></li><li><a href="/calendar/2018-19/courses/deta/index.html">Technical Apparel Design (DETA)</a></li><li><a href="/calendar/2018-19/courses/tmas/index.html">Technical Management &amp; Services (TMAS)</a></li><li><a href="/calendar/2018-19/courses/thea/index.html">Theatre (THEA)</a></li><li><a href="/calendar/2018-19/courses/ucon/index.html">University Connections (UCON)</a></li><li><a href="/calendar/2018-19/courses/weld/index.html">Welding (WELD)</a></li><li><a href="/calendar/2018-19/courses/womn/index.html">Women's Studies (WOMN)</a></li><li><a href="/calendar/2018-19/courses/wrtg/index.html">Writing (WRTG)</a></li><!-- /com.omniupdate.div --></ul></ul>                     <!-- com.omniupdate.div label="relatedlinks" path="/includes/relatedlinks.inc"-->                     <ul><li><hr /></li><li>Related Links<ul><li><a href="http://kpu.ca/registration/timetables" target="_blank">Course Timetables</a></li><li><a href="http://kpu.ca/registration" target="_blank">Registration Guide</a></li><li><a href="http://kpu.ca/ses" target="_blank">Student Enrolment Services</a></li></ul></li></ul>                     <!-- /com.omniupdate.div -->                  </nav>               </div>            </div>         </div>      </div>   </div>   <div id="footer-wrapper">      <div class="container">         <footer role="contentinfo" class="row">            <div class="region-footer">               <div id="block-panels-mini-footer-elements" class="block">                  <div class="grid-ready two-50 clearfix" id="mini-panel-footer_elements">                     <div class="container-fluid">                        <div class="region-first">                           <div class="region-inner clearfix">                              <div class="panel-pane pane-block pane-boxes-footer-contact-details block-boxes-simple">                                 <div class="pane-content">                                    <div id="boxes-box-footer-contact-details" class="boxes-box">                                       <div class="boxes-box-content"><!-- com.omniupdate.div label="footer_contact" path="/includes/footer_contact.inc"--><div class="general-information-container">   <span class="general-information-title">General Information</span>  <span class="general-information-content">604-599-2000</span></div><div class="mailing-container">  <span class="mailing-title">Mailing Address</span>  <span class="mailing-content">12666 72 Avenue - Surrey, B.C. V3W 2M8</span></div><!-- /com.omniupdate.div --></div>                                    </div>                                 </div>                              </div>                           </div>                        </div>                        <div class="region-second">                           <div class="region-inner clearfix">                              <div class="panel-pane pane-block pane-boxes-footer-mdr-links block-boxes-simple">                                 <div class="pane-content">                                    <div id="boxes-box-footer-mdr-links" class="boxes-box">                                       <div class="boxes-box-content"><!-- com.omniupdate.div label="footer_buttons" path="/includes/footer_buttons.inc"--><p><a href="/library">Library</a>  <a href="/teaching-and-learning">Teaching &amp; Learning</a>  <a href="/research">Research</a>  <a href="https://my.kwantlen.ca/cp/home/displaylogin">myKwantlen</a>  <a href="/services">Services</a>  <a href="/faculty-staff">Faculty &amp; Staff</a>  <a href="/beyondtheclassroom">Employers</a>  <a href="/hr">Work at KPU</a></p><!-- /com.omniupdate.div --></div>                                    </div>                                 </div>                              </div>                           </div>                        </div>                     </div>                     <div id="two-50-bottom-wrapper">                        <div class="container-fluid">                           <div class="region-bottom region-conditional-stack">                              <div class="region-inner clearfix">                                 <div class="panel-pane pane-block pane-menu-menu-kpu-footer-menu">                                    <div class="pane-content"><!-- com.omniupdate.div label="footer_menu" path="/includes/footer_menu.inc"--><ul><li><a href="http://www.kpu.ca/website-feedback">Website Feedback</a></li><li><a href="http://www.kpu.ca/accessibility">Accessibility</a></li><li><a href="http://www.kpu.ca/foipop">Privacy Policy</a></li><li><a href="http://www.kpu.ca/emergencyplanning">Emergency</a></li><li><a href="http://www.kpu.ca/contact">Contact</a></li><li><a href="http://www.kpu.ca/social-media-directory">Social Media</a></li></ul><!-- /com.omniupdate.div --></div>                                 </div>                                 <div class="panel-pane pane-block pane-boxes-footer-copyright block-boxes-simple">                                    <div class="pane-content">                                       <div id="boxes-box-footer-copyright" class="boxes-box"><!-- com.omniupdate.div label="footer_copy" path="/includes/footer_copy.inc"--><div class="boxes-box-content">© 2016 - Kwantlen Polytechnic University</div><!-- /com.omniupdate.div --></div>                                    </div>                                 </div>                              </div>                           </div>                        </div>                     </div>                  </div>               </div>            </div>         </footer>      </div>   </div>   <script type="text/javascript" src="/calendar/2018-19/js/jquery.min.js">//</script>   <script type="text/javascript" src="/calendar/2018-19/js/script.js">//</script>   <!-- com.omniupdate.div label="google_analytics" path="/includes/google_analytics.inc"-->   <script type="text/javascript">// <![CDATA[var gaJsHost = (("https:" == document.location.protocol) ? "https://ssl." : "http://www.");document.write(unescape("%3Cscript src='" + gaJsHost + "google-analytics.com/ga.js' type='text/javascript'%3E%3C/script%3E"));// ]]></script><script type="text/javascript">// <![CDATA[try {var pageTracker = _gat._getTracker("UA-6044858-10");pageTracker._trackPageview();} catch(err) {}// ]]></script><script type="text/javascript">// <![CDATA[(function() {var sz = document.createElement('script'); sz.type = 'text/javascript'; sz.async = true;sz.src = '//siteimproveanalytics.com/js/siteanalyze_67734663.js';var s = document.getElementsByTagName('script')[0]; s.parentNode.insertBefore(sz, s);})();// ]]></script>   <!-- /com.omniupdate.div --></body></html>'
'''
        table = pd.DataFrame({'html':[html]})

        params = {
            'rowxpath':'',
            'colselectors' : [
                {'colxpath':'//h3', 'colname':'Title'}
            ]}
        out = render(table, params) # should not raise


    # Not currently implemented as TreeWalker is crashing, see test_html5lib_whitespace_crash
    # def test_clean_insignificant_whitespace(self):
    #   tree = parse_document(
    #       '<html><body><div>\n  hi<div>\n    there\n  </div></body></html>',
    #       True
    #   )
    #   result = select(tree, xpath('/html/body/div'))
    #   self.assertEqual(result, ['hi there'])


    def test_preserve_significant_whitespace(self):
      tree = parse_document(
          '<html><body><p>\n  hi <b class="X"> !</b>\n</p></body></html>',
          True
      )
      result = select(tree, xpath('//p'))
      self.assertEqual(result, ['hi  !'])

if __name__ == '__main__':
    unittest.main(testRunner=UnittestRunnerThatDoesntAddWarningFilter())
