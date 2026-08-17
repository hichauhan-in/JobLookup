Drop your own `.docx` in this folder to use it as the CV layout.

JobLookup reads only the styles from it — fonts, sizes, margins, the definition
of "List Bullet" — and writes its own content. Any text already in the file is
removed.

To use one, set it on the Settings screen, or in `config/local.yaml`:

```yaml
tailor:
  template: my-layout.docx
```

Leave it blank for the built-in single-column layout, which is deliberately plain
so an applicant tracking system can extract the text from it correctly.
