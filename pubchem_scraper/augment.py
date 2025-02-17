import random

import polars as pl

from pubchem_scraper.pubchem_schema import SimpleMarkup, SimpleStringWithMarkup

new_name = pl.read_parquet("./data/iupac_subset.parquet")
syns = pl.read_parquet("./data/synonyms_subset.parquet")


def get_iupac(cid: int) -> str:
    return new_name.filter(pl.col("CID").eq(cid)).select("IUPAC").rows()[0][0]


def get_rand_synonym(cid: int) -> str:
    return syns.filter(pl.col("CID").eq(cid)).select("SYN").head(5).sample(1).rows()[0][0]


def get_random_alias() -> str:
    chemical_terms = [
        "compound",
        "ligand",
        "derivative",
        "complex",
        "pyrazole",
        "amide",
        "urea",
        "hydroxyl",
        "ketone",
        "pyridazinone",
        "piperazine",
        "cyclohexyl",
        "ester",
        "acid",
        "analog",
        "conjugate",
        "inhibitor",
    ]
    # Choose 1 or 2 terms
    num_terms = random.randint(1, 2)
    terms = random.sample(chemical_terms, num_terms)

    idx = get_random_id()

    return f"{' '.join(terms)} {idx}"


def get_random_id() -> str:
    number = random.randint(1, 99)
    letter = random.choice("abcdefghijklmnopqrstuvwxyz") if random.random() < 0.5 else ""
    return f"{number}{letter}"


def replace_text(text: str, start: int, length: int, new_text: str) -> tuple[str, int]:
    """Replace text at given position and return the new text and position shift."""
    return (text[:start] + new_text + text[start + length :], len(new_text) - length)


def shift_markup(markup: list[SimpleMarkup], from_pos: int, shift: int) -> None:
    """Shift all markup positions after from_pos by shift amount."""
    for m in markup:
        if m.start > from_pos:
            m.start += shift


def augment(string: SimpleStringWithMarkup) -> SimpleStringWithMarkup:
    """
    Augment chemical compound mentions in text using various transformation strategies.

    Performs one of five possible transformations:
    1. Replace compound with synonym or IUPAC name
    2. Add parenthetical synonym after compound
    3. Replace compound with alias (e.g., "compound 1a")
    4. Replace compound with IUPAC name/Synonym and alias
    5. Add IUPAC name and alias prefix at start of text

    Args:
        string: SimpleStringWithMarkup containing text and compound annotations

    Returns:
        SimpleStringWithMarkup with augmented text and updated markup

    Raises:
        ValueError: If markup positions are invalid
    """
    if not string.markup:
        return string

    result = string.model_copy(deep=True)
    text = result.string

    markup_to_change = random.choice(result.markup)
    case = random.choice(range(1, 6))
    print(case)
    print(markup_to_change)

    match case:
        case 1:
            new_text = random.choice([get_rand_synonym(markup_to_change.cid), get_iupac(markup_to_change.cid)])
            text, shift = replace_text(text, markup_to_change.start, markup_to_change.length, new_text)
            markup_to_change.hit = new_text
            markup_to_change.length = len(new_text)
            shift_markup(result.markup, markup_to_change.start, shift)

        case 2:
            new_synonym = get_rand_synonym(markup_to_change.cid)
            new_string = f"{markup_to_change.hit} ({new_synonym})"
            text, shift = replace_text(text, markup_to_change.start, markup_to_change.length, new_string)
            markup_to_change.hit = new_string
            markup_to_change.length = len(new_string)
            shift_markup(result.markup, markup_to_change.start, shift)

        case 3:
            alias = random.choice([get_random_alias(), get_random_id()])
            text, shift = replace_text(text, markup_to_change.start, markup_to_change.length, alias)
            markup_to_change.hit = alias
            markup_to_change.length = len(alias)
            shift_markup(result.markup, markup_to_change.start, shift)

        case 4:
            new_name = random.choice([get_rand_synonym(markup_to_change.cid), get_iupac(markup_to_change.cid)])
            alias = get_random_id()
            new_text = f"{new_name} ({alias})"

            text, shift = replace_text(text, markup_to_change.start, markup_to_change.length, new_text)
            markup_to_change.hit = new_text
            markup_to_change.length = len(new_text)
            shift_markup(result.markup, markup_to_change.start, shift)

        case 5:
            first_markup = min(result.markup, key=lambda x: x.start)
            if not first_markup.cid:
                return string

            new_name = get_iupac(first_markup.cid)
            alias = get_random_id()
            prefix = f"{new_name} ({alias}): "

            new_markup = SimpleMarkup(
                start=0,
                length=len(prefix) - 2,
                cid=first_markup.cid,
                hit=f"{new_name} ({alias})",
            )

            text = prefix + text
            shift_markup(result.markup, -1, len(prefix))

            result.markup.append(new_markup)

    result.string = text
    result.markup = sorted(result.markup, key=lambda x: x.start)
    return result
