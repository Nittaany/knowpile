"""
The manifest is the Step-1 evidence-inventory artifact for one major project
-- the traceability record every derived fact in the eventual Layer-2 file
must trace back to.

Schema kept flat deliberately (no nested "supporting docs" array under
research): a nested-optional structure was floated during design but never
proven necessary against a real project.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from knowpiler.core.utils import slugify, strip_shell_quotes

SCHEMA_VERSION = 1

ReportType = Literal[
    "final_report", "architecture_report", "functional_report",
    "research_report", "synopsis", "other",
]


class CodePaths(BaseModel):
    root_dir: str
    src_dir: str


class ReadmeInfo(BaseModel):
    status: Literal["collected", "missing"] = "missing"
    path: Optional[str] = None

    @field_validator("path")
    @classmethod
    def _clean_path(cls, v: Optional[str]) -> Optional[str]:
        return strip_shell_quotes(v) if v else v

    @model_validator(mode="after")
    def _status_matches_path(self) -> "ReadmeInfo":
        # Derive status from the final cleaned path -- never trust status
        # as a separately-passed value that could disagree with path.
        self.status = "collected" if self.path else "missing"
        return self


class TypedFile(BaseModel):
    type: str
    path: str

    @field_validator("path")
    @classmethod
    def _clean_path(cls, v: str) -> str:
        return strip_shell_quotes(v)


class PlainFile(BaseModel):
    path: str

    @field_validator("path")
    @classmethod
    def _clean_path(cls, v: str) -> str:
        return strip_shell_quotes(v)


class ArchDiagramInfo(BaseModel):
    status: Literal["collected", "missing"] = "missing"
    path: Optional[str] = None

    @field_validator("path")
    @classmethod
    def _clean_path(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "null":
            return None
        return strip_shell_quotes(v)

    @model_validator(mode="after")
    def _status_matches_path(self) -> "ArchDiagramInfo":
        self.status = "collected" if self.path else "missing"
        return self


class Manifest(BaseModel):
    schema_version: int = SCHEMA_VERSION
    project: str
    staging_dir: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    code: CodePaths
    readme: ReadmeInfo = ReadmeInfo()
    reports: List[TypedFile] = []
    research: List[PlainFile] = []
    presentations: List[PlainFile] = []
    notes: List[PlainFile] = []
    arch_diagram: ArchDiagramInfo = ArchDiagramInfo()

    # Filled in once `rewrite` actually runs -- traceability for which model
    # produced the Layer-2 semantic rewrite, not guessed after the fact.
    backend_used: Optional[str] = None
    model_used: Optional[str] = None

    def save(self, path: Optional[Path] = None) -> Path:
        target = path or (Path(self.staging_dir) / "manifest.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.model_dump(), indent=2))
        return target

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        return cls(**json.loads(Path(path).read_text()))


def create_manifest(
    project: str,
    root_dir: str,
    src_dir: str,
    storage_root: str,
    readme_path: Optional[str] = None,
    reports: Optional[List[dict]] = None,
    research: Optional[List[str]] = None,
    presentations: Optional[List[str]] = None,
    notes: Optional[List[str]] = None,
    arch_diagram_path: Optional[str] = None,
) -> Manifest:
    """Build, validate, and save a Manifest from plain values.

    This is the one place a Manifest gets constructed. A terminal interface
    gathers these same arguments one prompt at a time; a future web
    interface would gather them from one HTTP request body. Neither
    interface touches Pydantic or the manifest schema directly.
    """
    staging_dir = str(Path(storage_root) / slugify(project))

    manifest = Manifest(
        project=project,
        staging_dir=staging_dir,
        code=CodePaths(root_dir=root_dir, src_dir=src_dir),
        readme=ReadmeInfo(status="collected", path=readme_path) if readme_path else ReadmeInfo(),
        reports=[TypedFile(**r) for r in (reports or [])],
        research=[PlainFile(path=p) for p in (research or [])],
        presentations=[PlainFile(path=p) for p in (presentations or [])],
        notes=[PlainFile(path=p) for p in (notes or [])],
        arch_diagram=(
            ArchDiagramInfo(status="collected", path=arch_diagram_path)
            if arch_diagram_path
            else ArchDiagramInfo()
        ),
    )
    manifest.save()
    return manifest
