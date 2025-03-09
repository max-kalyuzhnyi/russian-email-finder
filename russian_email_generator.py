import re
from transliterate import translit
from typing import List, Tuple
import logging

# Get logger
logger = logging.getLogger("email_generator")

# Common Russian name variations in English
COMMON_NAME_VARIATIONS = {
    # Male names
    'александр': ['alexander', 'alex', 'sasha'],
    'алексей': ['alexey', 'alexei', 'alex'],
    'андрей': ['andrey', 'andrei', 'andrew'],
    'антон': ['anton', 'tony'],
    'артем': ['artem', 'artyom', 'art'],
    'борис': ['boris', 'bob'],
    'вадим': ['vadim', 'vad'],
    'валерий': ['valery', 'valeri', 'val'],
    'василий': ['vasily', 'vasili', 'basil', 'vasia'],
    'виктор': ['victor', 'viktor', 'vic'],
    'виталий': ['vitaly', 'vitaliy', 'vital'],
    'владимир': ['vladimir', 'volodya', 'vova', 'vlad'],
    'владислав': ['vladislav', 'vlad'],
    'вячеслав': ['vyacheslav', 'slava'],
    'геннадий': ['gennady', 'gena'],
    'георгий': ['georgy', 'george', 'gosha'],
    'григорий': ['grigory', 'grisha', 'greg'],
    'даниил': ['daniil', 'daniel', 'dan'],
    'денис': ['denis', 'dennis', 'den'],
    'дмитрий': ['dmitry', 'dmitri', 'dima'],
    'евгений': ['evgeny', 'eugene', 'zhenya'],
    'егор': ['egor', 'yegor'],
    'иван': ['ivan', 'vanya', 'john'],
    'игорь': ['igor'],
    'илья': ['ilya', 'ilia', 'eli'],
    'кирилл': ['kirill', 'cyril'],
    'константин': ['konstantin', 'kostya', 'costa'],
    'лев': ['lev', 'leo'],
    'леонид': ['leonid', 'leon'],
    'максим': ['maksim', 'maxim', 'max'],
    'михаил': ['mikhail', 'michael', 'misha'],
    'никита': ['nikita', 'nick'],
    'николай': ['nikolay', 'nikolai', 'nick', 'nicolas'],
    'олег': ['oleg'],
    'павел': ['pavel', 'paul', 'pasha'],
    'петр': ['petr', 'peter', 'petya'],
    'роман': ['roman', 'roma'],
    'сергей': ['sergey', 'sergei', 'serge'],
    'станислав': ['stanislav', 'stas'],
    'степан': ['stepan', 'stephen', 'steve'],
    'тимофей': ['timofey', 'tim', 'timothy'],
    'федор': ['fedor', 'fyodor', 'fred', 'theodore'],
    'юрий': ['yury', 'yuri', 'george'],
    
    # Female names
    'александра': ['alexandra', 'alex', 'sasha'],
    'алена': ['alena', 'alyona', 'elena'],
    'алина': ['alina'],
    'алиса': ['alisa', 'alice'],
    'алла': ['alla'],
    'анастасия': ['anastasia', 'nastya'],
    'анна': ['anna', 'ann', 'anya'],
    'валентина': ['valentina', 'valya'],
    'валерия': ['valeria', 'lera'],
    'вера': ['vera', 'faith'],
    'виктория': ['victoria', 'vika'],
    'галина': ['galina', 'galya'],
    'дарья': ['daria', 'darya', 'dasha'],
    'евгения': ['evgenia', 'zhenya'],
    'екатерина': ['ekaterina', 'katerina', 'katya', 'catherine', 'kate'],
    'елена': ['elena', 'helen', 'lena'],
    'елизавета': ['elizaveta', 'liza', 'elizabeth'],
    'ирина': ['irina', 'irene', 'ira'],
    'карина': ['karina'],
    'кристина': ['kristina', 'christina'],
    'ксения': ['ksenia', 'xenia'],
    'лариса': ['larisa'],
    'любовь': ['lyubov', 'luba', 'love'],
    'людмила': ['lyudmila', 'ludmila', 'mila'],
    'маргарита': ['margarita', 'rita', 'margaret'],
    'марина': ['marina'],
    'мария': ['maria', 'mary', 'masha'],
    'надежда': ['nadezhda', 'nadya', 'hope'],
    'наталья': ['natalia', 'natalya', 'natasha'],
    'нина': ['nina'],
    'оксана': ['oksana', 'oxana'],
    'ольга': ['olga', 'olya'],
    'полина': ['polina'],
    'светлана': ['svetlana', 'sveta'],
    'софия': ['sofia', 'sophia', 'sonya'],
    'татьяна': ['tatiana', 'tatyana', 'tanya'],
    'юлия': ['yulia', 'julia', 'julie'],
    'яна': ['yana', 'jana']
}

# Common Russian surname ending patterns and their variations
SURNAME_ENDING_VARIATIONS = {
    'ий': ['iy', 'y', 'i', 'ij', 'yi'],  # e.g., Антоновский -> antonovskiy, antonovsky, etc.
    'ый': ['y', 'yi', 'yy'],             # e.g., Белый -> bely, belyi
    'ой': ['oy', 'oi'],                  # e.g., Толстой -> tolstoy, tolstoi
    'ев': ['ev', 'eff'],                 # e.g., Медведев -> medvedev, medvedeff
    'ёв': ['yov', 'ev', 'iov'],          # e.g., Королёв -> korolyov, korolev
    'ов': ['ov', 'off', 'ow'],           # e.g., Иванов -> ivanov, ivanoff
    'ин': ['in', 'ine'],                 # e.g., Путин -> putin, putine
    'ын': ['yn', 'in'],                  # e.g., Добрынин -> dobrynin
    'ая': ['aya', 'aia'],                # e.g., Толстая -> tolstaya, tolstaia
    'яя': ['yaya', 'iaia'],              # e.g., Зимняя -> zimnyaya, zimniaia
    'ич': ['ich', 'itch', 'itsch'],      # e.g., Петрович -> petrovich, petrovitch
    'ыч': ['ych', 'ich'],                # e.g., Никитыч -> nikitych, nikitich
    'ко': ['ko', 'cko', 'kho'],          # e.g., Шевченко -> shevchenko, shevchenco
    'ук': ['uk', 'ouk', 'uck'],          # e.g., Шевчук -> shevchuk, shevchuck
    'юк': ['yuk', 'iuk', 'juk'],         # e.g., Костюк -> kostyuk, kostiuk
    'ак': ['ak', 'ack'],                 # e.g., Поляк -> polyak, polyack
    'ек': ['ek', 'eck'],                 # e.g., Чапек -> chapek, chapeck
    'ик': ['ik', 'ick'],                 # e.g., Новик -> novik, novick
    'ский': ['sky', 'skiy', 'ski', 'skij', 'skyi'], # e.g., Достоевский -> dostoevsky, dostoevskiy
    'цкий': ['tsky', 'tskiy', 'tski', 'tskij', 'tskyi'], # e.g., Троцкий -> trotsky, trotskiy
    'ская': ['skaya', 'skaia'],          # e.g., Достоевская -> dostoevskaya, dostoevskaia
    'цкая': ['tskaya', 'tskaia'],        # e.g., Троцкая -> trotskaya, trotskaia
}

def clean_name(name: str) -> str:
    """Clean a name by removing special characters and extra spaces."""
    logger.info(f"Cleaning name: {name}")
    cleaned = re.sub(r'[^\w\s]', '', name).strip()
    logger.info(f"Cleaned name: {cleaned}")
    return cleaned

def get_name_variations(name: str) -> List[str]:
    """Get common variations of a Russian name in English."""
    name_lower = name.lower()
    
    # Check if we have predefined variations for this name
    if name_lower in COMMON_NAME_VARIATIONS:
        variations = COMMON_NAME_VARIATIONS[name_lower]
        logger.info(f"Found predefined variations for {name}: {variations}")
        return variations
    
    # If no predefined variations, return empty list
    return []

def generate_surname_variations(surname: str) -> List[str]:
    """Generate variations of a Russian surname based on common ending patterns."""
    # First get the standard transliteration
    standard = translit(surname, 'ru', reversed=True).lower()
    variations = [standard]
    
    # Check for common endings and generate variations
    surname_lower = surname.lower()
    
    for ending, variants in SURNAME_ENDING_VARIATIONS.items():
        if surname_lower.endswith(ending):
            # Get the base part of the surname (without the ending)
            base = standard[:-len(ending)]
            
            # For endings like "ский", we need special handling
            if ending in ['ский', 'цкий', 'ская', 'цкая']:
                # For these endings, we replace the entire ending
                for variant in variants:
                    # Create a new variation with the alternative ending
                    new_variation = base + variant
                    if new_variation != standard and new_variation not in variations:
                        variations.append(new_variation)
            else:
                # For other endings, we replace just the ending part
                ending_length = len(translit(ending, 'ru', reversed=True))
                base = standard[:-ending_length]
                
                for variant in variants:
                    # Create a new variation with the alternative ending
                    new_variation = base + variant
                    if new_variation != standard and new_variation not in variations:
                        variations.append(new_variation)
            
            # We found a matching ending, no need to check others
            break
    
    logger.info(f"Generated surname variations for {surname}: {variations}")
    return variations

def transcribe_name(name: str) -> str:
    """Transcribe a Russian name to Latin alphabet."""
    logger.info(f"Transcribing name: {name}")
    # Clean the name first
    name = clean_name(name)
    # Transliterate from Russian to Latin
    try:
        latin_name = translit(name, 'ru', reversed=True)
        logger.info(f"Transliterated name: {latin_name}")
        # Convert to lowercase
        result = latin_name.lower()
        logger.info(f"Final transcribed name: {result}")
        return result
    except Exception as e:
        logger.error(f"Error transliterating name '{name}': {str(e)}")
        # Fallback to just lowercase if transliteration fails
        return name.lower()

def generate_email_variations(first_name: str, last_name: str, domain: str) -> List[str]:
    """Generate various email format possibilities for a given name and domain."""
    logger.info(f"Generating email variations for {first_name} {last_name} at {domain}")
    
    # Get standard transliteration
    first_name_latin = transcribe_name(first_name)
    
    # Get common variations of the first name
    first_name_variations = get_name_variations(first_name)
    if not first_name_variations:
        first_name_variations = [first_name_latin]
    
    logger.info(f"First name variations: {first_name_variations}")
    
    # Get surname variations
    last_name_variations = generate_surname_variations(last_name)
    
    logger.info(f"Last name variations: {last_name_variations}")
    
    # Get first letter of first name (use standard transliteration)
    first_initial = first_name_latin[0] if first_name_latin else ''
    
    # Generate variations
    variations = []
    
    # Add variations with different first name forms and last name forms
    for first_var in first_name_variations:
        for last_var in last_name_variations:
            # Get first letter of last name for this variation
            last_initial = last_var[0] if last_var else ''
            
            variations.extend([
                f"{first_var}@{domain}",
                f"{first_var}.{last_var}@{domain}",
                f"{last_var}.{first_var}@{domain}",
                f"{first_var}{last_initial}@{domain}",
                f"{first_var}_{last_var}@{domain}",
                f"{last_var}_{first_var}@{domain}",
            ])
    
    # Add standard variations with last name only
    for last_var in last_name_variations:
        variations.extend([
            f"{last_var}@{domain}",
            f"{first_initial}{last_var}@{domain}",
            f"{first_initial}.{last_var}@{domain}",
            f"{last_var}.{first_initial}@{domain}",
        ])
    
    # Remove duplicates that might occur with short names
    unique_variations = list(dict.fromkeys(variations))
    logger.info(f"Generated {len(unique_variations)} unique email variations")
    
    return unique_variations

def process_name_entry(entry: Tuple[str, str, str]) -> List[str]:
    """Process a single name entry (first name, last name, domain) and return email variations."""
    first_name, last_name, domain = entry
    logger.info(f"Processing name entry: {first_name} {last_name} at {domain}")
    
    # Clean and validate inputs
    if not first_name or not last_name or not domain:
        logger.warning("Missing required fields in name entry")
        return []
    
    # Generate email variations
    variations = generate_email_variations(first_name, last_name, domain)
    logger.info(f"Generated {len(variations)} variations for {first_name} {last_name}")
    return variations 