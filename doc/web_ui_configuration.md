# Web UI Configuration

The web interface of the navigation server is driven by a **declarative
configuration**: the pages, their blocks and the widgets are described in a
YAML file, not hard-coded. Adding a page, a block or a display only requires
a configuration change - no HTML, no navigation code.

This document is the reference for that configuration. The working
specification (concepts and design rationale) is kept in
`doc/web_ui_modular.md` (French); this document is the product
documentation.

## 1. Concepts

| Concept | Definition |
|---|---|
| **Page** | A set of blocks. The page is the navigation unit (navigation bar). |
| **Block** | Bound to an **entity** (energy controller, battery, MPPT, DC-DC charger...); displays a set of views on that entity. |
| **View** | One piece of information (a value or a series) with its representation, rendered by a **widget**. |
| **Widget** | A parameterized elementary view built on a hard-coded base widget (bar, curve, indicator). |
| **Dataset** | One of the three standard data sets exposed by every energy service: `parameters` (static/semi-static), `data` (instantaneous), `trend` (immediate history). |

Responsibility chain:

```
Page (e.g. Energy Management)
  └─ Block (e.g. battery) — bound to the battery entity
       └─ Views (current, state of charge, trend...)
            └─ Data: /api/<service>/<instance>/<dataset>/<name>
                 └─ Web server collector
                      └─ gRPC service (BatteryService)
```

## 2. Configuration file

### 2.1 Providing the configuration

The UI configuration is a YAML file, referenced by the web server
configuration (`web_server.yml`):

```yaml
servers:
- Main:
      class: WebTopServer
      port: 8080
      ...
      ui_config: web_ui.yml     # relative to the configuration directory
```

When the `ui_config` key is absent, the reference configuration shipped with
the application (`conf/web_ui_default.yml`) is served. The file is loaded,
decoded and validated at startup by the `ui_config` module
(`navigation_server/web_server/ui_config.py`) - a misconfiguration is fully
diagnosed at startup, and the frontend embedded default is the ultimate
fallback.

For a standalone test, the web server also accepts the `--ui-config <file>`
command line option.

The configuration is served to the browser on `/api/ui_config`.

### 2.2 Structure

Three global sections, plus a color palette:

| Section | Role | Reuse |
|---|---|---|
| `colors` | Named color palette referenced by the widgets | global |
| `widgets` | Parameterized widgets built on the base widgets | across block types and pages |
| `block_types` | Reusable block definitions (title, status widget, views) | across pages |
| `pages` | Pages: layout, blocks, endpoints, refresh cycle | — |

A block either references a `block_type` **or** carries its `definition`
inline (one-off override).

## 3. Pages

```yaml
pages:
  - id: services              # page 0: built-in, always present
    title_i18n: nav.services
    builtin: services
    optional: false

  - id: ems
    title_i18n: nav.ems
    layout: {columns: 2}
    refresh_interval: 10000    # ms
    availability_endpoint: /api/energy_available
    parameters_endpoint: /api/energy/parameters
    blocks: [ ... ]
```

| Key | Meaning |
|---|---|
| `id` | unique page identifier (used in navigation and URLs) |
| `title_i18n` | translation key of the navigation button |
| `builtin: services` | page 0 rendered by the legacy code - always present, not part of the block framework |
| `layout.columns` | number of grid columns of the page |
| `refresh_interval` | refresh cycle of the page data, in ms |
| `availability_endpoint` | when set, the page is only shown when the endpoint answers `{available: true}` |
| `parameters_endpoint` | page-level parameters (fallback resolution of the scale/title paths) |

### Block positioning (§ layout)

Blocks are placed in the page grid:

| Key | Meaning |
|---|---|
| `position: {row: R, column: C}` | explicit position in the grid (0-indexed) |
| `width: N` | width in columns (default 1) |
| `priority: P` | automatic placement order: blocks without `position` are placed by increasing priority (1 = most important), then in declaration order |

## 4. Blocks

```yaml
blocks:
  - id: energy_summary
    title: Energy Controller
    priority: 1
    position: {row: 0, column: 0}
    width: 2
    endpoint: /api/energy/data
    definition: [ ... ]        # inline views, or:
  - id: energy-sources
    type: energy_source        # reference to a block_type
    repeat: { ... }
```

| Key | Meaning |
|---|---|
| `id` | unique block identifier within the page |
| `title` | literal text, or a data path (`parameters/label`), or an i18n key |
| `type` | reference to a `block_type` (mutually exclusive with `definition`) |
| `definition` | inline list of views |
| `endpoint` | data path of the block's primary dataset |
| `process` | optional host process qualification (required only when several processes host the service, e.g. console) |
| `position`, `width`, `priority` | layout |
| `repeat` | repeated block (one instance per item of a collection) |

### Repeated blocks

A repeated block is instantiated **once per item** returned by its source
endpoint - the number of instances follows the application data (e.g. the
active energy sources):

```yaml
repeat:
  source_endpoint: /api/energy/parameters/sources
  block_endpoint: /api/{service}/{instance}
  types:
    mppt: energy_source        # optional: block type per service
    dc_dc: dc_dc_source
```

- `source_endpoint` returns the collection of items (each item carries at
  least `service` and `instance`, optionally `process`);
- `block_endpoint` is the **base address** template of each instance,
  built by substituting `{service}` and `{instance}`;
- `types` (optional) selects the block type **per service**: heterogeneous
  entities do not expose the same dataset fields (e.g. `MPPT_Data` has
  `current`/`power`, `DC_DC_Data` has `output_current`/`output_power`).

## 5. Data paths

### 5.1 Endpoints

```
/api/<service>/<instance>/<dataset>/<name>    multi-instance services
/api/<service>/<dataset>/<name>               singleton services (instance omitted)
```

- **service**: the gRPC service (e.g. `energy`, `battery`, `mppt`, `dc_dc`)
- **instance**: entity instance for multi-instance services; **omitted for
  singletons** (instance 0 implicit)
- **dataset**: `parameters`, `data` or `trend`
- **name**: protobuf field name

The process hosting the service is resolved by the web server (implicit
when a single process hosts it; qualify with `process:` when several do).

### 5.2 View data paths

A view's `data` is `<dataset>/<name>` or `<name>` alone:

- **implicit dataset** (`main_voltage`): resolves in the block's **primary**
  dataset - the one stated in the `endpoint` (`data` by default). The
  dataset is stated once, in the endpoint;
- **explicit dataset** (`trend/power`, `parameters/label`): references that
  dataset - a dataset other than the primary one triggers an additional
  fetch per refresh cycle.

Fetch cycle (driven by what is displayed):
- `data`: at each page refresh cycle, one fetch per endpoint;
- `trend`: at the same cycle, **only if** at least one view references it;
- `parameters`: at page activation (and on context change), only if a
  title, a scale or a repeat references it.

### 5.3 Conventions

- **Ratios** (e.g. state of charge) are transported between 0 and 1; the
  percent conversion (0-100) is a display responsibility - use the widget
  parameter `ratio_percent: true`;
- **Live status fields** (`communication_ok`, `state`, `off_reason`) are
  present uniformly in both the `parameters` and `data` datasets of every
  energy service;
- **No duplication between entities**: each entity is served by its own
  dedicated service (the energy controller serves only its consolidated
  view).

## 6. Views and widgets

### 6.1 Views

```yaml
- view: state_of_charge
  title: State of charge
  data: state_of_charge
  widget: state_of_charge_viewgraph
```

| Key | Meaning |
|---|---|
| `view` | view identifier |
| `title` | label displayed by the widget |
| `data` | data path (see §5.2) |
| `widget` | reference to a parameterized widget |

### 6.2 Widgets

```yaml
widgets:
  - id: state_of_charge_viewgraph
    base_widget: positive_viewgraph
    unit: "%"
    precision: 1
    color: state_of_charge
    ratio_percent: true
    scale: {type: fixed, max: 100}
```

| Parameter | Values | Meaning |
|---|---|---|
| `base_widget` | see §6.3 | hard-coded renderer |
| `unit` | string | unit symbol displayed with the value |
| `precision` | int [0-3] | decimal digits (default 0) |
| `color` | string | palette name (§ `colors`) or direct value |
| `ratio_percent` | bool | transport ratio 0-1 displayed as 0-100 % |
| `scale` | object (§6.4) | display scale |

### 6.3 Base widgets

| Base widget | Description |
|---|---|
| `positive_viewgraph` | vertical bar, 0 at the bottom |
| `symmetric_viewgraph` | vertical bar centered on 0 (zero line drawn): positive above, negative below |
| `single_positive_curve` | one curve, positive values |
| `single_symmetric_curve` | one curve centered on 0: symmetric scale (+/- max of the series), zero reference line, area filled between the curve and the zero line |
| `device_state_indicator` | 3-state operating indicator (block title): **NO COM** (grey) when `communication_ok` is false, **OFF** (red) when `state` = Off, **ON** (green) otherwise - dot + text label |
| `communication_indicator` | communication status dot (green/red) |

Curve widgets apply the widget `color` to the stroke and to a translucent
area.

### 6.4 Scales

```yaml
scale: {type: fixed, max: parameters/max_voltage_scale}

scale:
  type: dual
  low: parameters/total_power_low    # low scale AND switching threshold
  high: parameters/total_power_high  # high scale

scale: {type: dynamic}
```

| Type | Meaning |
|---|---|
| `fixed` | constant scale; `max` is the displayable maximum (data path or literal number) |
| `dual` | automatic low/high switching: displayed on the low scale while \|value\| ≤ `low`, otherwise on the high scale. The **High-Power ⚡ / Low-Power ◎** mode indicator shown by the widget is derived by the frontend from this same rule |
| `dynamic` | recomputed from the displayed series (observed min/max) |

Scale references resolve in the block's service `parameters` first, then in
the page `parameters_endpoint`.

## 7. Reference example

The reference configuration `conf/web_ui_default.yml` defines the Energy
Management page: the energy controller block (voltages, production,
consumption, battery balance, state of charge, energy stock, balance
trend) and one block per energy source (MPPT, DC-DC) with current, power
and power trend. It is the recommended starting point for writing a custom
configuration.

## 8. Adding a page or a block

1. Create or reuse **widgets** (palette colors, base widget, unit,
   precision, scale);
2. Create or reuse a **block type** (or define the views inline);
3. Declare the **page** (layout, blocks, refresh interval, availability);
4. No HTML or navigation change: the framework builds the navigation
   buttons and the pages dynamically.

Keep the look and feel: the existing base widgets are the reference
renderers - new representations should be added as new base widgets, not
by diverging from the parameterization model.
