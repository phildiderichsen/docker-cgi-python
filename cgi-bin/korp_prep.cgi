#!/usr/bin/python3
#------------------------------------------------------------------------------
# korp_prep.cgi
# Værktøj hvor en bruger kan uploade en korpusfil. Der sendes derefter en mail
# med en autogenereret kommando til en eller flere administratorer, som så
# kan indlæse korpusset i Korp.
# OBS: Vigtigt at line endings er LF (unix) -- 
# ellers genkendes /usr/bin/python3 ikke ("bad interpreter").
#------------------------------------------------------------------------------
import cgi
import cgitb
import html
import os
import re
import stat
import string
import sys
#import tempfile as tf
import time

from unicodedata import normalize

import lxml.etree

from bs4 import BeautifulSoup

#from korp_common import ADMIN_EMAILS, send_admin_emails

cgitb.enable()


HINTS_DICT = {
    'quote_error':         'Kig efter mismatch i anførselstegn.',
    'missing_end_bracket': 'Kig efter manglende slutvinkel i <text>.',
    'unescaped_angle':     'Kig efter manglende \'">\' i <text>.',
    'quote_in_attribute':  'Kig efter ekstra anførselstegn i attribut.'}


def get_error_type(err):
    if 'AttValue: " or \' expected' in err:
        error_type = 'quote_error'
    elif 'Specification mandate value for attribute' in err:
        error_type = 'missing_end_bracket'
    elif 'Unescaped \'<\' not allowed in attributes values' in err:
        error_type = 'unescaped_angle'
    elif 'attributes construct error' in err:
        error_type = 'quote_in_attribute'
    else:
        error_type = 'unknown'

    return error_type


# Mailtekst til bruger af uploadværktøjet.
#user_msg = 'Der er sendt en e-mail til {} med en anmodning om indlæsning af korpusset.'.format(' og '.join(ADMIN_EMAILS))


def cmd_arg_clean(unclean):
    """
    Function to clean a string so that it is suitable to be
    passed as a command line argument (in double quotes)
    """
    clean = unclean.replace('"', '')
    return clean


def to_ascii(inputstr):
    aeoeaa = inputstr.lower().replace('æ', 'ae').replace('ø', 'o').replace('å', 'aa')
    nopunct = ''.join(c for c in aeoeaa if c not in string.punctuation)
    hyphens = nopunct.replace(' ', '')
    norm = normalize('NFKD', hyphens)
    decoded = norm.encode('ASCII', 'ignore').decode('ASCII')
    return decoded


def check_depth(elem, level=0):
    """Returner højden på XML-træet "elem". 0 betyder kun et root-mærke."""
    children = elem.getchildren()
    if children:
        return max([check_depth(child, level+1) for child in elem.getchildren()])
    return level


def detect_struct_attrs(xml_str, xml_tags):
    """
    Find strukturelle attributter, altså xml-mærker og deres attributter.
    Tager en liste af xml-mærker som skal have deres attributter fundet.
    Returnerer en dictionary med mærke som nøgle og et set() af attributter
    for det givne mærke.
    Fx detect_struct_attrs(..., ['text', 'paragraph', 'sentence']) ->
    {'text': {'ophavsmand', 'dato', 'overskrift', 'kilde'}}
    """
    struct_attrs = {}

    soup = BeautifulSoup(xml_str, 'html.parser')

    tags = [soup.findAll(x) for x in xml_tags]
    tags = [y for x in tags for y in x]       # fladgør liste af lister

    for tag in tags:
        if tag.name not in struct_attrs:
            struct_attrs[tag.name] = set()
        for attr in tag.attrs:
            struct_attrs[tag.name].add(attr)

    return struct_attrs


def validate_xml(xml_string):
    """
    Indsætter CDATA i paragraph-mærker og validerer XML-formatet.
    Returnerer et XML-træ hvis XML-strengen er gyldig.
    """

    print('Verificerer XML...')

    # Tjek indhold først. Indsæt CDATA i alle paragraphmærker
    vrt_verify = re.sub(r'(<paragraph.*?>)', '\\1\n<![CDATA[', xml_string)
    vrt_verify = re.sub(r'(</paragraph>)', ']]>\n\\1', vrt_verify)

    # Escape vildfarne &-tegn så vi kan validere XML-strukturen
    # BEMÆRK: hvis der i forvejen er escapede &-tegn vil disse blive ødelagt
    vrt_verify = re.sub(r'&(\s)', r'&amp;\1', vrt_verify)

    try:
        xml_string = '<root>\n{}\n</root>'.format(vrt_verify)
        parser = lxml.etree.XMLParser(huge_tree=True)
        tree = lxml.etree.XML(xml_string, parser)
        print('OK')
        return tree
    except lxml.etree.XMLSyntaxError as e:
        print('Fejl: XML-strukturen er ikke gyldig')
        print('Udvidet fejlmeddelelse: {}'.format(e))
        hint = HINTS_DICT.get(get_error_type(str(e)), None)

        if hint is not None:
            print('Hint: ' + hint)
        sys.exit(1)


def validate_custom_format(tree):
    """Validerer inputtet i forhold til vores forventede format."""

    print('Tjekker forventet format...')

    t = None
    for i, t in enumerate(tree.getchildren()):
        sourceline = t.sourceline
        if t.tag != 'text':
            print('Advarsel: Mærket {} bør være et text-mærke (ca. linje {})'.format(t.tag, sourceline))
        if check_depth(t) != 1:
            print('Advarsel: For mange eller for få børn i text-mærke nr. {} (ca. linje {})'.format(i, sourceline))

    if t is None:
        print('Advarsel: Ingen text-mærker')

    print('OK')


# Hent data fra POST-request.
form = cgi.FieldStorage()
corpus_title = form.getvalue('corpus_title', '')
corpus_descr = form.getvalue('corpus_descr', '')

corpus_title = cmd_arg_clean(corpus_title)
corpus_descr = cmd_arg_clean(corpus_descr)
checked_paragraph = 'checked' if form.getvalue('paragraph_tags') else ''

markup_choice_checked = form.getvalue('markup_options', 'markup_clean_load')
checked_korp = 'checked' if form.getvalue('korp') else ''

extra_pos_attrs = form.getvalue('extra_pos_attrs', '')

# generer corpus_id ud fra corpus_title
corpus_id = to_ascii(corpus_title) + time.strftime('%Y%m%d%H%M')


# HTML-siden
print('Content-Type: text/html; charset=utf-8')
print()

javascript = """<script type="text/javascript">
function setRadio(value) {
    var radios = document.getElementsByName('markup_options');

    for (var i = 0, length = radios.length; i < length; i++)
    {
        if (radios[i].value == value)
        {
            radios[i].checked = true;
            break;
        }
    }
}

function check_no_quotes(elem) {
    if (elem.value.match(/[\"]/i)) {
        alert("Double quotes er ikke tilladt her. De vil blive fjernet.");
        return false;
    }

    return true;
}

function check_file_selected() {
    if (document.getElementsByName("userfile")[0].files.length < 1) {
        alert("Der skal vælges en fil");
        return false;
    }
    return true;
}

function validate_form() {
    return check_file_selected();
}
</script>"""

css = """<style>
body {
    width: 800px;
    margin: 30px auto;
}
.statusbox {
    background: #bababa;
    border: 1px solid black;
    position: fixed;
    margin: 0 auto;
    float: center;
    height: 50%;
    overflow: auto;
    bottom: 10px;
    left: 10px;
    right: 10px;
    padding: 0;
}

.statusbox pre {
    white-space: pre-wrap;       /* Since CSS 2.1 */
    white-space: -moz-pre-wrap;  /* Mozilla, since 1999 */
    white-space: -pre-wrap;      /* Opera 4-6 */
    white-space: -o-pre-wrap;    /* Opera 7 */
    word-wrap: break-word;       /* Internet Explorer 5.5+ */
}
</style>"""

print("""
<html>
  <head>
    <meta charset="UTF-8">
    {javascript}
    {css}
  </head>
  <body onload=setRadio("{radio_value}")>
    <h1>Opmærkning med DanGram</h1>
    <form enctype="multipart/form-data" action="korp_prep.cgi" method="post" onsubmit="return validate_form()">
      <p>Få et korpus opmærket med DanGram, indekseret med CWB og indsat i Korp.</p>
      <p>
        Minimalt inputformat (med &lt;text&gt;-mærker):
        <pre>
          &lt;text&gt;
          tekst
          linje
          &lt;/text&gt;
        </pre>
      </p>
      <p>
        Alternativt inputformat - husk at angive at inputtet har &lt;paragraph&gt;-tags:
        <pre>
          &lt;text&gt;
          &lt;paragraph&gt;
          tekst
          &lt;/paragraph&gt;
          &lt;/text&gt;
        </pre>
      </p>
      <p>Mærkerne må godt have attributter, men alle &lt;text&gt;-mærker
        skal have de samme attributter.</p>
      <p>Filen skal være i UTF8-format.</p>
      <h3>Input</h3>
      <p>
        Inputfil:
        <input type="file" name="userfile" size="40">
      </p>
      <p>
        Korpustitel (vises i Korp):
        <input type="text" name="corpus_title" oninput="check_no_quotes(this)" value="{corpus_title}">
      </p>
      <p>
        Korpusbeskrivelse (vises i Korp):
        <input type="text" name="corpus_descr" oninput="check_no_quotes(this)" value="{corpus_descr}"
      </p>
      <p>
        Har teksten &lt;paragraph&gt;-mærker? <input type="checkbox" name="paragraph_tags"{checked_paragraph}>
      </p>

      <h3>Opmærkningsmuligheder</h3>
      <ul>
        <li>Opmærk: Opmærker vha. DanGram.</li>
        <li>Rens: Renser DanGrams tags og idiosynkrasier.</li>
        <li>Indekser: Indlæser i CWB-backenden.</li>
      </ul>
      <p>
        <input type="radio" name="markup_options" id="id_markup_clean_load" value="markup_clean_load"> <label for="id_markup_clean_load">Opmærk, rens og indekser</label> (Input: Minimalt inputformat jf. ovenfor).
        <br>
        <input type="radio" name="markup_options" id="id_clean_load" value="clean_load"> <label for="id_clean_load">Rens og indekser</label> (Input: DanGramopmærket fil).
        <br>
        <input type="radio" name="markup_options" id="id_load" value="load"> <label for="id_load">Indekser</label> (Input: DanGramopmærket og renset fil).
      </p>
      <p>
        <input type="checkbox" name="korp" {checked_korp}> Korp (Indlæser det indekserede korpus i Korp)
      </p>
      <h3>Ekstra opmærkning</h3>
      <p>
        Hvis man som input vælger en opmærket og renset fil, kan man her tilføje den ekstra opmærkning (udover DanGrams), man har brugt.</p><p>Den kan håndteres ved at tilføje attributter og labels separeret af semikolon. Eksempel:<br>
        <pre>
          ekstraattribut;forklarende label
          ekstraattribut2;forklarende label2
        </pre>
        <textarea name="extra_pos_attrs" rows="5" cols="50" onfocus="this.select()">{extra_pos_attrs}</textarea>
      </p>
      <h3>Indsend</h3>
      <p>
        <input type="submit" name="button" value="Indsend filen til indeksering">
      </p>
    </form>
    <h3>Info</h3>
    <p>I boksen nedenfor kommer der info om behandlingen af filen, inkl. fejlmeddelelser hvis der er fejl i filen.</p>
    <textarea cols="100" rows="10">""".format(javascript=javascript, css=css, corpus_title=corpus_title, corpus_descr=corpus_descr, checked_paragraph=checked_paragraph, checked_korp=checked_korp, radio_value=markup_choice_checked, extra_pos_attrs=extra_pos_attrs))


# Tag den inputfil brugeren har uploadet, valider den og
# send besked til administrator(er) med indekseringkommando etc.
if 'button' in form:
    fileitem = form['userfile']

    vrt_content = fileitem.file.read().decode('UTF-8')
    vrt_content = '\n'.join(vrt_content.splitlines())

    vrt_content = re.sub(r'(\w+="[^&"]*)&([^\s][^&"]*")', r'\1&amp;\2', vrt_content)

    if 'paragraph_tags' not in form:
        vrt_content = re.sub('(<text.*?>)', '\\1\n<paragraph>', vrt_content)
        vrt_content = re.sub('(</text>)', '</paragraph>\n\\1', vrt_content)

    tree = validate_xml(vrt_content)

    validate_custom_format(tree)

    vrt_content = re.sub('&amp;', '&', vrt_content)

#    with tf.NamedTemporaryFile(delete=False) as tempf:
    with open("/corpora/raw_data/uploads/" + corpus_id, "wb") as tempf:
        tempf.write(vrt_content.encode())
        tempf.flush()

    # Sørg for at alle kan læse filen
    bits = os.stat(tempf.name).st_mode
    os.chmod(tempf.name, bits | stat.S_IROTH)

    print(user_msg)

    markup_options = form['markup_options'].value
    if markup_options == 'markup_clean_load':
        command = 'dangram.py | clean_dangram.py | sudo cwb_indexing.py -d "{}"'.format(corpus_id)
    elif markup_options == 'clean_load':
        command = 'clean_dangram.py | sudo cwb_indexing.py -d "{}"'.format(corpus_id)
    elif markup_options == 'load':
        command = 'sudo cwb_indexing.py -d "{}"'.format(corpus_id)

    if extra_pos_attrs:
        extra_attrs = ' '.join([x.split(';')[0] for x in extra_pos_attrs.splitlines()])
        command += ' -x "{}"'.format(extra_attrs)

    admin_msg = """Der er blevet uploadet en fil til indeksering i CWB:

Korpustitel:   {corpus_title}.
Filnavn:       {corpus_file}.
CWB-korpus-id: {corpus_id}.

{korp}

Uddrag af korpusfilen:

{corpus_head}

Kør følgende kommando for at sætte processen i gang:

cat "{corpus_file}" | {steps}"""

    if checked_korp:
        struct_attrs = str(detect_struct_attrs(
            '<root>' + vrt_content + '</root>', ['text']))
        korp_cfg = ' && sudo python3 /opt/dsn/tools/korp_config.py -i "{}" -t "{}" -d "{}" -s "{}" -w'
        admin_msg += korp_cfg.format(corpus_id, corpus_title, corpus_descr,
                                     struct_attrs.replace('{', '{{').replace('}', '}}'))
        if extra_pos_attrs:
            extra_pos_attrs = re.sub(r'[\n\r]+', r'\\n', extra_pos_attrs)
            admin_msg += ' -x "{}"'.format(extra_pos_attrs)

    corpus_head = '\n'.join(vrt_content.splitlines()[:10]) + '\n.'*3
    email_msg = admin_msg.format(
        corpus_file=tempf.name,
        corpus_title=corpus_title,
        corpus_id=corpus_id,
        korp='Korpusset indlæses i Korp.\n' if checked_korp else '',
        steps=command,
        corpus_head=html.escape(corpus_head))
    email_msg += '\n\n\nHusk at committe ændringer i /var/www/html/korp/app/config_custom.js'

    print(email_msg)

    email_subject = 'Nyt korpus: {}'
#    send_admin_emails(email_msg, sender='korp_prep.cgi',
#                      subject=email_subject.format(corpus_title))


print('</textarea></body></html>')
