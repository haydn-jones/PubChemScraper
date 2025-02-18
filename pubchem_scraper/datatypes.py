import re
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from functools import cached_property

from pydantic import BaseModel


class Molecule(BaseModel):
    name: str
    alternatives: list[str] = []

    @cached_property
    def _all_ids(self):
        all_ids = [self.name, *self.alternatives]
        all_ids = [map_unicode_characters(id_) for id_ in all_ids]

        all_ids = set(all_ids)

        # Include upper and lowercase
        all_ids.update([id_.lower() for id_ in all_ids])

        # Now, go through everything and add strings with greek letters replaced with english words and single letters
        updates = []
        for id_ in all_ids:
            updates.append(replace_greek_letters(id_))
            updates.append(replace_greek_single_letter(id_))

        all_ids.update(updates)

        return all_ids


class Paragraph(BaseModel):
    text: str

    gt_tags: list[Molecule]


class Example(BaseModel):
    sys_prompt: str
    user_prompt: str
    response: str


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        if x != self.parent.setdefault(x, x):
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x, y):
        self.parent[self.find(x)] = self.find(y)


def merge_molecules(molecules: list[Molecule]) -> list[Molecule]:
    uf = UnionFind()
    id_to_indices = defaultdict(set)

    for idx, mol in enumerate(molecules):
        for id_ in mol._all_ids:
            id_to_indices[id_].add(idx)

    for indices in id_to_indices.values():
        indices = list(indices)
        for i in range(len(indices) - 1):
            uf.union(indices[i], indices[i + 1])

    groups = defaultdict(list)
    for idx in range(len(molecules)):
        root = uf.find(idx)
        groups[root].append(idx)

    merged_molecules = []
    for group in groups.values():
        names = set()
        alternatives = set()
        for idx in group:
            mol = molecules[idx]
            names.add(mol.name)
            alternatives.update(mol.alternatives)
        all_ids = names.union(alternatives)
        all_ids = dedup_prefer_capital(all_ids)  # type: ignore
        chosen_name = sorted(all_ids, key=len, reverse=True)[0]
        all_ids.remove(chosen_name)

        # Sort chosen names alphabetically, with capital letters first
        all_ids = sorted(all_ids, key=lambda x: (x.lower(), x))

        selected = []
        for id_ in all_ids:
            if id_.lower() in [s.lower() for s in selected]:
                continue
            selected.append(id_)

        merged_molecules.append(Molecule(name=chosen_name, alternatives=selected))

    return merged_molecules


MATCH_RE = re.compile(r"^(.*?)\s\((.*?)\)\s*$")
GREEK_RE = re.compile(r"[\u0370-\u03FF]")
ALIAS_RE = re.compile(r".*?(\d{1,2}[a-zA-Z]?)$")


def replace_greek_letters(text: str) -> str:
    def greek_to_english(match: re.Match) -> str:
        char = match.group(0)
        try:
            name = unicodedata.name(char).lower()
            name = name.replace("greek small letter ", "").replace("greek capital letter ", "")
            return name
        except ValueError:
            return char

    return GREEK_RE.sub(greek_to_english, text)


def replace_greek_single_letter(text: str) -> str:
    # fmt: off
    greek_to_english = {
        'α': 'a', 'Α': 'A',  # alpha
        'β': 'b', 'Β': 'B',  # beta
        'γ': 'g', 'Γ': 'G',  # gamma
        'δ': 'd', 'Δ': 'D',  # delta
        'ε': 'e', 'Ε': 'E',  # epsilon
        'ζ': 'z', 'Ζ': 'Z',  # zeta
        'η': 'h', 'Η': 'H',  # eta
        'θ': 'th', 'Θ': 'Th',  # theta
        'ι': 'i', 'Ι': 'I',  # iota
        'κ': 'k', 'Κ': 'K',  # kappa
        'λ': 'l', 'Λ': 'L',  # lambda
        'μ': 'm', 'Μ': 'M',  # mu
        'ν': 'n', 'Ν': 'N',  # nu
        'ξ': 'x', 'Ξ': 'X',  # xi
        'ο': 'o', 'Ο': 'O',  # omicron
        'π': 'p', 'Π': 'P',  # pi
        'ρ': 'r', 'Ρ': 'R',  # rho
        'σ': 's', 'Σ': 'S',  # sigma
        'ς': 's',            # final sigma
        'τ': 't', 'Τ': 'T',  # tau
        'υ': 'y', 'Υ': 'Y',  # upsilon
        'φ': 'ph', 'Φ': 'Ph',  # phi
        'χ': 'ch', 'Χ': 'Ch',  # chi
        'ψ': 'ps', 'Ψ': 'Ps',  # psi
        'ω': 'o', 'Ω': 'O'   # omega
    }
    # fmt: on

    for greek, english in greek_to_english.items():
        text = text.replace(greek, english)

    return text


def map_unicode_characters(text):
    translation_table = {
        ord("’"): "'",
        ord("“"): '"',
        ord("”"): '"',
        ord("—"): "-",
        ord("–"): "-",
        ord("…"): "...",
        ord("‘"): "'",
        ord("´"): "'",
        ord("″"): '"',
    }

    return text.translate(translation_table)


def dedup_prefer_capital(strings: Sequence[str]) -> list[str]:
    seen = {}
    for s in strings:
        lower = s.lower()
        if lower not in seen or s[0].isupper():
            seen[lower] = s

    return list(seen.values())
