#-------------------------------------------------------------------------------
# Name:        ui_config
# Purpose:     UI page/bloc configuration management for the web interface
#
#              Single point of responsibility for the configuration lifecycle:
#              loading, decoding (YAML), validation and normalized serving of
#              the modular UI configuration (pages -> blocks -> views ->
#              widgets), as specified in doc/web_ui_modular.md section 2.
#
# Author:      Vibe Code
#
# Created:     21/10/2026
# Copyright:   (c) Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import os

import yaml

_logger = logging.getLogger("ShipDataServer." + __name__)

# Reference configuration shipped with the application, served when the
# web server configuration does not provide the ui_config key.
_DEFAULT_CONFIG_FILENAME = "web_ui_default.yml"

# Candidate locations for the reference configuration file, in resolution order:
# 1. conf/ directory at the root of the running instance (repo or deployment)
# 2. conf/ directory relative to the package (installed alongside sources)
_DEFAULT_CONFIG_CANDIDATES = (
    os.path.join("conf", _DEFAULT_CONFIG_FILENAME),
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                 "conf", _DEFAULT_CONFIG_FILENAME),
)

# Datasets standard exposites par les services (doc/web_ui_modular.md section 3.2)
_STANDARD_DATASETS = ("parameters", "data", "trend")

# Types d'echelle definis par les specifications (section 5.7)
_SCALE_TYPES = ("fixed", "dual", "dynamic")


class UIConfigError(Exception):
    """Raised when the UI configuration cannot be loaded at startup."""


class UIConfiguration:
    """UI configuration: loading, validation and normalized serving.

    The configuration follows doc/web_ui_modular.md section 2: three global
    sections (widgets, block_types, pages). Validation collects all the
    errors into a report so a misconfiguration is fully diagnosed at startup
    instead of failing one error at a time.
    """

    def __init__(self, config: dict, source: str = "unknown"):
        if not isinstance(config, dict):
            raise UIConfigError(f"UI configuration must be a mapping, got {type(config).__name__}")
        self._config = config
        self._source = source
        self._errors = []

    # --- Construction -----------------------------------------------------

    @classmethod
    def from_file(cls, path: str) -> "UIConfiguration":
        """Load and decode a UI configuration YAML file.

        Raises UIConfigError when the file cannot be read or decoded - a bad
        configuration path is a startup error, not a silent fallback.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
        except OSError as e:
            raise UIConfigError(f"Cannot read UI configuration file {path}: {e}") from e
        except yaml.YAMLError as e:
            raise UIConfigError(f"Cannot decode UI configuration file {path}: {e}") from e
        return cls(config, source=path)

    @classmethod
    def default(cls) -> "UIConfiguration":
        """Load the reference configuration shipped with the application.

        Raises UIConfigError when no candidate file is found - the embedded
        frontend default is then the only remaining fallback.
        """
        for candidate in _DEFAULT_CONFIG_CANDIDATES:
            if os.path.isfile(candidate):
                return cls.from_file(candidate)
        raise UIConfigError(
            f"Reference UI configuration file {_DEFAULT_CONFIG_FILENAME} not found in "
            f"{[os.path.dirname(c) for c in _DEFAULT_CONFIG_CANDIDATES]}")

    # --- Accessors --------------------------------------------------------

    @property
    def source(self) -> str:
        return self._source

    def as_dict(self) -> dict:
        """The raw configuration dictionary, ready to serve on /api/ui_config."""
        return self._config

    @property
    def widgets(self) -> list:
        return self._config.get("widgets", [])

    @property
    def block_types(self) -> list:
        return self._config.get("block_types", [])

    @property
    def pages(self) -> list:
        return self._config.get("pages", [])

    # --- Validation -------------------------------------------------------

    def validate(self) -> list:
        """Validate the configuration against the specification.

        Returns the full list of errors (empty when valid). Errors reference
        the section of the specification that is violated.
        """
        self._errors = []
        if "pages" not in self._config:
            self._errors.append("missing 'pages' section (doc/web_ui_modular.md section 2.1)")
            return self._errors

        widget_ids = self._collect_section_ids("widgets")
        block_type_ids = self._collect_section_ids("block_types")

        # Block type definitions also reference widgets - validate them so a
        # bad reference is caught at startup, not on the first page display.
        for i, block_type in enumerate(self._config.get("block_types", []) or []):
            if isinstance(block_type, dict):
                self._validate_definition(block_type.get("definition"),
                                          f"block_type '{block_type.get('id', i)}'", widget_ids)

        if "pages" in self._config:
            page_ids = set()
            for i, page in enumerate(self._config["pages"]):
                self._validate_page(page, i, page_ids, widget_ids, block_type_ids)
        return self._errors

    def validate_or_raise(self):
        """Validate and raise UIConfigError on the first problem (startup)."""
        errors = self.validate()
        if errors:
            raise UIConfigError(
                f"Invalid UI configuration ({self._source}): " + "; ".join(errors))

    def _collect_section_ids(self, section: str) -> dict:
        ids = {}
        for i, item in enumerate(self._config.get(section, []) or []):
            if isinstance(item, dict) and "id" in item:
                ids.setdefault(item["id"], []).append(i)
                if len(ids[item["id"]]) > 1:
                    self._errors.append(f"duplicate id '{item['id']}' in section '{section}'")
        return ids

    def _validate_page(self, page: dict, index: int, page_ids: set,
                      widget_ids: dict, block_type_ids: dict) -> None:
        if not isinstance(page, dict):
            self._errors.append(f"pages[{index}] must be a mapping")
            return
        page_id = page.get("id")
        if not page_id:
            self._errors.append(f"pages[{index}] missing 'id'")
            return
        if page_id in page_ids:
            self._errors.append(f"duplicate page id '{page_id}'")
        page_ids.add(page_id)

        if page.get("builtin") == "services":
            # Page 0: built-in, rendered by the legacy code - nothing to check.
            return

        layout = page.get("layout") or {}
        if layout and not isinstance(layout, dict):
            self._errors.append(f"page '{page_id}': 'layout' must be a mapping (section 2.3)")
        columns = layout.get("columns") if isinstance(layout, dict) else None
        if columns is not None and (not isinstance(columns, int) or columns < 1):
            self._errors.append(f"page '{page_id}': 'layout.columns' must be a positive integer (section 2.3)")

        # Page-level parameters endpoint (doc section 3.3): scale/title paths
        # unresolved in the block service parameters are looked up here.
        parameters_endpoint = page.get("parameters_endpoint")
        if parameters_endpoint is not None:
            self._validate_endpoint(parameters_endpoint, f"page '{page_id}': 'parameters_endpoint'")

        blocks = page.get("blocks") or []
        if not isinstance(blocks, list):
            self._errors.append(f"page '{page_id}': 'blocks' must be a list")
            return
        block_ids = set()
        for i, block in enumerate(blocks):
            self._validate_block(block, f"page '{page_id}' block[{i}]",
                                 block_ids, widget_ids, block_type_ids)

    def _validate_block(self, block: dict, where: str, block_ids: set,
                        widget_ids: dict, block_type_ids: dict) -> None:
        if not isinstance(block, dict):
            self._errors.append(f"{where} must be a mapping")
            return
        block_id = block.get("id")
        if not block_id:
            self._errors.append(f"{where} missing 'id'")
        elif block_id in block_ids:
            self._errors.append(f"{where} duplicate block id '{block_id}'")
        else:
            block_ids.add(block_id)

        # type XOR definition (section 2.4)
        has_type = "type" in block
        has_definition = "definition" in block
        if has_type and has_definition:
            self._errors.append(f"{where}: 'type' and 'definition' are mutually exclusive (section 2.4)")
        if has_type and block["type"] not in block_type_ids:
            self._errors.append(f"{where} references unknown block_type '{block['type']}'")
        if not has_type and not has_definition:
            self._errors.append(f"{where} requires either 'type' or 'definition' (section 2.4)")

        # A block is either repeated (base address) or a simple block (endpoint)
        if "repeat" in block:
            self._validate_repeat(block["repeat"], where)
        elif "endpoint" in block:
            self._validate_endpoint(block["endpoint"], where)
        else:
            self._errors.append(f"{where} requires 'endpoint' or 'repeat' (section 2.4/2.5)")

        # Views: check widget references on the inline definition
        definition = block.get("definition")
        if definition:
            self._validate_definition(definition, where, widget_ids)

        # Optional explicit position
        position = block.get("position")
        if position is not None:
            if not isinstance(position, dict) or not {"row", "column"} <= set(position):
                self._errors.append(f"{where}: 'position' must be {{row: R, column: C}} (section 2.3)")

    def _validate_repeat(self, repeat, where: str) -> None:
        if not isinstance(repeat, dict):
            self._errors.append(f"{where}: 'repeat' must be a mapping {{source_endpoint, block_endpoint}} (section 2.5)")
            return
        source_endpoint = repeat.get("source_endpoint")
        if not source_endpoint:
            self._errors.append(f"{where}: 'repeat' missing 'source_endpoint' (section 2.5)")
        block_endpoint = repeat.get("block_endpoint")
        if not block_endpoint:
            self._errors.append(f"{where}: 'repeat' missing 'block_endpoint' (section 2.5)")
        if block_endpoint and ("{service}" not in block_endpoint or "{instance}" not in block_endpoint):
            self._errors.append(
                f"{where}: 'repeat.block_endpoint' must contain the {{service}} and {{instance}} placeholders (section 2.5)")

    def _validate_endpoint(self, endpoint, where: str) -> None:
        if not isinstance(endpoint, str) or not endpoint.startswith("/api/"):
            self._errors.append(f"{where}: endpoint must be an API path starting with /api/ (section 3.2)")
            return
        parts = endpoint.rstrip("/").split("/")[2:]  # drop '', 'api'
        if parts and parts[0] in _STANDARD_DATASETS:
            # Short form /api/<service>/<dataset> - allowed (instance 0)
            if len(parts) > 2:
                self._errors.append(f"{where}: endpoint {endpoint} does not match the data path schema (section 3.2)")
        elif len(parts) not in (2, 3, 4):
            self._errors.append(
                f"{where}: endpoint {endpoint} must match /api/<service>/<instance>/<dataset>[/<name>] (section 3.2)")

    def _validate_definition(self, definition, where: str, widget_ids: dict) -> None:
        if not isinstance(definition, list):
            self._errors.append(f"{where}: 'definition' must be a list of views")
            return
        for i, view in enumerate(definition):
            if not isinstance(view, dict):
                self._errors.append(f"{where} definition[{i}] must be a mapping")
                continue
            if not view.get("data"):
                self._errors.append(f"{where} definition[{i}] missing 'data' path (section 2.4)")
            widget = view.get("widget")
            if widget and widget not in widget_ids:
                self._errors.append(f"{where} definition[{i}] references unknown widget '{widget}'")

    # --- Serving ----------------------------------------------------------

    def normalized(self) -> dict:
        """Validate then return the configuration ready to serve.

        Called by the web server when serving /api/ui_config: a configuration
        that reached this point is either valid or the errors have been
        logged - the frontend embedded default remains the ultimate fallback.
        """
        errors = self.validate()
        if errors:
            _logger.error("UI configuration errors (%s): %s", self._source, "; ".join(errors))
        return self._config
