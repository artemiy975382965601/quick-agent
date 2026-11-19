from dataclasses import dataclass, field

import annotationlib


class FieldMeta(type):
    def __new__(mcs, name, bases, namespace, **kwargs):
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        try:
            annotations = annotationlib.get_annotations(
                cls, format=annotationlib.Format.FORWARDREF
            )
        except Exception:
            annotations = {}
        cls.__fields__ = tuple(annotations)
        return cls


class Fielded(metaclass=FieldMeta):
    __fields__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FileContent(Fielded):
    path: str
    content: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class FolderContent(Fielded):
    path: str
    files: list[FileContent] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PinnedContent(Fielded):
    files: list[FileContent] = field(default_factory=list)
    folders: list[FolderContent] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.files and not self.folders


@dataclass(frozen=True, slots=True)
class PromptParts(Fielded):
    base: str
    client: str
    pinned: PinnedContent
