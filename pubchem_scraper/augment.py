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


def augment(string: SimpleStringWithMarkup, n: int = 1) -> SimpleStringWithMarkup:
    """
    Augment chemical compound mentions in text using various transformation strategies n times.

    Performs one of five possible transformations for each augmentation:
    1. Replace compound with synonym or IUPAC name
    2. Add parenthetical synonym after compound
    3. Replace compound with alias (e.g., "compound 1a")
    4. Replace compound with IUPAC name/Synonym and alias
    5. Add IUPAC name and alias prefix at start of text

    Args:
        string: SimpleStringWithMarkup containing text and compound annotations
        n: Number of augmentations to perform (default=1)

    Returns:
        SimpleStringWithMarkup with augmented text and updated markup

    Raises:
        ValueError: If markup positions are invalid
    """
    if not string.markup:
        return string

    result = string.model_copy(deep=True)

    choices = []
    while len(choices) < n:
        choice = random.choice(range(1, 6))
        if choice == 5 and 5 in choices:
            continue

        choices.append(choice)

    for case in choices:
        if not result.markup:
            break

        markup_to_change = random.choice(result.markup)

        match case:
            case 1:
                result, text = _aug_type_1(markup_to_change, result)
            case 2:
                result, text = _aug_type_2(markup_to_change, result)
            case 3:
                result, text = _aug_type_3(markup_to_change, result)
            case 4:
                result, text = _aug_type_4(markup_to_change, result)
            case 5:
                result, text = _aug_type_5(markup_to_change, result)
            case _:
                raise ValueError("Invalid case number")

        result.string = text
        result.markup = sorted(result.markup, key=lambda x: x.start)

    return result


def _aug_type_1(markup_to_change: SimpleMarkup, result: SimpleStringWithMarkup) -> tuple[SimpleStringWithMarkup, str]:
    new_text = random.choice([get_rand_synonym(markup_to_change.cid), get_iupac(markup_to_change.cid)])
    text, shift = replace_text(result.string, markup_to_change.start, markup_to_change.length, new_text)
    markup_to_change.hit = new_text
    markup_to_change.length = len(new_text)
    shift_markup(result.markup, markup_to_change.start, shift)

    return result, text


def _aug_type_2(markup_to_change: SimpleMarkup, result: SimpleStringWithMarkup) -> tuple[SimpleStringWithMarkup, str]:
    new_synonym = get_rand_synonym(markup_to_change.cid)
    new_string = f"{markup_to_change.hit} ({new_synonym})"
    text, shift = replace_text(result.string, markup_to_change.start, markup_to_change.length, new_string)
    markup_to_change.hit = new_string
    markup_to_change.length = len(new_string)
    shift_markup(result.markup, markup_to_change.start, shift)

    return result, text


def _aug_type_3(markup_to_change: SimpleMarkup, result: SimpleStringWithMarkup) -> tuple[SimpleStringWithMarkup, str]:
    alias = random.choice([get_random_alias(), get_random_id()])
    text, shift = replace_text(result.string, markup_to_change.start, markup_to_change.length, alias)
    markup_to_change.hit = alias
    markup_to_change.length = len(alias)
    shift_markup(result.markup, markup_to_change.start, shift)

    return result, text


def _aug_type_4(markup_to_change: SimpleMarkup, result: SimpleStringWithMarkup) -> tuple[SimpleStringWithMarkup, str]:
    new_name = random.choice([get_rand_synonym(markup_to_change.cid), get_iupac(markup_to_change.cid)])
    alias = random.choice([get_random_alias(), get_random_id()])
    new_text = f"{new_name} ({alias})"

    text, shift = replace_text(result.string, markup_to_change.start, markup_to_change.length, new_text)
    markup_to_change.hit = new_text
    markup_to_change.length = len(new_text)
    shift_markup(result.markup, markup_to_change.start, shift)

    return result, text


def _aug_type_5(markup_to_change: SimpleMarkup, result: SimpleStringWithMarkup) -> tuple[SimpleStringWithMarkup, str]:
    first_markup = min(result.markup, key=lambda x: x.start)
    if not first_markup.cid:
        return result, result.string

    new_name = get_iupac(first_markup.cid)
    alias = random.choice([get_random_alias(), get_random_id()])
    prefix = f"{new_name} ({alias}): "

    new_markup = SimpleMarkup(
        start=0,
        length=len(prefix) - 2,
        cid=first_markup.cid,
        hit=f"{new_name} ({alias})",
    )

    text = prefix + result.string
    shift_markup(result.markup, -1, len(prefix))

    result.markup.append(new_markup)

    return result, text
