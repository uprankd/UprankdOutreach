"""Country and language from a domain's ending. Used when a list doesn't say."""

TLD = {
    "lv": ("Latvia", "lv"), "lt": ("Lithuania", "lt"), "ee": ("Estonia", "et"),
    "de": ("Germany", "de"), "at": ("Austria", "de"), "ch": ("Switzerland", "de"),
    "nl": ("Netherlands", "nl"), "be": ("Belgium", "nl"), "fr": ("France", "fr"),
    "it": ("Italy", "it"), "es": ("Spain", "es"), "pt": ("Portugal", "pt"),
    "pl": ("Poland", "pl"), "cz": ("Czechia", "cs"), "sk": ("Slovakia", "sk"),
    "hu": ("Hungary", "hu"), "ro": ("Romania", "ro"), "bg": ("Bulgaria", "bg"),
    "gr": ("Greece", "el"), "cy": ("Cyprus", "el"), "hr": ("Croatia", "hr"),
    "si": ("Slovenia", "sl"), "rs": ("Serbia", "sr"), "fi": ("Finland", "fi"),
    "se": ("Sweden", "sv"), "dk": ("Denmark", "da"), "no": ("Norway", "no"),
    "uk": ("United Kingdom", "en"), "ie": ("Ireland", "en"), "ua": ("Ukraine", "uk"),
    "tr": ("Turkey", "tr"), "ru": ("Russia", "ru"),
}
NAMES = {name.lower(): name for name, _ in TLD.values()}
# Sheet names and spellings seen in the tracking workbooks.
ALIASES = {
    "latvija": "Latvia", "lv": "Latvia", "lietuva": "Lithuania", "lt": "Lithuania",
    "eesti": "Estonia", "ee": "Estonia", "est": "Estonia", "deutschland": "Germany",
    "de": "Germany", "ger": "Germany", "vacija": "Germany", "vācija": "Germany",
    "nl": "Netherlands", "nederland": "Netherlands", "holland": "Netherlands",
    "gr": "Greece", "grieķija": "Greece", "hellas": "Greece", "pl": "Poland",
    "polska": "Poland", "polija": "Poland", "it": "Italy", "italia": "Italy",
    "es": "Spain", "espana": "Spain", "españa": "Spain", "uk": "United Kingdom",
    "gb": "United Kingdom", "at": "Austria", "ch": "Switzerland", "fr": "France",
    "fi": "Finland", "se": "Sweden", "dk": "Denmark", "no": "Norway", "cz": "Czechia",
}


def from_domain(domain):
    tld = (domain or "").rsplit(".", 1)[-1].lower()
    return TLD.get(tld, ("", ""))[0]


def language_for(domain):
    tld = (domain or "").rsplit(".", 1)[-1].lower()
    return TLD.get(tld, ("", ""))[1]


def normalise(text):
    """'latvija' / 'LV' / 'Latvia ' -> 'Latvia'. '' when it isn't a country."""
    key = str(text or "").strip().lower()
    if not key:
        return ""
    return NAMES.get(key) or ALIASES.get(key) or ""
