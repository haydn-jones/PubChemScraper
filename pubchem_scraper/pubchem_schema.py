from typing import Literal

from pydantic import BaseModel, Field


class TOCHeadingCompound(BaseModel):
    type: Literal["Compound"]
    TOCHeading: str = Field(alias="#TOCHeading")


class _Markup(BaseModel):
    Start: int | None = None
    Length: int | None = None
    URL: str | None = None
    Type: str | None = None
    Extra: str | None = None

    @property
    def has_cid(self) -> bool:
        return (self.Extra is not None) and self.Extra.startswith("CID")

    @property
    def cid(self) -> int | None:
        if self.has_cid and self.Extra:
            return int(self.Extra.split("-")[1])
        return None


class StringWithMarkupItem(BaseModel):
    String: str
    Markup: list[_Markup] = []

    @property
    def has_cid(self) -> bool:
        return any(markup.has_cid for markup in self.Markup)

    # Custom print
    def __str__(self):
        ret = f"{self.String}\n"
        for markup in self.Markup:
            if not markup.has_cid:
                continue
            if markup.Start is None or markup.Length is None:
                continue

            hit = self.String[markup.Start : markup.Start + markup.Length]
            cid = markup.Extra.split("-")[1] if markup.Extra else None

            ret += f"\tStart={markup.Start} Len={markup.Length} Hit='{hit}' CID='{cid}'\n"

        return ret


class ExternalDataReference(BaseModel):
    ExternalDataURL: list[str]
    MimeType: str


class StringWithMarkup(BaseModel):
    StringWithMarkup: list[StringWithMarkupItem]

    @property
    def has_cid(self) -> bool:
        return any(item.has_cid for item in self.StringWithMarkup)


class SimpleMarkup(BaseModel):
    start: int
    length: int

    cid: int
    hit: str

    def comp_hit(self, string: str):
        return string[self.start : self.start + self.length]


class SimpleStringWithMarkup(BaseModel):
    string: str
    markup: list[SimpleMarkup]

    @classmethod
    def from_string_with_markup(cls, swm: StringWithMarkup) -> "SimpleStringWithMarkup":
        # Track the current offset as we build the combined string
        current_offset = 0
        combined_string_parts: list[str] = []
        combined_markup: list[SimpleMarkup] = []

        for item in swm.StringWithMarkup:
            # Add the string to our combined string
            combined_string_parts.append(item.String)

            # Adjust and add markup
            for markup in item.Markup:
                if markup.Start is None or markup.Length is None or not markup.has_cid:
                    raise ValueError(f"Invalid markup: {markup}")

                adjusted_markup = SimpleMarkup(
                    start=markup.Start + current_offset,
                    length=markup.Length,
                    cid=markup.cid,  # type: ignore
                    hit=item.String[markup.Start : markup.Start + markup.Length],
                )
                combined_markup.append(adjusted_markup)

            current_offset += len(item.String) + 1

        combined_string = "\n".join(combined_string_parts)

        return cls(string=combined_string, markup=combined_markup)

    def __str__(self):
        ret = f"{self.string}\n"
        for markup in self.markup:
            ret += (
                f"\tStart={markup.start} Len={markup.length} Hit='{markup.comp_hit(self.string)}' CID='{markup.cid}'\n"
            )

        return ret


class ExternalTableReference(BaseModel):
    ExternalTableName: str


class BinaryData(BaseModel):
    Binary: list[str]
    MimeType: str


class NumericValue(BaseModel):
    Number: list[int | float]


class ContentSection(BaseModel):
    TOCHeading: TOCHeadingCompound
    Value: StringWithMarkup | ExternalTableReference | ExternalDataReference | BinaryData | NumericValue
    Name: str | None = None
    Description: str | None = None
    Reference: list[str] | None = None


class _LinkedRecords(BaseModel):
    CID: list[int] | None = None
    SID: list[int] | None = None


class Annotation(BaseModel):
    SourceName: str
    SourceID: str
    Data: list[ContentSection]
    ANID: int
    Name: str | None = None
    Description: str | None = None
    URL: str | None = None
    LicenseURL: str | None = None
    LicenseNote: str | None = None
    LinkedRecords: _LinkedRecords | None = None


class Annotations(BaseModel):
    Annotation: list[Annotation]
    Page: int
    TotalPages: int


class Record(BaseModel):
    Annotations: Annotations


class SimpleContentSection(BaseModel):
    Value: StringWithMarkup
    Name: str | None = None
    Description: str | None = None
    Reference: list[str] | None = None

    @classmethod
    def from_content_section(cls, content_section: ContentSection) -> "SimpleContentSection":
        return cls(
            Value=content_section.Value
            if isinstance(content_section.Value, StringWithMarkup)
            else StringWithMarkup(StringWithMarkup=[]),
            Name=content_section.Name,
            Description=content_section.Description,
            Reference=content_section.Reference,
        )

    @property
    def flat_string(self) -> str:
        return "\n".join([item.String for item in self.Value.StringWithMarkup])


class SimpleAnnotation(BaseModel):
    SourceName: str
    Data: list[SimpleContentSection]
    ANID: int
    LinkedRecords: list[int] | None = None

    @classmethod
    def from_annotation(cls, annotation: Annotation) -> "SimpleAnnotation":
        content_sections = []
        for content_section in annotation.Data:
            if not isinstance(content_section.Value, StringWithMarkup):
                continue
            content_sections.append(SimpleContentSection.from_content_section(content_section))

        return cls(
            SourceName=annotation.SourceName,
            Data=content_sections,
            ANID=annotation.ANID,
            LinkedRecords=annotation.LinkedRecords.CID if annotation.LinkedRecords else None,
        )


class SimpleRecord(BaseModel):
    TOCHeading: str
    Annotations: list[SimpleAnnotation]

    @classmethod
    def from_record(cls, record: Record) -> "SimpleRecord":
        annotations = []
        for annotation in record.Annotations.Annotation:
            simple_annotation = SimpleAnnotation.from_annotation(annotation)
            if simple_annotation.Data:
                annotations.append(simple_annotation)

        return cls(
            Annotations=annotations,
            TOCHeading=record.Annotations.Annotation[0].Data[0].TOCHeading.TOCHeading,
        )


class SimpleElement(BaseModel):
    string: SimpleStringWithMarkup
    label: str
    records: list[int] | None = None
