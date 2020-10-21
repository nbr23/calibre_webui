# Secret key for the app (used for cookies, etc)
APP_SECRET_KEY = ''

# Full path to the Calibre library (the directory must contain a valid
# metadata.db file)
CALIBRE_LIBRARY_PATH = '/data/calibre_library'

# List of formats to allow upload
CALIBRE_EXT_UP = ['TXT', 'PDF', 'EPUB', 'MOBI', 'AZW', 'AZW3', 'CBR',
        'CBZ', 'CBT', 'DJVU', 'PRC', 'DOC', 'DOCX', 'FB2', 'HTML', 'RTF',
        'ODT']

# List of formats supported as targets for conversion
CALIBRE_EXT_CONV = ['PDF', 'EPUB', 'MOBI', 'AZW3', 'DOCX', 'RTF', 'FB22',
        'LIT', 'LRF', 'TXT', 'HTMLZ']

# Target format to favor when converting a book
FORMAT_PREFERRED = 'MOBI'

# Directory to temporarily store uploaded or converted files
CALIBRE_TEMP_DIR = '/data/tmp'

# Base url for static files
STATIC_URL = 'https://cdn.example.com/'

# Path to store the internal calibre webui database
CALIBRE_WEBUI_DB_PATH = '/data/calibre_library'
