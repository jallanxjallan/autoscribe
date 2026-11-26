# Accepted application source reconciliation

Recovered app/asc, app/bin, app/daemon and app/tests from the accepted immutable
release qualified-d9aa18b58e29-8867afa0ad34b56a9f73. Every recovered file matched that release manifest
before copying. This is a snapshot recovery, not restoration of the unavailable
historical commit d9aa18b58e291e9056ff25f2ca67dc68ec381da4.
Common remains separately owned/pinned; native binaries and application dependencies
are reused unchanged. Release tooling starts from GitHub AutoScribe main
89fd3a6, not the unrelated modified home checkout.
