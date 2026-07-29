from __future__ import annotations

from dataclasses import dataclass

from openchem.domain.common import CacheState
from openchem.domain.conformer import ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.events.base import Event


@dataclass(frozen=True)
class MoleculeChanged(Event):
    molecule_uuid: str


@dataclass(frozen=True)
class MoleculeSelected(Event):
    molecule_uuid: str | None


@dataclass(frozen=True)
class ProjectLoaded(Event):
    project_uuid: str


@dataclass(frozen=True)
class ProjectClosed(Event):
    project_uuid: str


@dataclass(frozen=True)
class DescriptorInvalidated(Event):
    molecule_uuid: str
    descriptor_id: str


@dataclass(frozen=True)
class DescriptorComputed(Event):
    descriptor: DescriptorValue


@dataclass(frozen=True)
class ConformerJobStateChanged(Event):
    molecule_uuid: str
    state: CacheState
    message: str = ""


@dataclass(frozen=True)
class ConformersReady(Event):
    molecule_uuid: str
    conformers: list[ConformerModel]


@dataclass(frozen=True)
class ConformersChanged(Event):
    molecule_uuid: str


@dataclass(frozen=True)
class ConformerSelected(Event):
    molecule_uuid: str
    conformer_id: str | None


@dataclass(frozen=True)
class PluginLoaded(Event):
    plugin_id: str


@dataclass(frozen=True)
class SettingsChanged(Event):
    key: str
