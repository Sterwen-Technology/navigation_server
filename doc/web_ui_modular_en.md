# Web UI — Page / Block Modular Architecture

> English base version of this specification. The working draft is
> `doc/web_ui_modular.md` (French); in case of divergence during the design
> phase, the French version prevails.

## 1. Formalized concepts

The Web interface is organized along two levels of modularity:

| Concept | Definition |
|---|---|
| **Page** | A set of blocks. The page is the navigation unit (navigation bar). |
| **Block** | Bound to an **entity**; defines a **view** on that entity (which information is displayed). |
| **View** | The representation of the information: text, bar, centered bar, trend curve... |
| **Entity** | An application concept (energy controller, battery, energy source, MPPT, DC-DC charger, engine...). Each entity corresponds to a **data collector** in the backend, itself backed by a **gRPC service**. |

Complete responsibility chain:

```
Page (e.g. Energy Management)
  └─ Block (e.g. "battery") — bound to the "battery" entity
       └─ View (centered bar, bar, curve...)
            └─ Data: data path (/api/<service>/<instance>/data/<name>)
                 └─ Data collector (web_server/data_collectors.py)
                      └─ gRPC service (BatteryService)
```

Endpoint ↔ gRPC service mapping: `ENDPOINT_SERVICE_MAP` in
`navigation_server/web_server/data_collectors.py` (battery, mppt, energy,
dc_dc, engine, nmea2000, gnss, network, console...).

### General rules

1. **The Services page is page 0**: always present, not optional, rendered
   by the legacy code (`static/js/collectors/system.js`).
2. Any other page is **declared by configuration** and assembled by the
   page/block framework.
3. There is **no preconfigured block**: a block definition (the views it
   contains) is part of the configuration, based on parameterized block
   types and widgets.
4. **A gRPC service exposes three datasets**: `parameters` (static /
   semi-static), `data` (instantaneous), `trend` (immediate history).
   See §7 (protobuf rationalization).
5. **No data duplication between entities**, except two acknowledged
   exceptions:
   - the **consolidated** view presented by the Energy Controller (e.g.
     `battery_balance`, `state_of_charge`), which is its very purpose;
   - the live status fields (`communication_ok`, `state`, `off_reason`...)
     repeated in the `data` dataset of every service, to avoid permanently
     fetching the `parameters` dataset. These fields are present
     **uniformly in both datasets** (`parameters` and `data`) of all energy
     services; semi-static data stays in `parameters` only.

## 2. Interface configuration

The configuration is declarative. It defines: **widgets** (parameterized
elementary views), **block types** (reusable block definitions) and
**pages** (assembly of blocks).

### 2.1 File structure

Three **global** sections (not nested inside pages):

| Section | Role | Reuse |
|---|---|---|
| `widgets` | Parameterized widgets, built on hard-coded base widgets | across block types and pages |
| `block_types` | Reusable block types (title, status widget, list of views) | across pages |
| `pages` | Pages: layout, blocks, endpoints, refresh cycle | — |

A block in a page either references a `block_type` or carries its
`definition` inline (one-off override, no reuse).

### 2.2 Reference schema

*A significant but incomplete example at this stage: the definitive widget
list will be consolidated at the end of the design phase.*

```yaml
# --- Widgets (global) ----------------------------------------------
widgets:
  - id: voltage_viewgraph
    base_widget: positive_viewgraph
    unit: V
    precision: 2            # number of decimals (default 0)
    color: voltage          # reference to the color palette
    scale: {type: fixed, max: parameters/max_voltage_scale}

  - id: production_viewgraph
    base_widget: positive_viewgraph
    unit: W
    precision: 0
    scale:
      type: dual
      low: parameters/total_power_low
      high: parameters/total_power_high

  - id: power_balance
    base_widget: symmetric_viewgraph
    unit: W
    precision: 0
    color: power
    scale:
      type: dual
      low: parameters/total_power_low
      high: parameters/total_power_high

  - id: power_trend
    base_widget: single_positive_curve
    scale: {type: dynamic}

  - id: power_balance_trend
    base_widget: single_symmetric_curve
    scale: {type: dynamic}

# --- Block types (global) ------------------------------------------
block_types:
  - id: energy_source
    title: parameters/label        # path relative to the block's service
    top_widget: communication_indicator
    definition:
      - view: current
        title: Current
        data: data/current         # dataset always explicit
        widget: production_current_viewgraph
      - view: power
        title: Power
        data: data/power
        widget: production_viewgraph
      - view: power_trend
        title: Power trend
        data: trend/power          # a different dataset => one more fetch
        widget: power_trend

# --- Pages ----------------------------------------------------------
pages:
  - id: ems
    title_i18n: nav.ems
    layout:
      columns: 2
    refresh_interval: 10000        # ms
    availability_endpoint: /api/energy_available
    blocks:
      - id: energy_summary
        title: Energy Controller
        priority: 1
        position: {row: 0, column: 0}
        width: 2                    # 2 columns (default 1)
        endpoint: /api/energy/0/data
        definition:
          - view: main_voltage
            title: Main Voltage
            data: data/main_voltage
            widget: voltage_viewgraph
          - view: auxiliary_voltage
            title: Auxiliary Voltage
            data: data/auxiliary_voltage
            widget: voltage_viewgraph
          - view: production_power
            title: Production
            data: data/production_power
            widget: production_viewgraph
          - view: battery_power_balance
            title: Battery power
            data: data/battery_balance
            widget: power_balance
          - view: power_balance_trend
            title: Battery balance trend
            data: trend/battery_balance

      - id: energy-sources
        type: energy_source
        priority: 2
        repeat:
          source_endpoint: /api/energy/0/parameters/sources
          block_endpoint: /api/{service}/{instance}
```

### 2.3 Pages and layout

Each page declares a `layout`: a grid with `columns` columns (rows adapt to
the content; no fixed `rows` notion).

Block positioning is **explicit or automatic**:

| Key | Meaning |
|---|---|
| `position: {row: R, column: C}` | explicit position in the grid (0-indexed) |
| `width: N` | width in columns (default 1) |
| `priority: P` | automatic placement order: blocks without `position` are placed by increasing priority (1 = most important), then in declaration order on ties |

**priority** reflects the information hierarchy of the page: the most
important blocks are placed first (top/left), regardless of the order in
which they are written in the configuration.

### 2.4 Blocks

A block declares:

| Key | Meaning |
|---|---|
| `id` | unique identifier within the page |
| `title` | raw text, data path (`parameters/label`) or i18n key |
| `type` | reference to a `block_type` (mutually exclusive with `definition`) |
| `definition` | inline definition of the views (one-off override) |
| `endpoint` | data path of the block's primary dataset (`/api/<service>/<instance>/<dataset>`) |
| `process` | **optional**: host process qualification, required only if the service is hosted by several processes (§3.1) |
| `position`, `width`, `priority` | layout (§2.3) |
| `repeat` | repeated block (§2.5) |

Each view (`definition`) declares: `view` (identifier), `title`, `data`
(relative path — see §3.3) and `widget` (reference to a parameterized
widget).

### 2.5 Repeated blocks (`repeat`)

A repeated block is instantiated **once per item** returned by its source
endpoint — the number of instances follows the application data (e.g.
number of active energy sources).

```yaml
repeat:
  source_endpoint: /api/energy/0/parameters/sources
  block_endpoint: /api/{service}/{instance}
```

- `source_endpoint`: endpoint returning the collection describing the items
  (at least `service` and `instance` per item; an item may also carry
  `process` if the service is hosted by several processes, §3.1).
- `block_endpoint`: **base** address template of each instance
  (`/api/<service>/<instance>`), built by substituting the `{service}` and
  `{instance}` placeholders from the item. The primary dataset is
  determined by the views of the block type (§2.4) and the explicit `data`
  paths of each view.
- `types` (optional): block type **per service** (`types: {mppt:
  energy_source, dc_dc: dc_dc_source}`). Heterogeneous entities do not
  expose the same fields in their datasets (e.g. `MPPT_Data.current/power`
  vs `DC_DC_Data.output_current/output_power`): without qualification the
  type of the block declaring the repeat is used.
- The block `title` and the views' `data` paths are relative to the
  instance's base address.
- Each instance receives a unique identifier `<block id>-<index>`.

### 2.6 Endpoint fetch cycles

Fetches are **explicit and driven by usage** — a dataset is only queried if
a displayed element uses it:

| Dataset | Fetch cycle |
|---|---|
| `data` | at each page refresh cycle (`refresh_interval`), a single fetch per endpoint even if several views/blocks share it |
| `trend` | at the same cycle, **only if at least one view of the block references a `trend/...` path** (maps to a distinct `GetTrend` protobuf request) |
| `parameters` | once at page activation, then re-fetched on context change (keepalive `system_changed`); **only if** a title, a widget (`scale`) or a `repeat` references it |

Possible future optimizations (not addressed initially): separate frequency
for `trend`, request batching, backend-side caching. Simplicity first — this
scheme is anyway more efficient than the current situation where the
backend queries all datasets at every cycle.

## 3. Data paths

### 3.1 Processes, services and instances

**gRPC services are hosted in processes.** The process ↔ service link is
established by the backend (process configuration, agent status) and **does
not appear in the UI data paths**. The UI configuration references entities
(service + instance), never processes directly.

Two distinct dimensions must be distinguished:

| Notion | Definition | Examples |
|---|---|---|
| **multi-instance service** | a service managing several entities of the same type **within the same process**; the instance identifies the entity within the process | `battery`, `mppt`, `dc_dc`, `engine` |
| **multi-process service** | a single service type hosted by **several processes**; singleton in each process, but several instances in the system | `console` (present in every process) |

The complete backend address of an entity is therefore the triplet
**(service, process, instance)** — instance being 0 for singleton services
within their process.

**Process resolution rule** (backend, from the agent status):

1. The service is hosted by **a single process** → implicit resolution
   (the case of all EMS page services, hosted in the `energy` process;
   this is a special case, not a general rule).
2. The service is hosted by **several processes** (e.g. `console`) → the
   configuration must qualify the process explicitly, via the block's
   `process:` key (§2.4) or the `repeat` item (§2.5).
3. Service not found, or process not qualified although the service is
   multi-process → visible error in the block.

### 3.2 Data access paths

The data access path follows the schema:

```
/api/<service>/<instance>/<dataset>/<name>
```

- **service**: the gRPC service (protobuf `service` directive)
- **instance**: instance number (0 by default) for multi-instance services
  (§3.1); the process is resolved by the backend (§3.1), possibly
  qualified by the block's `process:` key
- **dataset**: a specific protobuf message (JSON structure between server
  and client). Four datasets:
  1. `parameters`: static or semi-static data, refreshed at startup or on
     context change
  2. `data`: instantaneous values
  3. `trend`: immediate history — the last value is the present instant.
     Specific case: values are stored in the `samples` array; this
     non-significant path element is omitted.
  4. `history`: long-term history — not implemented yet
- **name**: protobuf/JSON field name

Other datasets may be defined for other pages, outside the "energy" context.

### 3.3 Relative paths of views

The **dataset is always explicit** in the views' data paths:

- A view's `data` = `<dataset>/<name>`, e.g. `data/main_voltage`,
  `trend/power`, `parameters/label`. The dataset of the block's `endpoint`
  is the **primary** dataset (the one motivating the block's fetch); a view
  may reference another dataset (additional fetch, §2.6).
- Widget paths (`scale.max`/`low`/`high`, parameterized `color`, `title`)
  resolve: first in the `parameters` **of the block's service**
  (`/api/<service>/<instance>/parameters`), otherwise in the page's
  `parameters` dataset (`parameters_endpoint` of the page, if declared —
  page-level parameters are valid for the whole page).

## 4. Data visualization in blocks

Data falls into the following categories:

| Data type                  | Internal representation | Description                                                              | Additional data                      |
|----------------------------|-------------------------|--------------------------------------------------------------------------|---------------------------------------|
| positive scalar            | float                   | Positive floating-point number                                            | maximum display value                 |
| scalar                     | float                   | floating-point number                                                     | absolute maximum display value        |
| text                       | string (utf_8)          | Character string                                                          | maximum display character count      |
| date                       | string                  | ISO 8601 UTC date                                                         | N/A                                   |
| trend time series          | list[float]             | series of values at fixed interval, referenced to current time           | interval, maximum value              |
| regular time series        | list[float]             | series of values at fixed interval, referenced to a date                 | date, interval, maximum value        |

Series may be strictly positive or negative/positive.

The units used in the application are as follows (non-exhaustive list):

| Physical quantity | Unit                | Symbol | Type             |
|-------------------|---------------------|--------|------------------|
| Time/Duration     | second              | s      | positive scalar |
| Date              | N/A                 | N/A    | date             |
| Voltage           | Volt                | V      | positive scalar |
| Current           | Ampere              | A      | scalar           |
| Power             | Watt                | W      | scalar           |
| Energy            | Watt-hour           | Wh     | scalar           |
| Pressure          | hectoPascal         | hPa    | positive scalar |
| Rotation speed    | revolution/minute   | RPM    | positive scalar |
| Temperature       | Celsius             | °C     | scalar           |

**Ratio convention**: ratios (e.g. `state_of_charge`) are always represented
**between 0 and 1** in protobuf messages. The interface displays them as
**0-100 percent**; the conversion is the widget's responsibility (display
parameter), never the transport's.

## 5. Widgets

### 5.1 Viewgraph

A viewgraph is a graphical set made of the following elements:
- A centered title on 2 lines (if the title is a single word, 2 lines are
  always provisioned)
- A colored rectangle filled vertically proportionally to the represented
  data, with two variants: 0 at the bottom (`positive_viewgraph`) or 0 in
  the middle with positive values above and negative values below
  (`symmetric_viewgraph`). In the latter case the zero is marked by a
  horizontal line.
- The numeric value (signed if symmetric) with the precision given as
  parameter, followed by the unit symbol.

### 5.2 Time curves

Two variants: `positive_curve` or `symmetric_curve`. Same principle as the
bargraphs. By default, no axes or scale are drawn.

There may be widgets with a single curve or with two curves.

### 5.3 Histograms

Same principle as the curves but with a histogram chart.

### 5.4 Base widgets (consolidated list)

*Sufficient for the energy part; it may be extended for other pages,
without questioning the principles.*

| base_widget | Description |
|---|---|
| `positive_viewgraph` | bar, 0 at the bottom |
| `symmetric_viewgraph` | bar centered on 0 |
| `single_positive_curve` | one curve, positive values |
| `single_symmetric_curve` | one curve, signed values |
| `dual_curve` | two superimposed curves |
| `positive_histogram` / `symmetric_histogram` | histograms |
| `communication_indicator` | communication status indicator rendered in the block title (`top_widget`): **green** dot = `communication_ok` true, **red** = communication lost, **grey** = no data (missing `data` dataset) |
| `text_value` | plain text |

### 5.5 Widget dimensions

Viewgraphs have a fixed size across the whole application. These dimensions
are a global front-end parameter (`widget_defaults`). It may eventually be
dynamic depending on the screen resolution. The height is tied to the block
dimension; the number of widgets instantiable in a block is therefore
limited. **A visible error message is required if the generated view cannot
be constructed.** Curves and histograms take all the remaining space on the
right in the block.

### 5.6 Widget parameters

| parameter | values or type | meaning |
|-----------|----------------|---------|
| title     | string         | displayed title |
| unit      | string         | unit symbol |
| color     | string         | color palette reference (name) or coded value |
| precision | int [0, 3]     | number of decimals (default 0) |
| scale     | object (§5.7)  | scale definition: `{type: fixed\|dual\|dynamic, ...}` |
| data      | data path      | reference relative to the block endpoint, explicit dataset |

Parameters can be configured as arrays when multiple values have to be
displayed in the widget (e.g. `dual_curve` with two `data` paths and two
`color`s).

### 5.7 Scale definition (`scale`)

The display scale is defined by a structured object (reference values are
data paths, resolved per §3.3, or literal numeric values):

```yaml
scale: {type: fixed, max: parameters/max_voltage_scale}

scale:
  type: dual
  low: parameters/total_power_low      # low scale AND switching threshold
  high: parameters/total_power_high    # high scale

scale: {type: dynamic}
```

| Type | Meaning |
|---|---|
| `fixed` | constant scale; `max` = the displayable maximum value (or path) |
| `dual` | dual scale with automatic switching: the widget displays on the low scale while \|value\| ≤ `low`, otherwise on the high scale; `low` serves both as threshold and low scale, `high` is the high scale |
| `dynamic` | recomputed from the displayed series (observed min/max) |

### 5.8 Color palette

Colors are referenced by name in the configuration (e.g. `color: voltage`)
and resolved in a global palette declared at the front-end level (`colors`
parameter of the UI configuration), with possible direct coded value.

## 6. Configuration loading

Two ways to provide the configuration at startup:

1. **Web process YAML file** (deployment mode, `WebTopServer`): `ui_config`
   key in the `Main` block of `web_server.yml` (`run_server
   conf/web_server.yml`).
2. **Command line** (standalone test mode): `--ui-config <file>` option of
   `web_main()`.

In both cases, decoding is done by `yaml.safe_load()`:
`WebTopServer.__init__` (`web_top_server.py`) reads the `ui_config` key,
decodes the file and passes the dict to `NavigationWebServer(ui_config=...)`;
`web_main()` does the same for the `--ui-config` option.

The configuration is validated (dict with a `pages` key), then served as-is
to the front-end through `/api/ui_config` (404 if absent → the front-end
uses its embedded default configuration). The final decoding into page/block
objects is done browser-side by `js/ui/config.js` (`loadUiConfig()`) and
`js/ui/framework.js`.

Reference example: `conf/web_ui_default.yml`.

## 7. Protobuf service rationalization

### 7.1 Standard service structure

Each service systematically exposes **three datasets** = three protobuf
messages and three rpcs:

| Dataset | Message | Rpc (proposed standard naming) |
|---|---|---|
| `parameters` | `<Service>_Parameters` | `GetParameters` |
| `data` | `<Service>_Data` | `GetData` |
| `trend` | `<Service>_Trend` | `GetTrend` |

The current naming (`GetInformation`/`GetValues`) will be rationalized in
this direction during the protobuf work. Configuration/command services
(`SetConfiguration`, `DeviceCommand`) remain out of this scope.

### 7.2 EnergyController rationalization

The historical deviation (`EnergyControllerData` copied data from the
batteries, MPPT and DC-DC chargers, which have their own gRPC services) is
corrected: `EnergyControllerData` contains only the controller's
consolidated view (voltages, production, consumption, stock, balance, state
of charge). Each entity is served by its dedicated service.

| Block | Entity | Endpoint |
|---|---|---|
| Energy Controller | energy_controller | `/api/energy/0/...` |
| Battery | battery | `/api/battery/<instance>/...` |
| Sources (MPPT, DC-DC...) | mppt, dc_dc | `/api/mppt/<instance>/...`, `/api/dc_dc/<instance>/...` |

**Compatibility**: the Web server is considered part of the application: no
wire compatibility constraint between versions — the application (server
processes) and the Web server are updated simultaneously. The field
renumbering in `energy.proto` (e.g. `MPPT_device` absorbing
`MPPT_parameters`) is therefore accepted without reservation. After
modifying a `.proto`, always regenerate (`gen_proto`); the backend impacts
(`energy_mgmt/`, `data_collectors.py`, simulator) and the default UI
configuration (removed `batteries.0`/`sources` selectors) are to be handled
in the same iteration.

## 8. Adding a new page or block

1. Create or reuse **widgets** (`widgets` section) based on the hard-coded
   base widgets (`js/ui/views.js`).
2. Create or reuse a **block type** (`block_types` section), or define the
   views inline in the block.
3. Declare the page and its blocks (`pages` section): layout (`layout`,
   `position`/`priority`), endpoints, refresh cycle.
4. No HTML or navigation change is required: the framework builds the
   navigation buttons and the pages dynamically.

## 9. Reuse of the existing

The existing views must be reused and adapted, but the principles and the
look and feel of the current version must be preserved. It is the modular
construction and the parameterization that change, not the result.
