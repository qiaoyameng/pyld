# :material-arrow-expand: `jsonld.expand()`

::: pyld.jsonld.expand
    options:
      show_docstring_description: false

## Options

::: pyld.options.ExpandOptions
    options:
      show_root_heading: false
      show_bases: false
      heading_level: 3

## Diagnostics

Pass a list via the `expansionDiagnostics` option to collect an
`ExpansionDiagnostic` for every source value dropped during expansion. Each
diagnostic locates the dropped data with a JSON Pointer into the source
document, reports the reason, and records the provenance of the context that
was in effect. Diagnostics are observational only and never change the
expanded output.

::: pyld.options.ExpansionDiagnostic
    options:
      show_root_heading: false
      show_bases: false
      heading_level: 3

## Example

{{ example('expand.py', 'json') }}
