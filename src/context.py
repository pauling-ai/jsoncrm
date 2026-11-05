"""Explicit configuration and filesystem context for one CRM."""

from pathlib import Path

from jsoncrm.config import Config
from jsoncrm.invariants import identity_fields, normalize_records
from jsoncrm.utils import atomic_write_json, load_json


class CRMContext:
    def __init__(self, config, root, config_path=None):
        self.config = config
        self.root = Path(root).resolve()
        self._config_path = Path(config_path).resolve() if config_path else self.root / ".crm.json"
        self.identity_fields = identity_fields(config)

    @classmethod
    def from_file(cls, path=None):
        config_path = Path(path).resolve() if path else Path.cwd() / ".crm.json"
        return cls(Config.from_file(str(config_path)), config_path.parent, config_path)

    @property
    def config_path(self):
        return self._config_path

    @property
    def pipeline_stages(self):
        return self.config.pipeline_stages

    @property
    def pipeline_files(self):
        return [(stage["name"], self.root / stage["file"]) for stage in self.pipeline_stages]

    @property
    def transitions(self):
        return self.config.pipeline_transitions

    @property
    def score_order(self):
        return self.config.score_order

    def legacy_stage_path(self, name):
        stage = self.stage_for_name(name)
        return self.root / (stage["file"] if stage else f"{name}.json")

    @property
    def leads_file(self):
        return self.legacy_stage_path("leads")

    @property
    def prospects_file(self):
        return self.legacy_stage_path("prospects")

    @property
    def customers_file(self):
        return self.legacy_stage_path("customers")

    @property
    def competitors_file(self):
        return self.root / self.config.blocklist_file

    @property
    def pending_file(self):
        return self.root / ".pending_update.json"

    def transition_map(self, source, destination):
        return self.config.transition_map(source, destination)

    def stage_for_name(self, name):
        for stage in self.pipeline_stages:
            if stage["name"] == name:
                return stage
        return None

    def stage_path(self, name):
        stage = self.stage_for_name(name)
        if stage is None:
            raise KeyError(name)
        return self.root / stage["file"]

    def stage_for_path(self, path):
        target = Path(path).resolve()
        for stage in self.pipeline_stages:
            if (self.root / stage["file"]).resolve() == target:
                return stage
        return None

    def other_records(self, *excluded):
        excluded_paths = {Path(path).resolve() for path in excluded}
        records = []
        for _stage, path in self.pipeline_files:
            if path.resolve() not in excluded_paths and path.exists():
                data = load_json(path)
                if isinstance(data, list):
                    records.extend(data)
        return records

    def promote_map(self):
        result = {}
        for source, destinations in self.transitions.items():
            if not destinations:
                continue
            key = source[:-1] if source.endswith("s") else source
            result[key] = (
                self.stage_path(source).name,
                self.stage_path(destinations[0]).name,
            )
        return result

    def score_value(self, score):
        return self.score_order.get(score or "", 0)

    def write_json(self, path, data):
        stage = self.stage_for_path(path)
        if stage is not None:
            data = normalize_records(data, stage, self.identity_fields)
        atomic_write_json(path, data)
