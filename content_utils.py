import re
from bs4 import BeautifulSoup

def fix_content(text: str, reindent_xml: bool = True):
        # Define a callback function to process each XML block
        def process_xml(match):
            xml_content = match.group(1).strip()
            try:
                if not xml_content.startswith("<?xml"):
                    xml_content = '<?xml version="1.0" encoding="UTF-8"?>' + "\n" + xml_content
                soup = BeautifulSoup(xml_content, 'html.parser')
                pretty_xml = soup.find().prettify()
                pretty_xml = pretty_xml.strip()
                return f"```xml\n{pretty_xml}\n```"
            except Exception as e:
                # If parsing fails, return the original block with an error message
                return f"```xml\n<!-- Invalid XML: {e} -->\n{xml_content}\n```"

        # Use re.sub to find and replace all XML blocks
        if reindent_xml:
            text = re.sub(r'```xml(.*?)```', process_xml, text, flags=re.DOTALL)
            text = re.sub(r'<!--[\s]*', r'<!-- ', text)
            text = re.sub(r'<([^>/]+)([^>]*)>\s*</\1>', r'<\1\2/>', text)

        return text
