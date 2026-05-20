# Context Bridge Browser Extension

Browser extensions for integrating Context Bridge with web-based chatbots.

## Extensions

- **[chrome/](chrome/)** — Chrome/Edge/Firefox extension (Manifest V3)

## Planned

- Firefox specific build
- Safari extension (App Extension)

## Architecture

All extensions communicate with the local Context Bridge HTTP server:

```
Browser Extension → localhost:8080 → Context Bridge → Your Data
```

## Development

See individual extension READMEs for build instructions.
