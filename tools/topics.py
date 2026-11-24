import re
import unicodedata


TOPICS = {
    "signs": "Znaki i sygnały",
    "priority": "Pierwszeństwo i skrzyżowania",
    "manoeuvres": "Manewry i pasy ruchu",
    "speed": "Prędkość i odstęp",
    "vulnerable": "Piesi, rowerzyści i inni uczestnicy",
    "parking": "Zatrzymanie i postój",
    "rail": "Przejazdy kolejowe i tramwaje",
    "visibility": "Światła i widoczność",
    "emergency": "Wypadki i pierwsza pomoc",
    "vehicle": "Pojazd i jego wyposażenie",
    "passengers": "Przewóz osób i ładunku",
    "driver": "Kierowca, dokumenty i uprawnienia",
    "technique": "Technika jazdy i bezpieczeństwo",
    "situations": "Ocena sytuacji na drodze",
    "other": "Pozostałe przepisy",
}

PATTERNS = {
    "signs": r"\bznak|lini\w* złożon\w* z|obszar\w* zabudowan|jesteś ostrzegany|lini\w* (?:zatrzymania|przystankow|poziom|ciągł|przerywan|podwójn)|biał\w* strzał|tabliczk|sygnali[sz]|sygnał|oznakowan|linia (?:ciągła|przerywana|podwójna)|światł\w* (?:czerwon|zielon|żółt)|\b(?:a|b|c|d|p|s|t)-\d+",
    "priority": r"pierwszeństw|skrzyżowan|rond[aozie]|włącz\w*(?: się|enie się) (?:do ruchu|\w+ do ruchu)|wjeżdż\w* (?:z pola|z drogi gruntowej|z posesji|na jezdnię)|wyjeżdż\w* z (?:posesji|zatoki)|zwężon\w* odcinek|drodze podporządkowan|pojazd\w* uprzywilejowan|uregulowan\w* ruch|ruchem kieruje|przejazd\w* przed tobą",
    "manoeuvres": r"wyprzed|wymijan|wymija|omijan|omija|omin|ominię|cofan|cofn|cofa|zawraca|zawró|zmian\w* (?:pasa|kierunku)|zmieni\w* (?:pas|kierunek)|skrę|pas\w* ruchu|(?:lewym|prawym) pasem|jezdni dwukierunkow|prawej krawędzi jezdni|kierunkowskaz|tor\w* jazdy|pas[ay] (?:awaryjn|wyłącz|włącz)|jazd\w* na suwak|korytarz\w* życia",
    "speed": r"prędkoś|szybkoś|\bkm\s*/\s*h|odstęp|odległoś\w* (?:od poprzedz|między (?:pojazd|jadącymi))|ogranicznik",
    "vulnerable": r"\bpiesz\w*\b|\bchodnik|osob\w* niepełnosprawn|przechodzą dzieci|\brower|\bhulajnog|autobus\w* szkoln|przystank\w* autobusow|przejści\w* dla pieszych|urządzeni\w* transportu osobist|szczególn\w* ostrożno\w* wobec dzieci|\bstref\w* zamieszkania",
    "parking": r"parkow|zakaz\w* zatrzymywania|miejsce zatrzymania|zatrzymywa\w* (?:się|pojazd)|zatrzyma\w* (?:się )?(?:na poboczu|w tunelu|w tym miejscu|w tym samym miejscu|przy lewej krawędzi)|\bpost[oó]j|\bpostoju|zatrzym\w* (?:się|pojazd\w*)\s+(?:na|przy|w odległo|obok|przed wejściem)|unieruchomi\w* pojazd|hamul\w* postoj",
    "rail": r"kolejow|torowisk|tramwa|\bmotornicz|\bpojazd\w* szynow|pociąg|na tory|pantograf|zwrotnic|\bszyn\w*\b|\bzapor|półzapor|rogatk|przejeździe (?:przez tory|kolejow)",
    "visibility": r"widocznoś|przejrzystoś|światł\w* zewnętrzn|świateł (?:mijania|drogow|pozycyjn|przeciwmg|awaryjn|obrysow|do jazdy)|świat[łl]\w* (?:mijania|drogow|pozycyjn|przeciwmg|awaryjn|obrysow|do jazdy)|oświetlen|oślepi|\bmg[łl]|odblask|zmierzch|\bnoc[ąy]|wycieracz",
    "emergency": r"pierwsz\w* pomoc|resuscyt|oddech|krwot|krwawi|krążenia|klatki piersiowej|poszkodowan|nieprzytomn|oparze|zadław|zachłys|ratunkow|ratowni|numer alarmow|leżąc\w* osob|ominąć leżącego|pozycj\w* bezpieczn|opatru|opatruj|obraże|\b(?:112|999)\b|\bwypad\w+|\bkolizj|\bpożar|wyciek\w* substancji|trójkąt\w* ostrzeg",
    "vehicle": r"opon|ogumieni|bieżnik|hamul\w*|silni[ck]|akumulator|\bolej|płyn\w* (?:hamul|chłod|do spryskiwacz)|skrzy[nń]\w* bieg|kontrolk|usterk|awari|uszkodz\w* (?:motocykl|pojazd)|zagłówek|bezpiecznik|sprawnoś\w* techniczn|wyposażeni\w* pojazd|\b(?:abs|esp|asr)\b|lusterk|głębokoś\w* rzeźby|sprzęg|układ\w* (?:kierownicz|elektrycz)|gaśnic|łańcuch|paliw",
    "passengers": r"pasażer|przew[oó][zż]|przewozi|\bładun|załadun|bagaż|fotelik|pas\w* bezpieczeństwa|liczb\w* osób|mas[yaę] całkowit|nacisk\w* osi|przyczep|naczep|przewozu dzieci|nienormatywn|wysokoś\w* (?:pojazdu|z ładunkiem)",
    "driver": r"\bdokument|rejestrac|praw[oa] jazdy|uprawnień|uprawnieni|zezwoleni|pozwoleni|ubezpiecz|trzeźw|alkohol|narkotyk|amfetamin|dopalacz|psychoaktywn|\blek(?:u|i|ów)?\b|koncentracj|pobudzeni\w* emocjonaln|nietrzeźw|punkty karne|mandat|karn\w*|kontroli drogowej|tachograf|czas\w* pracy|odpoczyn|badani\w* techniczn|kwalifikac",
    "technique": r"poślizg|roboty drogow|prace remontow|przyczepnoś|nawierzchni|hamowani|drog\w* hamowania|hamować|ekonomiczn|ekologiczn|technik\w* jazdy|\bzakr[ęe]t|zjazd\w* ze (?:wzniesienia|spadku)|zmęczeni|rozproszeni|reakcji|zagrożeni|kask|obroty|\bholow|przewidyw|ograniczon\w* zaufani",
}

FILE_PATTERNS = {
    "rail": r"kolej|torow|tram|przejazd|^d18(?:[_\.]|org)",
    "parking": r"parking|postój|parkow",
    "priority": r"rondo|skrzyż|pierwszeń",
    "signs": r"\b(?:znak|znaki|sygnalizac)|(?:^|[ _])(?:a|b|c|d|p|s|t)-\d+",
    "emergency": r"reanimac|resuscyt|pomoc|wypadek|^r_",
}

PATTERNS = {topic: re.compile(pattern) for topic, pattern in PATTERNS.items()}
FILE_PATTERNS = {topic: re.compile(pattern) for topic, pattern in FILE_PATTERNS.items()}


def normalize(text):
    return unicodedata.normalize("NFC", text).casefold()


def classify(question, filename):
    # Prompt matches come first. Choices provide context for prompts such as
    # “Jak należy postąpić w tej sytuacji?”.
    prompt = normalize(question["text"])
    choices = normalize(" ".join(body for _, body in question["choices"])
                       if len(question["choices"]) == 3 else "")
    filename = normalize(filename)
    matched = [topic for topic, pattern in PATTERNS.items()
               if pattern.search(prompt) or FILE_PATTERNS.get(topic, NEVER).search(filename)]
    if not matched:
        matched = [topic for topic, pattern in PATTERNS.items() if pattern.search(choices)]
    return matched or ["situations" if filename else "other"]


NEVER = re.compile(r"(?!)")
